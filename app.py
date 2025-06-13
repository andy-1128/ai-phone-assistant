import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI
from datetime import datetime

app = Flask(__name__)

# Environment variables
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
        "You are a professional and friendly AI receptionist for a real estate property company called GRHUSA. "
        "Converse naturally, respond intelligently to any topic, and engage warmly. "
        "If the caller talks about rent, tell them to pay using the Buildium app or resident portal. "
        "If the caller mentions a problem (e.g. leaking toilet, broken appliance), ask for the property address and apartment number. "
        "Tell them to submit a maintenance ticket in the Buildium portal, and say this call will be forwarded to the team. "
        "Only mention Liz or Elsie if the tenant says their names. Then say 'this will be escalated to the team and someone will reach out.'"
        if lang == "en" else
        "Eres una recepcionista profesional y amable para una empresa inmobiliaria llamada GRHUSA. "
        "Habla como humano, responde con empatía y amabilidad. "
        "Si hablan del alquiler, diles que paguen usando la aplicación o portal Buildium. "
        "Si mencionan un problema (ej. inodoro roto, fuga), pide la dirección de la propiedad y el número del apartamento. "
        "Diles que ingresen un ticket en el portal de Buildium y que esta llamada será enviada al equipo. "
        "Solo menciona a Liz o Elsie si ellos las mencionan — responde que se escalará al equipo."
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
        print(f"[Email Error] {e}")

@app.route("/voice", methods=["POST"])
def voice():
    speech = request.values.get("SpeechResult", "").lower()
    lang = detect_language(speech)
    voice_id = "Polly.Kimberly" if lang == "en" else "Lucia"
    language_code = "en-US" if lang == "en" else "es-US"

    resp = VoiceResponse()

    # No input yet — greet and listen
    if not speech:
        gather = Gather(
            input="speech", timeout=6, speech_timeout="auto",
            action="/voice", method="POST"
        )
        greet = "Hello, this is the AI assistant from GRHUSA Properties. How can I help you today?" \
            if lang == "en" else \
            "Hola, soy la asistente virtual de GRHUSA Properties. ¿Cómo puedo ayudarte hoy?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Voicemail trigger
    if any(x in speech for x in ["leave a message", "voicemail", "dejar mensaje", "mensaje"]):
        resp.say("Sure, leave your message after the beep. We will follow up shortly.", voice=voice_id, language=language_code)
        resp.record(max_length=90, timeout=5, transcribe=True, play_beep=True, action="/voicemail")
        resp.say("Thank you. Goodbye!", voice=voice_id, language=language_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    # AI reply
    reply = generate_response(speech, lang)
    send_email("Tenant Call Summary", f"Tenant said: {speech}\n\nAI replied: {reply}")

    # Voice assistant responds
    resp.say(reply, voice=voice_id, language=language_code)

    # Start new gather right away after speaking so user can interrupt and keep flowing
    gather = Gather(
        input="speech", timeout=6, speech_timeout="auto",
        action="/voice", method="POST"
    )
    gather.say("You can speak now, I’m listening.", voice=voice_id, language=language_code)
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/voicemail", methods=["POST"])
def voicemail():
    recording_url = request.values.get("RecordingUrl", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"Voicemail received at {timestamp}.\n\nListen to the voicemail here:\n{recording_url}"
    send_email("New Tenant Voicemail", body)
    return Response("Voicemail logged", mimetype="text/plain")

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
