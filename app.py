import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI

app = Flask(__name__)

# ENV variables
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
        "You are a smart, fast, human-sounding female AI receptionist for a real estate company. "
        "You speak naturally and warmly. Ask what property address and apartment number if a tenant mentions a problem. "
        "If it's about rent, tell them to pay through the Buildium portal. "
        "If it's a broken toilet, leak, or maintenance issue, tell them to submit a ticket on the Buildium resident portal and that the issue will be sent to the team. "
        "Only mention Liz or Elsie if their name is mentioned, and reply 'This will be escalated to the team and someone will reach out.' "
        "Do not hang up unless the caller says 'bye' or hangs up."
        if lang == "en" else
        "Eres una recepcionista virtual inteligente y amable para una empresa inmobiliaria. "
        "Pregunta la dirección de la propiedad y el número de apartamento si mencionan un problema. "
        "Para temas de alquiler, indica que usen el portal Buildium. "
        "Para problemas de mantenimiento como fugas o inodoros, diles que llenen un ticket en Buildium y que se informará al equipo. "
        "Solo menciona a Liz o Elsie si se dicen por nombre. No cuelgues hasta que el inquilino diga 'adiós' o termine la llamada."
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
        greet = "Hello, this is the AI assistant from GRHUSA Properties. How can I help you today?" if lang == "en" else "Hola, soy la asistente virtual de GRHUSA Properties. ¿Cómo puedo ayudarte hoy?"
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Detect end of conversation
    if any(x in speech for x in ["bye", "goodbye", "hang up", "adios"]):
        resp.say("Thank you for calling GRHUSA Properties. Have a great day!", voice=voice_id, language=language_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    # Voicemail trigger
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
    body = f"📬 Voicemail received at {timestamp}:\n\nListen: {recording_url}"
    send_email("New Tenant Voicemail", body)
    return Response("OK", mimetype="text/plain")

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
