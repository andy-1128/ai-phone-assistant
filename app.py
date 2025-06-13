import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)

# Environment Variables
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
        "You are a smart, caring, and human-like AI receptionist for a property management company. "
        "If the tenant mentions rent, tell them to use the Buildium portal to pay. "
        "If there's a problem like a leak or broken toilet, ask for the property address and apartment number, "
        "advise them to submit a maintenance ticket via Buildium, and say the call will be sent to the team. "
        "If Liz or Elsie are mentioned, say: 'This will be escalated to the team and someone will reach out.' "
        "Only stop talking when the caller speaks (barge-in), and resume politely. Avoid sounding robotic or repetitive."
        if lang == "en" else
        "Eres una recepcionista virtual humana y amable para una empresa de bienes raíces. "
        "Si mencionan la renta, diles que usen la aplicación de Buildium. "
        "Si mencionan un problema, pregunta por la dirección y número del apartamento, "
        "indica que ingresen un ticket de mantenimiento y que esta llamada se enviará al equipo. "
        "Si mencionan a Liz o Elsie, responde: 'Esto será escalado al equipo y alguien se comunicará.'"
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
            barge_in=True, action="/voice", method="POST"
        )
        greet = "Hello, this is the AI assistant from GRHUSA Properties. How can I help you today?" \
            if lang == "en" else "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    if any(x in speech for x in ["leave a message", "voicemail", "dejar mensaje", "mensaje"]):
        resp.say("Okay, please leave your message after the beep. We will follow up shortly.",
                 voice=voice_id, language=language_code)
        resp.record(max_length=90, timeout=5, transcribe=True, play_beep=True, action="/voicemail")
        resp.say("Thank you. Goodbye!", voice=voice_id, language=language_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    if "bye" in speech or "goodbye" in speech or "adios" in speech:
        resp.say("Thank you for calling. Take care.", voice=voice_id, language=language_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    reply = generate_response(speech, lang)
    send_email("Tenant Call Summary", f"Tenant said: {speech}\n\nAI replied: {reply}")

    resp.say(reply, voice=voice_id, language=language_code)
    gather = Gather(
        input="speech", timeout=6, speech_timeout="auto",
        barge_in=True, action="/voice", method="POST"
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/voicemail", methods=["POST"])
def voicemail():
    recording_url = request.values.get("RecordingUrl", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"Voicemail received at {timestamp}.\n\nLink: {recording_url}"
    send_email("New Tenant Voicemail", body)
    return Response("OK", mimetype="text/plain")

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist is live", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
