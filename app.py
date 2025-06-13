import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# --- Load secrets ---
openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = "notifications@grhusaproperties.net"
EMAIL_RECEIVER = "andrew@grhusaproperties.net"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")

# --- Language Detection ---
def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

# --- AI Prompt Response ---
def prompt_response(user_input, lang="en"):
    if lang == "es":
        system_msg = (
            "Eres una recepcionista virtual para una empresa inmobiliaria. "
            "Habla rápido y claramente como una persona real. "
            "Si el inquilino menciona alquiler, dile que use la aplicación de Buildium. "
            "Si mencionan algo roto como el baño, reconócelo y di que será escalado. "
            "Solo menciona a Liz o Elsie si dicen su nombre, entonces diga que será escalado al equipo."
        )
    else:
        system_msg = (
            "You are a fast, fluent AI receptionist for a real estate company. "
            "Speak clearly and confidently like a real person. "
            "If a tenant mentions rent, tell them to pay using the Buildium portal. "
            "If they mention issues like leaking toilet, broken light, or any issue, acknowledge it, ask for more detail if needed, and say the team will follow up. "
            "Only mention Liz or Elsie if they are mentioned, then say 'This will be escalated to the team and someone will reach out.'"
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

# --- Send Summary Email ---
def send_summary_email(text):
    msg = MIMEText(text)
    msg["Subject"] = "Tenant Call Summary"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

# --- Voice Handler ---
@app.route("/voice", methods=["POST"])
def handle_voice():
    speech = request.form.get("SpeechResult", "") or request.values.get("SpeechResult", "")
    lang = detect_language(speech)
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    lang_code = "en-US" if lang == "en" else "es-US"

    print(f"📞 Incoming voice call - Speech: {speech} | Lang: {lang}")

    resp = VoiceResponse()

    if not speech:
        # 🟢 Initial greeting and listen
        greeting = "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?" \
            if lang == "en" else \
            "Hola, soy la asistente virtual de GRHUSA Properties. Puedes hablar conmigo como con una persona real. ¿Cómo puedo ayudarte?"

        gather = resp.gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        gather.say(greeting, voice=voice_id, language=lang_code)

    else:
        # 🟢 AI reply
        reply = prompt_response(speech, lang)
        send_summary_email(f"Tenant said: {speech}\n\nAI replied: {reply}")
        resp.say(reply, voice=voice_id, language=lang_code)
        resp.hangup()

    return Response(str(resp), mimetype="application/xml")

# --- Health Check ---
@app.route("/", methods=["GET"])
def health_check():
    return "AI assistant is running", 200

# --- Run Flask Server ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
