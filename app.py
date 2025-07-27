import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__)

# === ENV VARIABLES ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ELEVENLABS_VOICE_PATH = ELEVENLABS_VOICE_PATH = "Voices/ElevenLabs_2025-07-25T15_10_26_Arabella_pvc_sp100_s63_sb100_v3.mp3"
  # Your ElevenLabs voice file path

client = OpenAI(api_key=OPENAI_API_KEY)
memory = {}

# === HELPER FUNCTIONS ===
def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

def generate_response(user_input, lang="en", memory_state=None):
    system_prompt = (
        "You are a friendly, professional AI receptionist for GRHUSA Properties. "
        "Speak naturally, one question at a time, and allow interruptions. "
        "Gather property address, apartment number, and maintenance issue. "
        "If rent is mentioned, suggest using the Buildium portal at the end. "
        "Do not hang up unless the user says 'bye'."
    ) if lang == "en" else (
        "Eres una recepcionista IA amigable y profesional para GRHUSA Properties. "
        "Habla de forma natural, una pregunta a la vez, y permite interrupciones. "
        "Reúne dirección de la propiedad, número de apartamento y el problema de mantenimiento. "
        "Si se menciona renta, sugiere el portal Buildium al final. "
        "No cuelgues a menos que el usuario diga 'adiós'."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if memory_state:
        messages.extend(memory_state)
    messages.append({"role": "user", "content": user_input})

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.7,
        max_tokens=200
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
        print(f"Email sending failed: {e}")

# === VOICE HANDLER ===
@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech = request.values.get("SpeechResult", "").strip()
    lang = detect_language(speech) if speech else "en"
    resp = VoiceResponse()

    if call_sid not in memory:
        memory[call_sid] = []

    if not speech:  # Initial greeting
        gather = Gather(
            input="speech",
            timeout=8,
            speech_timeout="auto",
            barge_in=True,
            action="/voice",
            method="POST"
        )
        greet = "Hello, this is GRHUSA Properties AI assistant. How can I help you?" if lang == "en" \
            else "Hola, soy la asistente virtual de GRHUSA Properties. ¿En qué puedo ayudarte?"
        gather.say(greet, voice="Polly.Joanna", language="en-US")
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # Process user speech
    memory[call_sid].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, memory[call_sid])
    memory[call_sid].append({"role": "assistant", "content": reply})

    # Email summary
    summary = f"""
    📞 Call Summary:
    User said: {speech}
    AI replied: {reply}
    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    send_email("📬 New AI Call Summary – GRHUSA", summary)

    # Play ElevenLabs voice if available
    if os.path.exists(ELEVENLABS_VOICE_PATH):
        resp.play(ELEVENLABS_VOICE_PATH)
    else:
        resp.say(reply, voice="Polly.Joanna", language="en-US")

    # Continue listening
    gather = Gather(
        input="speech",
        timeout=8,
        speech_timeout="auto",
        barge_in=True,
        action="/voice",
        method="POST"
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI receptionist with ElevenLabs voice is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
