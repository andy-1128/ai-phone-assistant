import os
from flask import Flask, request, Response, send_file
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO", "andrew@grhusaproperties.net")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
VOICEMAIL_FOLDER = "./voicemails"
BUILDIUM_API_KEY = os.getenv("BUILDIUM_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Ensure voicemail folder exists
os.makedirs(VOICEMAIL_FOLDER, exist_ok=True)

def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

def generate_response(user_input, lang="en"):
    system_prompt = (
        "You are a fast, fluent, helpful AI receptionist for a real estate company. "
        "Speak like a natural human. If the tenant mentions rent, tell them to pay using the Buildium app. "
        "You respond to questions and concerns respectfully and helpfully. "
        "If they mention a broken toilet, leaks, or power outages, acknowledge the issue and say the team will follow up. "
        "Only mention Liz or Elsie if the tenant says their name — then respond 'this will be escalated to the team and someone will reach out.'"
        if lang == "en" else
        "Eres una recepcionista rápida y servicial para una empresa inmobiliaria. "
        "Si un inquilino menciona el alquiler, dile que use la aplicación de Buildium. "
        "Si menciona problemas como un inodoro roto, fugas o cortes de luz, reconócelo y di que el equipo dará seguimiento. "
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

def send_email(subject, content):
    try:
        msg = MIMEText(content)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

@app.route("/voice", methods=["POST"])
def voice():
    speech = request.values.get("SpeechResult", "").lower()
    recording_url = request.values.get("RecordingUrl")
    lang = detect_language(speech)
    voice_id = "Polly.Kimberly" if lang == "en" else "Polly.Lupe"
    language_code = "en-US" if lang == "en" else "es-US"

    resp = VoiceResponse()

    if recording_url:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        recording_link = f"{recording_url}.mp3"
        content = f"Voicemail received at {timestamp}."
Listen: {recording_link}"
        send_email("New Tenant Voicemail", content)
        resp.say("Thank you for your message. Someone will reach out shortly. Goodbye.", voice=voice_id, language=language_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    if not speech:
        gather = Gather(
            input="speech",
            timeout=6,
            speech_timeout="auto",
            action="/voice",
            method="POST"
        )
        greet = "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?" if lang == "en" else "Hola, soy la asistente de GRHUSA Properties. ¿Cómo puedo ayudarte?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    if any(keyword in speech for keyword in ["leave a message", "voicemail", "mensaje", "dejar mensaje"]):
        resp.say("Sure, leave your message after the beep.", voice=voice_id, language=language_code)
        resp.record(max_length=90, timeout=5, transcribe=False, play_beep=True)
        return Response(str(resp), mimetype="application/xml")

    reply = generate_response(speech, lang)
    send_email("Tenant Call Summary", f"Tenant said: {speech}

AI replied: {reply}")
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
    return "AI receptionist with voicemail logging & ticket forwarding is running", 200
