import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Load secrets
openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = "notifications@grhusaproperties.net"
EMAIL_RECEIVER = "andrew@grhusaproperties.net"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")


def detect_language(text):
    try:
        lang = detect(text)
        return "es" if lang == "es" else "en"
    except:
        return "en"


def prompt_response(user_input, lang="en"):
    if lang == "es":
        system_msg = (
            "Eres una asistente virtual rápida y profesional para una empresa inmobiliaria. "
            "Habla como una mujer real. Si se menciona el alquiler, indica que deben usar la aplicación Buildium. "
            "Si se menciona un problema como un inodoro con fugas o una tubería rota, reconócelo y di que se informará al equipo. "
            "Si se menciona a Liz o Elsie, responde que se enviará al equipo."
        )
    else:
        system_msg = (
            "You're a fast, helpful, fluent female AI receptionist for a real estate company. "
            "Speak confidently, like a real person. If the tenant mentions rent, tell them to use the Buildium app. "
            "If they mention something like a leaking toilet or pipe, acknowledge and say it’ll be escalated to the team. "
            "Only say 'Liz or Elsie will follow up' if those names are mentioned."
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


def send_summary_email(summary_text):
    if not SMTP_USER or not SMTP_PASS:
        print("❌ SMTP credentials are missing.")
        return

    msg = MIMEText(summary_text)
    msg["Subject"] = "Tenant Call Summary"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
            print("✅ Email sent.")
    except Exception as e:
        print(f"❌ Email send failed: {e}")


@app.route("/voice", methods=["POST"])
def handle_call():
    speech = request.form.get("SpeechResult", "")
    call_sid = request.form.get("CallSid", "")
    print(f"📞 Incoming call: {call_sid} | Speech: {speech}")

    resp = VoiceResponse()

    if not speech:
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        gather.say("Hello! This is the AI assistant from GRHUSA Properties. You can talk to me like a real person. How can I help?",
                   voice="Polly.Joanna", language="en-US")
        resp.append(gather)
        return Response(str(resp), mimetype="text/xml")

    lang = detect_language(speech)
    reply = prompt_response(speech, lang)

    # Send conversation summary via email
    send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")

    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    resp.say(reply, voice=voice_id, language="en-US" if lang == "en" else "es-US")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")


@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI assistant is running", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
