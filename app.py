import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from langdetect import detect
import openai
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Load environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_FROM")
EMAIL_RECEIVER = os.getenv("EMAIL_TO")
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_FROM")
SMTP_PASS = os.getenv("EMAIL_PASS")  # Optional override

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def prompt_response(user_input, lang="en"):
    if lang == "es":
        system_msg = (
            "Eres una recepcionista de bienes raíces. "
            "Si mencionan el alquiler, diles que usen la aplicación Buildium. "
            "Si mencionan problemas como fugas o inodoros rotos, reconócelo y explica que se escalará. "
            "Solo menciona a Liz o Elsie si se mencionan por su nombre."
        )
    else:
        system_msg = (
            "You are a helpful, fast-talking female AI receptionist for a real estate company. "
            "If someone mentions rent, recommend Buildium app or portal. "
            "If they mention issues like broken toilets or leaks, acknowledge and escalate. "
            "Only mention Liz or Elsie if the caller says their name."
        )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_input}
    ]

    try:
        completion = openai.ChatCompletion.create(model="gpt-4", messages=messages)
        return completion.choices[0].message["content"]
    except Exception as e:
        return "Sorry, there was a problem generating a response. We'll follow up with you shortly."

def send_summary_email(summary):
    msg = MIMEText(summary)
    msg["Subject"] = "Tenant Call Summary"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS or "")
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER.split(",")[0], msg.as_string())
            print("✅ Email sent successfully")
    except Exception as e:
        print(f"❌ Email failed: {e}")

@app.route("/voice", methods=["POST"])
def handle_voice():
    speech = request.form.get("SpeechResult", "") or ""
    call_sid = request.form.get("CallSid", "")
    print(f"📞 Call from SID {call_sid} - Speech: {speech}")

    resp = VoiceResponse()

    if not speech:
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        gather.say("Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?",
                   voice="Polly.Joanna", language="en-US")
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    lang = detect_language(speech)
    reply = prompt_response(speech, lang)
    send_summary_email(f"Caller said: {speech}\n\nAI replied: {reply}")

    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Mia"
    lang_code = "en-US" if lang == "en" else "es-US"

    resp.say(reply, voice=voice_id, language=lang_code)
    resp.pause(length=1)
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "AI assistant is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
