import os
import logging
from datetime import datetime

from flask import Flask, request, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS      = int(os.getenv("MAX_TURNS", "6"))

# Path INSIDE your /static folder (we'll turn it into a full absolute URL)
ELEVENLABS_GREETING_FILE = os.getenv(
    "ELEVENLABS_GREETING_FILE",
    "voices/ElevenLabs_2025-07-25T15_10_26_Arabella_pvc_sp100_s63_sb100_v3.mp3"
)

EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER  = os.getenv("SMTP_USER")
SMTP_PASS  = os.getenv("SMTP_PASS")

# ------------------------------------------------------------------------------
# Init
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-phone")

app = Flask(__name__, static_folder="static")  # make sure your static dir is named 'static'
client = OpenAI(api_key=OPENAI_API_KEY)

# memory = { call_sid: { "lang": "en"/"es", "history": [] } }
memory = {}

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def safe_detect_language(text: str, default="en") -> str:
    try:
        if not text:
            return default
        lang = detect(text)
        return "es" if lang.startswith("es") else "en"
    except Exception:
        return default

def system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde SIEMPRE en español, de forma natural y humana, y haz solo una pregunta a la vez. "
            "Permite interrupciones. Recolecta dirección, número de apartamento y problema de mantenimiento. "
            "Si mencionan renta, recomiéndales el portal de Buildium al final. No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You are a friendly, professional AI receptionist for a property management company. "
        "Respond ONLY in English, naturally, with a slow human tone. Ask one question at a time. "
        "Allow interruptions. Collect property address, unit number, and maintenance issue. "
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
        return ("Lo siento, hubo un problema generando la respuesta. ¿Podrías repetir?"
                if lang == "es"
                else "Sorry, I had trouble generating a response. Could you say that again?")

def send_email(subject: str, body: str):
    if not (EMAIL_FROM and SMTP_USER and SMTP_PASS):
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
    except Exception:
        log.exception("Failed to send email")

def greeting_for(lang: str) -> str:
    return ("Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
            if lang == "es"
            else "Hello, this is the AI assistant for GRHUSA Properties. How can I help you today?")

def polly_voice_for(lang: str) -> str:
    # Good Polly voices in Twilio
    return "Polly.Conchita" if lang == "es" else "Polly.Joanna"

def twilio_language_code(lang: str) -> str:
    # Use es-ES instead of es-US to avoid Twilio mismatch
    return "es-ES" if lang == "es" else "en-US"

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "✅ AI receptionist running (static ElevenLabs greeting + Polly dynamic speech).", 200

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech   = (request.values.get("SpeechResult") or "").strip()

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": []}

    # Lock language after first real utterance
    if speech and len(memory[call_sid]["history"]) == 0:
        detected = safe_detect_language(speech, "en")
        memory[call_sid]["lang"] = detected
        log.info(f"[{call_sid}] Detected language: {detected}")

    lang       = memory[call_sid]["lang"]
    voice_name = polly_voice_for(lang)
    lang_code  = twilio_language_code(lang)

    resp = VoiceResponse()

    # First round: greet
    if not speech:
        greet = greeting_for(lang)

        # play ElevenLabs greeting (absolute URL Twilio can fetch)
        greeting_url = None
        if ELEVENLABS_GREETING_FILE:
            # ensure file lives under /static
            # e.g. static/voices/your.mp3 => ELEVENLABS_GREETING_FILE = "voices/your.mp3"
            greeting_url = url_for("static", filename=ELEVENLABS_GREETING_FILE, _external=True)

        if greeting_url:
            resp.play(greeting_url)

        gather = Gather(
            input="speech",
            timeout=10,
            speech_timeout="auto",
            action="/voice",
            method="POST",
            barge_in=True
        )
        gather.say(greet, voice=voice_name, language=lang_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # User spoke
    memory[call_sid]["history"].append({"role": "user", "content": speech})

    reply = generate_response(speech, lang, memory[call_sid]["history"])
    memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    # Email the turn (optional)
    turn_summary = f"""
📞 AI Phone Bot Turn
CallSid: {call_sid}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

User said:
{speech}

Assistant replied:
{reply}
"""
    send_email("📬 AI Call Turn – GRHUSA", turn_summary)

    # Speak reply
    resp.say(reply, voice=voice_name, language=lang_code)

    # Keep listening
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
