import os
import logging
from datetime import datetime
from flask import Flask, request, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText
import requests

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_TURNS = int(os.getenv("MAX_TURNS", "6"))

EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_TO = os.getenv("EMAIL_TO", "andrew@grhusaproperties.net")

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
ELEVENLABS_GREETING_FILE = os.getenv("ELEVENLABS_GREETING_FILE")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-phone")

app = Flask(__name__, static_folder="static")
client = OpenAI(api_key=OPENAI_API_KEY)
memory = {}

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def safe_detect_language(text, default="en"):
    try:
        lang = detect(text)
        if len(text.split()) <= 2:
            if any(x in text.lower() for x in ["hola", "gracias", "español"]):
                return "es"
        return "es" if lang.startswith("es") else "en"
    except Exception:
        return default

def system_prompt(lang):
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde SIEMPRE en español, de forma natural y con tono calmado. Haz solo una pregunta a la vez. "
            "Recolecta: dirección, número de apartamento, problema de mantenimiento, y mejor contacto. "
            "Si mencionan renta, diles al final que usen el portal de Buildium. No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You are a friendly AI receptionist for a property management company. "
        "Respond ONLY in English with a natural, calm tone. Ask one question at a time. "
        "Collect: property address, unit number, maintenance issue, and best callback method. "
        "If rent is mentioned, tell them at the end to use the Buildium portal. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input, lang, history):
    messages = [
        {"role": "system", "content": system_prompt(lang)},
        {"role": "user", "content": "Responde solo en español." if lang == "es" else "Respond only in English."}
    ] + history[-MAX_TURNS*2:] + [{"role": "user", "content": user_input}]

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=220
        )
        return response.choices[0].message.content.strip()
    except Exception:
        log.exception("OpenAI error")
        return "Lo siento, ¿puedes repetir?" if lang == "es" else "Sorry, can you say that again?"

def send_email(subject, body):
    try:
        recipients = [x.strip() for x in EMAIL_TO.split(",") if x.strip()]
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, recipients, msg.as_string())
    except Exception:
        log.exception("EMAIL FAILED via SMTP")

def post_to_n8n(payload):
    if not N8N_WEBHOOK_URL:
        return
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        log.exception("POST to n8n failed")

def greeting_for(lang):
    return "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?" if lang == "es" else "Thank you for calling GRHUSA Properties. How can I help you today?"

def twilio_voice_for(lang):
    return "Polly.Lupe" if lang == "es" else "Polly.Joanna"

def twilio_language_code(lang):
    return "es-ES" if lang == "es" else "en-US"

def final_email_and_n8n(call_sid):
    data = memory.get(call_sid, {})
    if not data:
        return
    lang = data.get("lang", "en")
    history = data.get("history", [])
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = []
    for msg in history:
        who = "TENANT" if msg["role"] == "user" else "AI"
        lines.append(f"{who}: {msg['content']}")

    body = (
        f"📞 AI Tenant Call Summary\n"
        f"Time: {now}\n"
        f"Language: {lang.upper()}\n\n" +
        "\n".join(lines)
    )

    send_email("📬 AI Receptionist – Final Call Summary", body)
    post_to_n8n({
        "callSid": call_sid,
        "timestamp": now,
        "lang": lang,
        "history": history
    })

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "✅ AI receptionist running", 200

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech = (request.values.get("SpeechResult") or "").strip()

    if not call_sid:
        return Response("<Response></Response>", mimetype="application/xml")

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": [], "done": False}

    data = memory[call_sid]
    if speech and not data["history"]:
        data["lang"] = safe_detect_language(speech)

    lang = data["lang"]
    voice_name = twilio_voice_for(lang)
    lang_code = twilio_language_code(lang)

    resp = VoiceResponse()

    if data.get("done"):
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    if not speech:
        if ELEVENLABS_GREETING_FILE:
            try:
                greeting_url = url_for("static", filename=ELEVENLABS_GREETING_FILE, _external=True)
                resp.play(greeting_url)
            except Exception:
                log.warning("Greeting file not found.")
        gather = Gather(
            input="speech",
            timeout=6,
            speech_timeout="auto",
            action="/voice",
            method="POST",
            barge_in=True
        )
        gather.say(greeting_for(lang), voice=voice_name, language=lang_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    if any(x in speech.lower() for x in ["bye", "goodbye", "thanks", "adios", "gracias"]):
        data["history"].append({"role": "user", "content": speech})
        reply = "Gracias por llamar a GRHUSA Properties. Que tenga un buen día. ¡Adiós!" if lang == "es" else "Thanks for calling GRHUSA Properties. Have a great day. Goodbye!"
        data["history"].append({"role": "assistant", "content": reply})
        data["done"] = True
        final_email_and_n8n(call_sid)
        resp.say(reply, voice=voice_name, language=lang_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    data["history"].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, data["history"])
    data["history"].append({"role": "assistant", "content": reply})

    resp.say(reply, voice=voice_name, language=lang_code)
    gather = Gather(
        input="speech",
        timeout=6,
        speech_timeout="auto",
        action="/voice",
        method="POST",
        barge_in=True
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/status", methods=["POST"])
def status():
    call_sid = request.values.get("CallSid")
    call_status = request.values.get("CallStatus")
    log.info(f"Status callback {call_sid=} {call_status=}")
    if call_status == "completed" and call_sid in memory and not memory[call_sid].get("done"):
        final_email_and_n8n(call_sid)
        memory[call_sid]["done"] = True
    return ("", 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
