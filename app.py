
import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI

app = Flask(__name__)

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

client = OpenAI(api_key=OPENAI_API_KEY)

def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

def generate_response(user_input, lang="en"):
    system_prompt = (
        "You are a fast, fluent, helpful AI receptionist for a real estate company. "
        "Speak like a natural human. If the tenant mentions rent, tell them to pay using the Buildium app. "
        "You conversate like a human and respond to questions and concerns"
        "You are respectable and caring about problems and concerns"
        "If they mention a problem like a broken toilet or leak, acknowledge and say the team will follow up. "
        "Only mention Liz or Elsie if the tenant says their name — then respond 'this will be escalated to the team and someone will reach out.'"
        if lang == "en" else
        "Eres una recepcionista rápida y servicial para una empresa inmobiliaria. "
        "Si un inquilino menciona el alquiler, dile que use la aplicación de Buildium. "
        "Si menciona problemas como un inodoro roto o fugas, reconócelo y di que el equipo dará seguimiento. "
        "Solo menciona a Liz o Elsie si el inquilino dice su nombre — entonces responde 'esto será escalado al equipo y alguien se comunicará'."
    )

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    return completion.choices[0].message.content.strip()

def send_email_summary(speech, reply):
    try:
        msg = MIMEText(f"Tenant said: {speech}\n\nAI replied: {reply}")
        msg["Subject"] = "Tenant Call Summary"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, EMAIL_TO.split(",")[0], msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

@app.route("/voice", methods=["POST"])
def voice():
    speech = request.values.get("SpeechResult", "")
    lang = detect_language(speech)
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    language_code = "en-US" if lang == "en" else "es-US"

    resp = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech",
            timeout=6,
            speech_timeout="auto",
            action="/voice",
            method="POST"
        )
        gather.say(
            "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?",
            voice=voice_id, language=language_code
        )
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Handle response
    reply = generate_response(speech, lang)
    send_email_summary(speech, reply)

    resp.say(reply, voice=voice_id, language=language_code)
    gather = Gather(
        input="speech",
        timeout=6,
        speech_timeout="auto",
        action="/voice",
        method="POST"
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "AI receptionist running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
