import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Load secrets from environment
openai.api_key = os.getenv("OPENAI_API_KEY")
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")

# Static config
EMAIL_SENDER = "notifications@grhusaproperties.net"
EMAIL_RECEIVER = "andrew@grhusaproperties.net"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def prompt_response(user_input, lang="en"):
    if lang == "es":
        system_msg = (
            "Eres una recepcionista de bienes raíces que habla rápido, claro y con confianza. "
            "Si el inquilino menciona el alquiler, dile que use la aplicación Buildium. "
            "Si menciona problemas como una fuga o inodoro roto, reconócelo y di que será escalado. "
            "Si mencionan a Liz o Elsie, di que se notificará al equipo."
        )
    else:
        system_msg = (
            "You're a fast, helpful, fluent AI receptionist for a real estate company. "
            "Greet warmly and confidently like a real person. "
            "If a tenant mentions rent, tell them to pay using the Buildium portal. "
            "If they mention issues like leaking toilets, broken lights, or any issue, acknowledge it, ask for more detail if needed, and say the team will follow up. "
            "Only mention Liz or Elsie if they are mentioned, then say 'this will be escalated to the team and someone will reach out.'"
        )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_input}
    ]

    completion = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages
    )
    return completion.choices[0].message["content"]

def send_summary_email(body):
    if not SMTP_USER or not SMTP_PASS:
        print("❌ SMTP credentials missing! Skipping email.")
        return

    msg = MIMEText(body)
    msg["Subject"] = "Tenant Call Summary"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
            print("✅ Email summary sent.")
    except Exception as e:
        print(f"❌ Email failed: {e}")

@app.route("/voice", methods=["POST"])
def voice():
    speech = request.form.get("SpeechResult", "") or request.values.get("SpeechResult", "")
    print(f"🗣️ Incoming voice call - Speech: {speech}")

    lang = detect_language(speech)
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    lang_code = "en-US" if lang == "en" else "es-US"

    try:
        reply = prompt_response(speech, lang)
        send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")

        resp = VoiceResponse()
        resp.say(reply, voice=voice_id, language=lang_code)
        return Response(str(resp), mimetype="application/xml")
    except Exception as e:
        print(f"❌ Application error: {e}")
        return Response("<Response><Say>Sorry, there was an error handling your call.</Say></Response>", mimetype="application/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "AI assistant is live", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
