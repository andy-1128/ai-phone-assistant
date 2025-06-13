import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Environment secrets
openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = "notifications@grhusaproperties.net"
EMAIL_RECEIVER = "andrew@grhusaproperties.net"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")

def detect_language(text):
    try:
        lang = detect(text)
        return "es" if lang == "es" else "en"
    except:
        return "en"

def prompt_response(user_input, lang="en"):
    system_msg = {
        "en": (
            "You're a warm, confident, fast-speaking female AI receptionist for GRHUSA Properties. "
            "Start with 'Hi, this is the AI assistant from GRHUSA Properties. You can speak to me naturally. How can I help you today?'. "
            "If the caller talks about rent, urge them to use the Buildium portal or app. "
            "If they mention a broken toilet, leak, or repair, acknowledge it and say it will be escalated. "
            "If Liz or Elsie are mentioned, say 'Thanks, this will be escalated to the team and someone will follow up.'"
        ),
        "es": (
            "Eres una recepcionista virtual amable, rápida y profesional para GRHUSA Properties. "
            "Comienza con 'Hola, soy la asistente virtual de GRHUSA Properties. Puedes hablarme como si fuera una persona real. ¿En qué puedo ayudarte?'. "
            "Si mencionan alquiler, dile que usen la app de Buildium. "
            "Si mencionan problemas como inodoros rotos o fugas, reconócelo y di que se escalará. "
            "Si mencionan a Liz o Elsie, responde que se escalará al equipo y alguien los contactará."
        )
    }

    messages = [
        {"role": "system", "content": system_msg[lang]},
        {"role": "user", "content": user_input}
    ]

    completion = openai.ChatCompletion.create(model="gpt-4", messages=messages)
    return completion.choices[0].message["content"]

def send_summary_email(text):
    if not SMTP_USER or not SMTP_PASS:
        print("Missing SMTP credentials")
        return
    try:
        msg = MIMEText(text)
        msg["Subject"] = "Tenant Call Summary"
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

@app.route("/voice", methods=["POST"])
def voice():
    speech = request.form.get("SpeechResult")
    resp = VoiceResponse()

    if not speech:
        gather = Gather(input="speech", timeout=5, speech_timeout="auto", action="/voice", method="POST")
        gather.say(
            "Hello, this is the AI assistant from GRHUSA Properties. You can speak to me like a real person. How can I help you today?",
            voice="Polly.Joanna", language="en-US"
        )
        resp.append(gather)
        return Response(str(resp), mimetype="text/xml")

    lang = detect_language(speech)
    reply = prompt_response(speech, lang)
    send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")

    resp.say(reply, voice="Polly.Joanna" if lang == "en" else "Polly.Mia", language="en-US" if lang == "en" else "es-US")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")

@app.route("/", methods=["GET"])
def health():
    return "AI receptionist is running.", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
