import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from twilio.rest import Client
from concurrent.futures import ThreadPoolExecutor

# -----------------------
# Config / Globals
# -----------------------
app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # faster/cheaper by default
MAX_TURNS      = int(os.getenv("MAX_TURNS", "6"))          # keep only last N user/assistant turns

EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER  = os.getenv("SMTP_USER")
SMTP_PASS  = os.getenv("SMTP_PASS")

TWILIO_SID    = os.getenv("TWILIO_SID")
TWILIO_AUTH   = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

client        = OpenAI(api_key=OPENAI_API_KEY)
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# async worker just for emails so Twilio isn't blocked
executor = ThreadPoolExecutor(max_workers=4)

# memory: { call_sid: { "lang": "en"/"es", "history": [ {role, content}, ... ] } }
memory = {}

VOICE_BY_LANG = {
    "en": {"voice": "Polly.Joanna", "code": "en-US"},
    "es": {"voice": "Polly.Lupe",   "code": "es-US"},
}

# -----------------------
# Helpers
# -----------------------
def safe_detect_language(text: str, default_lang="en"):
    try:
        lang = detect(text) if text else default_lang
        return "es" if lang.startswith("es") else "en"
    except Exception:
        return default_lang

def build_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una recepcionista de IA de una empresa de administración de propiedades. "
            "Responde con naturalidad, profesionalismo y tono humano. Habla despacio. "
            "Haz solo una pregunta a la vez. Detente si el usuario te interrumpe. "
            "Guarda datos clave (dirección, número de apartamento, problema de mantenimiento). "
            "Si mencionan renta, recomiéndales usar el portal de Buildium al final. "
            "No cuelgues a menos que digan 'adiós'."
        )
    return (
        "You're a smart, fluent, friendly, professional AI receptionist for a property management company. "
        "Respond in a natural, slow-paced, human tone. Only ask one question at a time. "
        "Stop talking if the caller interrupts and re-evaluate. "
        "Capture key info: property address, unit number, and maintenance issue. "
        "If rent is mentioned, advise using the Buildium portal at the end. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input, lang, history):
    """
    history: list of {'role': 'user'/'assistant', 'content': ...}
    Only keep latest MAX_TURNS*2 messages (user+assistant pairs).
    """
    system_prompt = build_system_prompt(lang)
    trimmed = history[-MAX_TURNS*2:] if MAX_TURNS > 0 else history

    messages = [{"role": "system", "content": system_prompt}] + trimmed + [
        {"role": "user", "content": user_input}
    ]

    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.5,     # slightly colder => faster, more on-topic
            max_tokens=150
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI error:", e)
        return ("I'm having a little trouble formulating a response. Could you please repeat that?" 
                if lang == "en" else
                "Estoy teniendo un pequeño problema para responder. ¿Puedes repetir, por favor?")

def send_email_async(subject, body):
    executor.submit(send_email, subject, body)

def send_email(subject, body):
    if not (EMAIL_FROM and SMTP_USER and SMTP_PASS):
        return
    try:
        recipients = [
            "andrew@grhusaproperties.net",
            "leasing@grhusaproperties.net",
            "office@grhusaproperties.net"
        ]
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

def get_lang_bundle(call_sid):
    lang = memory[call_sid].get("lang", "en")
    voice = VOICE_BY_LANG[lang]["voice"]
    code  = VOICE_BY_LANG[lang]["code"]
    return lang, voice, code

# -----------------------
# Routes
# -----------------------
@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist running", 200

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech   = (request.values.get("SpeechResult") or "").strip()

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": []}

    # auto detect language (first time we get speech)
    if speech:
        detected = safe_detect_language(speech)
        # only update if we haven't already locked onto a language
        if len(memory[call_sid]["history"]) == 0:
            memory[call_sid]["lang"] = detected

    lang, voice_id, language_code = get_lang_bundle(call_sid)
    resp = VoiceResponse()

    # First turn: greet and gather
    if not speech:
        gather = Gather(
            input="speech",
            timeout=10,
            speech_timeout="auto",
            action="/voice",
            method="POST"
        )
        greet = (
            "Hello, this is the assistant from GRHUSA Properties. How can I help you today?"
            if lang == "en" else
            "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
        )
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Add user message to memory
    memory[call_sid]["history"].append({"role": "user", "content": speech})

    # Generate assistant reply
    reply = generate_response(speech, lang, memory[call_sid]["history"])
    memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    # Async email summary (don't block Twilio)
    summary = f"""📞 New Tenant Call Summary
🆔 Call SID: {call_sid}
🗣️ Tenant said: {speech}
🤖 AI replied: {reply}
🕒 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Language: {lang}
"""
    send_email_async("📬 Tenant Call Summary – GRHUSA", summary)

    # Speak reply & keep gathering
    resp.say(reply, voice=voice_id, language=language_code)

    gather = Gather(
        input="speech",
        timeout=10,
        speech_timeout="auto",
        action="/voice",
        method="POST"
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/outbound", methods=["POST"])
def outbound():
    """Trigger a cold call to a number. POST form/json: number=+1XXX"""
    number = request.values.get("number") or request.json.get("number")
    if not number:
        return {"error": "number is required"}, 400

    url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") + "/voice"
    if not url:
        # fallback to Render URL if set as RENDER_EXTERNAL_URL
        url = (os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/") + "/voice") or "/voice"

    twilio_client.calls.create(
        to=number,
        from_=TWILIO_NUMBER,
        url=url
    )
    return {"status": f"Call initiated to {number}"}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
