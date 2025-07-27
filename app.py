import os
import logging
from datetime import datetime

from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText

# ------------------------------------------------------------------------------
# Config / Env
# ------------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS      = int(os.getenv("MAX_TURNS", "6"))  # how many (user, assistant) pairs to retain

# Path to your **downloaded** ElevenLabs MP3 greeting (optional)
# Put the file in your repo (e.g. Voices/Arabella.mp3) and set this path.
ELEVENLABS_GREETING_MP3 = os.getenv(
    "ELEVENLABS_GREETING_MP3",
    "Voices/ElevenLabs_2025-07-25T15_10_26_Arabella_pvc_sp100_s63_sb100_v3.mp3"
)

# Email settings (optional – comment out send_email() calls if you don’t want it)
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER  = os.getenv("SMTP_USER")
SMTP_PASS  = os.getenv("SMTP_PASS")

# ------------------------------------------------------------------------------
# Init
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-phone")

app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# memory = {
#   "<CallSid>": {
#       "lang": "en"|"es",
#       "history": [{"role":"user"/"assistant","content":"..."}, ...]
#   }
# }
memory = {}


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def safe_detect_language(text: str, default="en") -> str:
    try:
        if not text:
            return default
        return "es" if detect(text).startswith("es") else "en"
    except Exception:
        return default

def system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde SIEMPRE en español, de forma natural y humana, y haz solo una pregunta a la vez. "
            "Permite interrupciones. Recolecta información clave: dirección, número de apartamento y problema de mantenimiento. "
            "Si mencionan renta, recomiéndales el portal de Buildium al final. No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You are a friendly, professional AI receptionist for a property management company. "
        "Respond ONLY in English, naturally, with a slow human tone. Ask one question at a time. "
        "Allow interruptions. Collect key info: property address, unit number, and maintenance issue. "
        "If rent is mentioned, advise using the Buildium portal at the end. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input: str, lang: str, history: list) -> str:
    trimmed = history[-MAX_TURNS*2:] if MAX_TURNS > 0 else history
    messages = [{"role": "system", "content": system_prompt(lang)}] + trimmed + [
        {"role": "user", "content": user_input}
    ]
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=220
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.exception("OpenAI error")
        return "Lo siento, hubo un problema generando la respuesta. ¿Podrías repetir?" if lang == "es" \
               else "Sorry, I had trouble generating a response. Could you say that again?"

def send_email(subject: str, body: str):
    if not (EMAIL_FROM and SMTP_USER and SMTP_PASS):
        log.info("Email credentials not set. Skipping email send.")
        return
    try:
        recipients = [
            "andrew@grhusaproperties.net",
            "leasing@grhusaproperties.net",
            "office@grhusaproperties.net",
        ]
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = EMAIL_FROM
        msg["To"]      = ", ".join(recipients)

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, recipients, msg.as_string())

        log.info("Email sent.")
    except Exception as e:
        log.exception("Failed to send email")

def greeting_for(lang: str) -> str:
    return (
        "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
        if lang == "es"
        else "Hello, this is the AI assistant for GRHUSA Properties. How can I help you today?"
    )

def polly_voice_for(lang: str) -> str:
    # A couple of reasonable Polly voices Twilio supports
    return "Polly.Lupe" if lang == "es" else "Polly.Joanna"

def twilio_language_code(lang: str) -> str:
    return "es-US" if lang == "es" else "en-US"


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "✅ AI receptionist (OpenAI + optional ElevenLabs greeting) is running", 200


@app.route("/voice", methods=["POST"])
def voice():
    """
    Main Twilio webhook. We greet (playing ElevenLabs mp3 if present) on the first hit (no SpeechResult).
    After that we loop on /voice, receiving speech -> generating answer -> speaking.
    """
    call_sid = request.values.get("CallSid")
    speech   = (request.values.get("SpeechResult") or "").strip()

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": []}

    # Detect language the first time the caller actually speaks
    if speech and len(memory[call_sid]["history"]) == 0:
        memory[call_sid]["lang"] = safe_detect_language(speech, "en")

    lang       = memory[call_sid]["lang"]
    voice_name = polly_voice_for(lang)
    lang_code  = twilio_language_code(lang)
    resp       = VoiceResponse()

    # First round => greet
    if not speech:
        greet = greeting_for(lang)

        # If you want to play your ElevenLabs greeting mp3 FIRST, do it here:
        if ELEVENLABS_GREETING_MP3 and os.path.exists(ELEVENLABS_GREETING_MP3):
            resp.play(ELEVENLABS_GREETING_MP3)

        # Always follow with the textual greeting (in case mp3 is short)
        gather = Gather(
            input="speech",
            timeout=10,
            speech_timeout="auto",
            action="/voice",
            method="POST",
            barge_in=True  # Twilio supports this attr now; if your helper lib complains, remove it.
        )
        gather.say(greet, voice=voice_name, language=lang_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # If we get here, user spoke: add to history
    memory[call_sid]["history"].append({"role": "user", "content": speech})

    # Generate answer
    reply = generate_response(speech, lang, memory[call_sid]["history"])
    memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    # Email turn summary (optional)
    turn_summary = f"""
📞 New Tenant Call Turn

🗣️ Caller said:
{speech}

🤖 Assistant replied:
{reply}

🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
(CallSid: {call_sid})
"""
    send_email("📬 AI Call Turn – GRHUSA", turn_summary)

    # Speak reply
    resp.say(reply, voice=voice_name, language=lang_code)

    # Loop for next user input
    gather = Gather(
        input="speech",
        timeout=10,
        speech_timeout="auto",
        action="/voice",
        method="POST",
        barge_in=True
    )
    resp.append(gather)

    return Response(str(resp), mimetype="application/xml")


# Optional: Voicemail endpoint if you decide to add Record() flow later
@app.route("/voicemail", methods=["POST"])
def voicemail():
    recording_url = request.values.get("RecordingUrl", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"Voicemail received at {timestamp}.\n\nListen:\n{recording_url}"
    send_email("📨 New Tenant Voicemail", body)
    return Response("OK", mimetype="text/plain")


# ------------------------------------------------------------------------------
# main
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
