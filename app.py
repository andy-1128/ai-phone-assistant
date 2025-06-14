
import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

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
        "You are a smart, fluent, professional, and human-sounding AI receptionist for a real estate company. "
        "Respond naturally, in full conversation style. If a tenant interrupts, stop and reanalyze. "
        "Always ask for the tenant's property address and apartment number when there's a concern. "
        "If they mention rent, advise them to use the Buildium portal or app. "
        "If they report maintenance issues like a broken toilet, leaking pipe, etc., ask follow-up questions and acknowledge the concern. "
        "At the end, summarize and say the issue will be sent to the team and recommend submitting a ticket on the Buildium portal. "
        "Mention Liz or Elsie only if the caller says their names, and say it will be escalated."
        if lang == "en" else
        "Eres una recepcionista de IA inteligente, profesional y natural para una empresa de bienes raíces. "
        "Responde como humana y con fluidez. Si un inquilino interrumpe, detente y vuelve a analizar. "
        "Siempre pide la dirección de la propiedad y el número de apartamento cuando se mencione un problema. "
        "Si mencionan el alquiler, recomiéndales usar el portal o app de Buildium. "
        "Si reportan problemas de mantenimiento como inodoros rotos o fugas, haz preguntas de seguimiento y reconoce el problema. "
        "Al final, resume y di que el problema será enviado al equipo y recomienda poner un ticket en Buildium. "
        "Menciona a Liz o Elsie solo si el inquilino dice sus nombres y responde que será escalado."
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
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Lupe"
    language_code = "en-US" if lang == "en" else "es-US"
    resp = VoiceResponse()

    if not speech:
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        greet = "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?" if lang == "en" else "Hola, soy la asistente de GRHUSA Properties. ¿Cómo puedo ayudarte?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Handle voicemail
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
    return "✅ AI receptionist running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
