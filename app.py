import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get("CallSid")
    speech = request.form.get("SpeechResult", "")
    stage = request.form.get("SpeechResult") is not None

    print(f"📞 callSid={call_sid} stage={stage} speech='{speech}'", flush=True)

    resp = VoiceResponse()

    if not stage:
        # Step 1: Intro and listen
        resp.say(
            "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?",
            voice="Polly.Joanna", language="en-US"
        )
        resp.listen(timeout=6, speech_timeout="auto")
    else:
        # Step 2: User replied -> analyze
        lang = detect_language(speech)
        reply = prompt_response(speech, lang)
        send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")

        resp.say(reply, voice="Polly.Joanna" if lang == "en" else "Polly.Mia",
                 language="en-US" if lang == "en" else "es-US")
        # End call
        resp.hangup()

    return Response(str(resp), mimetype="application/xml")

# Load secrets
openai.api_key = os.getenv("OPENAI_API_KEY")
twilio_sid = os.getenv("TWILIO_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
@app.route("/voice", methods=["POST"])
def voice():
    print("🛎️ /voice hit!", flush=True)
    # ...
# Email for summary
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
    if lang == "es":
        system_msg = (
            "Eres una recepcionista virtual para una empresa inmobiliaria."
            " Hablas rápido y claramente como una persona real. "
            "Si el inquilino menciona alquiler, dile que use la aplicación de Buildium. "
            "Si menciona algo roto como el baño, reconócelo y diga que será escalado. "
            "Si mencionan a Liz o Elsie, diga que será escalado al equipo."
        )
    else:
        system_msg = (
            "You're a fast, fluent AI receptionist for a real estate company. "
            "Greet clearly and confidently. "
            "If a tenant mentions rent, tell them to pay via Buildium. "
            "If they mention issues like leaking toilets, acknowledge and escalate. "
            "Only mention Liz or Elsie if the caller says their name."
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

def send_summary_email(text):
    msg = MIMEText(text)
    msg["Subject"] = "Tenant Call Summary"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

@app.route("/voice", methods=["POST"])
def voice():
    speech = request.form.get("SpeechResult", "") or request.values.get("SpeechResult", "")
    lang = detect_language(speech)
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"

    # Log and process
    reply = prompt_response(speech, lang)
    send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")

    resp = VoiceResponse()
    intro = "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?" if lang == "en" else "Hola, soy la asistente virtual de GRHUSA Properties. ¿Cómo puedo ayudarte?"
    resp.say(intro, voice=voice_id, language="en-US" if lang == "en" else "es-US")
    resp.pause(length=1)
    resp.say(reply, voice=voice_id, language="en-US" if lang == "en" else "es-US")
    resp.listen(timeout=6, speech_timeout="auto")

    return Response(str(resp), mimetype="text/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "AI assistant is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
