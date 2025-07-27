import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from twilio.rest import Client

app = Flask(__name__)

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

client = OpenAI(api_key=OPENAI_API_KEY)
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

memory = {}

# -----------------
# Helper functions
# -----------------
def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

def generate_response(user_input, lang="en", memory_state=None):
    system_prompt = (
        "You're a smart, fluent, friendly, professional AI receptionist for a property management company. "
        "Respond in a natural, slow-paced, human tone. Only ask 1 question at a time. "
        "Stop talking if the user interrupts, and reanalyze their new message. "
        "Store key info: property address, apartment number, maintenance issue. "
        "If rent is mentioned, tell them to use the Buildium portal at the end. "
        "Summarize only at the end of the call, not now. Do not hang up unless they say 'bye'."
    ) if lang == "en" else (
        "Eres una recepcionista de IA para una empresa de bienes raíces. Responde con voz natural y profesional, "
        "como si fueras humana. Haz solo una pregunta a la vez. "
        "Detente si el inquilino interrumpe y vuelve a escuchar. "
        "Guarda información clave como dirección y número de apartamento. "
        "Si mencionan alquiler, recomiéndales usar el portal de Buildium al final. "
        "No cuelgues a menos que digan 'adiós'."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if memory_state:
        messages.extend(memory_state)
    messages.append({"role": "user", "content": user_input})

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.6,
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

# -----------------
# Routes
# -----------------
@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech = request.values.get("SpeechResult", "").strip()
    lang = detect_language(speech) if speech else "en"
    voice_id = "Polly.Joanna" if lang == "en" else "Polly.Lupe"
    language_code = "en-US" if lang == "en" else "es-US"
    resp = VoiceResponse()

    if call_sid not in memory:
        memory[call_sid] = []

    if not speech:
        gather = Gather(input="speech", timeout=10, speech_timeout="auto",
                        barge_in=True, action="/voice", method="POST")
        greet = "Hello, this is the assistant from GRHUSA Properties. How can I help you today?" \
            if lang == "en" else "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    memory[call_sid].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, memory[call_sid])
    memory[call_sid].append({"role": "assistant", "content": reply})

    summary = f"""
📞 New Tenant Call Summary
🗣️ Tenant said: {speech}
🤖 AI replied: {reply}
🕒 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    send_email("📬 Tenant Call Summary – GRHUSA", summary)

    resp.say(reply, voice=voice_id, language=language_code)
    gather = Gather(input="speech", timeout=10, speech_timeout="auto",
                    barge_in=True, action="/voice", method="POST")
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/outbound", methods=["POST"])
def outbound():
    number = request.values.get("number")
    if not number:
        return {"error": "Number is required"}, 400

    twilio_client.calls.create(
        to=number,
        from_=TWILIO_NUMBER,
        url="https://{your-render-url}/voice"
    )
    return {"status": f"Call initiated to {number}"}, 200

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist running", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
