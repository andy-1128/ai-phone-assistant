import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import openai
import smtplib
from email.mime.text import MIMEText
from langdetect import detect

app = Flask(__name__)

# Load credentials from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

openai.api_key = OPENAI_API_KEY

def detect_language(text):
    try:
        lang = detect(text)
        return "es" if lang == "es" else "en"
    except:
        return "en"

def generate_response(user_input, lang="en"):
    system_prompt_en = (
        "You are a fast, helpful, fluent female AI receptionist for a real estate company. "
        "Speak clearly and confidently, like a real person. "
        "If a tenant mentions rent, tell them to pay using the Buildium portal. "
        "If a tenant mentions a leaking toilet, broken light, or any issue, acknowledge it, ask for more detail if needed, and say the team will follow up. "
        "Only mention Liz or Elsie if they are mentioned, then say 'this will be escalated to the team and someone will reach out.'"
    )

    system_prompt_es = (
        "Eres una recepcionista virtual rápida, servicial y femenina para una empresa inmobiliaria. "
        "Habla con fluidez y confianza como una persona real. "
        "Si un inquilino menciona el alquiler, dile que paguen usando la aplicación o portal de Buildium. "
        "Si menciona problemas como fuga o inodoro roto, reconócelo, pide escalado si es necesario y di que el equipo dará seguimiento. "
        "Solo menciona a 'Liz' o 'Elsie' si se mencionan, luego responde que será escalado al equipo."
    )

    prompt = system_prompt_es if lang == "es" else system_prompt_en

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_input}
    ]

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages
    )
    return response.choices[0].message["content"]

def send_email_summary(speech, reply):
    try:
        body = f"Tenant said: {speech}\n\nAI replied: {reply}"
        msg = MIMEText(body)
        msg["Subject"] = "Tenant Call Summary"
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
    speech = request.values.get("SpeechResult", "")
    lang = detect_language(speech)
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    language_code = "en-US" if lang == "en" else "es-US"

    resp = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech",
            timeout=6,
            speech_timeout="auto",
            action="/voice",
            method="POST"
        )
        gather.say("Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help you?",
                   voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Generate reply and respond
    reply = generate_response(speech, lang)
    send_email_summary(speech, reply)

    resp.say(reply, voice=voice_id, language=language_code)
    resp.pause(length=1)
    resp.say("Is there anything else I can help you with?", voice=voice_id, language=language_code)
    gather = Gather(
        input="speech",
        timeout=6,
        speech_timeout="auto",
        action="/voice",
        method="POST"
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/", methods=["GET"])
def health():
    return "AI assistant running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
