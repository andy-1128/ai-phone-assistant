import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)

# ENV Variables
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
        "You are a professional and warm AI receptionist for a real estate company. "
        "Respond conversationally like a human. If the caller mentions rent, tell them to use the Buildium app. "
        "You are respectable and caring, help problem solve and troubleshoot" 
        "If they mention issues like broken toilets, leaks, or damage, express empathy and state the team will follow up. "
        "Only mention Liz or Elsie if the caller says their names, and reply that 'this will be escalated to the team and someone will reach out.'"
        if lang == "en" else
        "Eres una recepcionista profesional para una empresa inmobiliaria. "
        "Responde como un humano con empatía. Si mencionan el alquiler, dile que usen la aplicación Buildium. "
        "Si mencionan problemas como inodoros rotos o fugas, reconócelo y di que el equipo dará seguimiento. "
        "Solo menciona a Liz o Elsie si el inquilino dice su nombre — responde que será escalado al equipo."
    )
    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    return completion.choices[0].message.content.strip()

def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
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
    speech = request.values.get("SpeechResult", "").lower()
    lang = detect_language(speech)
    voice_id = "Polly.Kimberly" if lang == "en" else "Lucia"
    language_code = "en-US" if lang == "en" else "es-US"

    resp = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech", timeout=6, speech_timeout="auto",
            action="/voice", method="POST"
        )
        greet = "Hello, this is the AI assistant from GRHUSA Properties. How can I help?" if lang == "en" else "Hola, soy la asistente virtual de GRHUSA Properties. ¿En qué puedo ayudarte?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Voicemail condition
    if any(x in speech for x in ["leave a message", "voicemail", "dejar mensaje", "mensaje"]):
        resp.say("Sure, leave your message after the beep. We will follow up shortly.", voice=voice_id, language=language_code)
        resp.record(max_length=60, timeout=5, transcribe=True, play_beep=True, action="/voicemail")
        resp.say("Thank you. Goodbye!", voice=voice_id, language=language_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    reply = generate_response(speech, lang)
    send_email("Tenant Call Summary", f"Tenant said: {speech}\n\nAI replied: {reply}")

    resp.say(reply, voice=voice_id, language=language_code)
    gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/voicemail", methods=["POST"])
def voicemail():
    recording_url = request.values.get("RecordingUrl", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"Voicemail received at {timestamp}.\n\nListen to the voicemail here:\n{recording_url}"
    send_email("New Tenant Voicemail", body)
    return Response("OK", mimetype="text/plain")

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
