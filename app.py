import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Twilio & OpenAI keys
openai.api_key = os.getenv("OPENAI_API_KEY")
twilio_sid = os.getenv("TWILIO_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(twilio_sid, twilio_token)

# Email Config
EMAIL_SENDER = "no-reply@grhusaproperties.net"
EMAIL_RECEIVER = "andrew@grhusaproperties.net"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")

conversations = {}

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def generate_response(prompt, lang="en"):
    pre_prompt = (
        "You're a fast, helpful, fluent female AI receptionist for a real estate company. "
        "Speak warmly and confidently, like a real person. "
        "If a tenant mentions rent, tell them to pay using the Buildium portal. "
        "If a tenant mentions a leaking toilet, broken light, or any issue, acknowledge it, ask for more detail if needed, and say the team will follow up. "
        "Only mention 'Liz' or 'Elsie' if they are mentioned, then say 'This will be escalated to the team and someone will reach out.'"
    )
    if lang == "es":
        pre_prompt = (
            "Eres una recepcionista virtual rápida, servicial y femenina para una empresa inmobiliaria. "
            "Habla con fluidez y confianza como una persona real. "
            "Si un inquilino menciona el alquiler, diles que paguen usando la aplicación o portal de Buildium. "
            "Si mencionan problemas como una fuga o inodoro roto, reconócelo, pide detalles si es necesario y di que el equipo dará seguimiento. "
            "Solo menciona a 'Liz' o 'Elsie' si se mencionan, luego responde que será escalado al equipo."
        )
    messages = [
        {"role": "system", "content": pre_prompt},
        {"role": "user", "content": prompt}
    ]
    res = openai.ChatCompletion.create(model="gpt-4", messages=messages)
    return res.choices[0].message.content.strip()

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form["CallSid"]
    speech = request.form.get("SpeechResult", "")
    lang = detect_language(speech)
    voice = "Polly.Maria" if lang == "es" else "Polly.Joanna"

    conversations.setdefault(call_sid, "")
    conversations[call_sid] += f"User: {speech}\n"

    if not speech:
        return Response(str(VoiceResponse().say("Hello, this is the AI assistant from GRHUSA Properties. You can speak to me like a person. How can I help?", voice="Polly.Joanna", language="en-US")), mimetype="application/xml")

    reply = generate_response(speech, lang)
    conversations[call_sid] += f"Assistant: {reply}\n"

    response = VoiceResponse()
    response.say(reply, voice=voice, language="es-US" if lang == "es" else "en-US")
    response.listen()
    return Response(str(response), mimetype="application/xml")

@app.route("/end", methods=["POST"])
def end():
    call_sid = request.form["CallSid"]
    summary_prompt = "Summarize this tenant conversation and highlight actions needed: " + conversations.get(call_sid, "")
    summary = generate_response(summary_prompt)
    send_email("Tenant Call Summary", summary)

    response = VoiceResponse()
    response.say("Thank you for calling. We'll follow up shortly.", voice="Polly.Joanna")
    response.hangup()
    return Response(str(response), mimetype="application/xml")

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
