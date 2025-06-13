import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Load secrets from environment
openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = "notifications@grhusaproperties.net"
EMAIL_RECEIVER = "andrew@grhusaproperties.net"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def prompt_response(user_input, lang="en"):
    try:
        if lang == "es":
            system_msg = (
                "Eres una recepcionista de bienes raíces con voz femenina y clara. "
                "Si se menciona el alquiler, dígale al inquilino que use la aplicación Buildium. "
                "Si se menciona una fuga o problema, diga que será escalado. "
                "Solo mencione a Liz o Elsie si se dicen sus nombres."
            )
        else:
            system_msg = (
                "You are a professional AI receptionist for a real estate company. "
                "Speak fast, clearly, and friendly. "
                "If the tenant mentions rent, tell them to pay using the Buildium app. "
                "If they mention a leaking toilet, light issue, or anything broken, say it will be escalated to the team. "
                "Only mention Liz or Elsie if the caller says their name."
            )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_input}
        ]

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        return response.choices[0].message["content"]

    except Exception as e:
        return "I'm sorry, something went wrong while processing that. Please try again or leave a message."

def send_summary_email(body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = "Tenant Call Summary"
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    except:
        pass  # Fail silently

@app.route("/voice", methods=["POST"])
def handle_voice():
    speech = request.form.get("SpeechResult", "")
    lang = detect_language(speech)
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    lang_code = "en-US" if lang == "en" else "es-US"

    print(f"📞 Incoming voice call - Speech: {speech} | Lang: {lang}", flush=True)

    resp = VoiceResponse()

    if not speech:
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        gather.say(
            "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?",
            voice=voice_id, language=lang_code
        )
        resp.append(gather)
    else:
        reply = prompt_response(speech, lang)
        send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")
        resp.say(reply, voice=voice_id, language=lang_code)
        resp.hangup()

    return Response(str(resp), mimetype="application/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "AI Real Estate Receptionist is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
