import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "temp_secret")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

client = OpenAI(api_key=OPENAI_API_KEY)

memory = {}

def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

def generate_response(user_input, lang="en", memory_state=None):
    system_prompt = (
        "You are a smart, fluent, human-like AI receptionist for a real estate company. "
        "Speak slowly, warmly, and clearly. Only ask one question at a time. "
        "If interrupted, stop and listen again. Store address and issues. "
        "Understand words like rent, apartment, leaking, and recommend Buildium at the end."
    ) if lang == "en" else (
        "Eres una recepcionista de IA profesional, cálida y fluida en español. "
        "Habla con claridad y voz natural. Haz solo una pregunta a la vez. "
        "Detente si el inquilino interrumpe. Comprende palabras como baño, fuga, renta, apartamento, inodoro. "
        "Sugiere Buildium si se habla de alquiler. No cuelgues a menos que digan adiós."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if memory_state:
        messages.extend(memory_state)
    messages.append({"role": "user", "content": user_input})

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.5,
        max_tokens=150
    )
    return completion.choices[0].message.content.strip()

def send_email(subject, body):
    try:
        recipients = [
            "andrew@grhusaproperties.net",
            "leasing@grhusaproperties.net",
            "office@grhusaproperties.net"
        ]
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech = request.values.get("SpeechResult", "").strip()

    # Store language on first interaction only
    if call_sid not in memory:
        detected_lang = detect_language(speech)
        memory[call_sid] = {
            "lang": detected_lang,
            "history": []
        }

    lang = memory[call_sid]["lang"]
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Lupe"
    language_code = "en-US" if lang == "en" else "es-US"
    resp = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech",
            timeout=10,
            speech_timeout="auto",
            barge_in=True,
            action="/voice",
            method="POST"
        )
        greeting = "Hello, this is the assistant from GRHUSA Properties. How can I help you today?" if lang == "en" else "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
        gather.say(greeting, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    if any(x in speech.lower() for x in ["leave a message", "voicemail", "dejar mensaje", "mensaje"]):
        resp.say("Sure, leave your message after the beep. We’ll follow up soon.", voice=voice_id, language=language_code)
        resp.record(max_length=60, timeout=5, transcribe=True, play_beep=True, action="/voicemail")
        return Response(str(resp), mimetype="application/xml")

    # Store conversation and generate reply
    memory[call_sid]["history"].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, memory[call_sid]["history"])
    memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    # Email summary
    summary = f"""
📞 New Tenant Call Summary

🗣️ Tenant said:
{speech}

🤖 AI replied:
{reply}

🕒 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    send_email("📬 Tenant Call Summary – GRHUSA", summary)

    resp.say(reply, voice=voice_id, language=language_code)

    # Re-open gather
    gather = Gather(
        input="speech",
        timeout=10,
        speech_timeout="auto",
        barge_in=True,
        action="/voice",
        method="POST"
    )
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
