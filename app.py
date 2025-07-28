# app.py

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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
        if not text:
            return default
        lang = detect(text)
        return "es" if lang.startswith("es") else "en"
    except Exception:
        return default

def system_prompt(lang):
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde SIEMPRE en español, de forma natural, humana y con tono calmado. "
            "Haz solo una pregunta a la vez. Acepta interrupciones. "
            "Recolecta: dirección de propiedad, número de apartamento, problema de mantenimiento y mejor forma de contacto. "
            "Si mencionan renta, diles al final que usen el portal de Buildium. "
            "No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You are a friendly, professional AI receptionist for a property management company. "
        "Respond ONLY in English, naturally, with a calm human tone. Ask one question at a time. "
        "Allow interruptions. Collect: property address, unit number, maintenance issue, and best callback method. "
        "If rent is mentioned, tell them at the end to use the Buildium portal. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input, lang, history):
    trimmed = history[-MAX_TURNS*2:] if MAX_TURNS > 0 else history
    messages = [{"role": "system", "content": system_prompt(lang)}] + trimmed + [{"role": "user", "content": user_input}]
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
        return "Lo siento, ¿puedes repetir?" if lang == "es" else "Sorry, can you say that again?"

def send_email(subject, body):
    if not (EMAIL_FROM and SMTP_USER and SMTP_PASS):
        log.warning("Email creds not set; skipping email.")
        return
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
        log.exception("Failed to send email")

def post_to_n8n(payload):
    if not N8N_WEBHOOK_URL:
        return
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        log.exception("POST to n8n failed")

def greeting_for(lang):
    return "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?" if lang == "es" else "Hello, this is the AI assistant for GRHUSA Properties. How can I help you today?"

def twilio_voice_for(lang):
    return "Polly.Conchita" if lang == "es" else "Polly.Joanna"

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
        who = "Tenant" if msg["role"] == "user" else "AI"
        lines.append(f"{who}: {msg['content']}")

    body = (
        f"📞 Call Summary (CallSid: {call_sid})\n"
        f"Time: {now}\n"
        f"Language: {lang}\n\n" +
        "\n".join(lines)
    )

    send_email("📬 Tenant Call – Transcript/Turns", body)
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

    if speech and len(data["history"]) == 0:
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
        reply = "Gracias por llamar. ¡Hasta luego!" if lang == "es" else "Thanks for calling. Goodbye!"
        data["history"].append({"role": "assistant", "content": reply})
        final_email_and_n8n(call_sid)
        data["done"] = True
        resp.say(reply, voice=voice_name, language=lang_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    data["history"].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, data["history"])
    data["history"].append({"role": "assistant", "content": reply})

    # Optional: comment this if you ONLY want final email
    send_email("📬 AI Call Turn – GRHUSA", f"Tenant: {speech}\n\nAI: {reply}")
    post_to_n8n({
        "callSid": call_sid,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "tenant": speech,
        "assistant": reply,
        "lang": lang
    })

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
