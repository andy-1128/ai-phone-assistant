
import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
import smtplib
from email.mime.text import MIMEText
from langdetect import detect
from openai import OpenAI

app = Flask(__name__)

# Load secrets
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = "andrew@grhusaproperties.net"
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

client = OpenAI(api_key=OPENAI_API_KEY)

conversation_memory = {}

def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

def generate_response(sid, user_input, lang="en"):
    history = conversation_memory.get(sid, [])

    system_prompt = (
        "You're a smart, respectful, and responsive AI receptionist for a real estate company. "
        "You ask questions and help troubleshoot, then remember what they say, and further conversation like a human" 
        "Respond fluently like a human. Stop speaking if the user interrupts and reanalyze the latest concern. "
        "If tenant mentions a broken toilet, leaking pipe, or other issue, acknowledge it and ask: 'what is your property address and apartment number?' "
        "Once that info is received, respond empathetically and say this call will be sent to the team. "
        "Only at the end, after all problems are discussed, tell them to submit a maintenance request through the Buildium resident portal. "
        "Never repeat the same response. End the call only when the tenant says bye or hangs up. "
        "Mention Liz or Elsie only if the tenant says their names."
        if lang == "en" else
        "Eres una recepcionista inteligente y respetuosa para una empresa de bienes raíces. "
        "Habla como un humano, y si el inquilino interrumpe, escucha y responde con empatía. "
        "Si mencionan problemas, pide su dirección y número de apartamento. Al final, recuérdales usar Buildium para tickets."
    )

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_input}]
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )
    reply = response.choices[0].message.content.strip()
    conversation_memory[sid] = messages + [{"role": "assistant", "content": reply}]
    return reply

def send_email_summary(sid):
    history = conversation_memory.get(sid, [])
    text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history])
    msg = MIMEText(text)
    msg["Subject"] = "Tenant Call Summary"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

@app.route("/voice", methods=["POST"])
def voice():
    sid = request.values.get("CallSid", "default")
    speech = request.values.get("SpeechResult", "").lower()
    lang = detect_language(speech)
    voice_id = "Polly.Kimberly" if lang == "en" else "Lucia"
    language_code = "en-US" if lang == "en" else "es-US"

    resp = VoiceResponse()

    if "bye" in speech or "adios" in speech:
        resp.say("Thank you for calling. Goodbye!", voice=voice_id, language=language_code)
        send_email_summary(sid)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    if not speech:
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
        greet = "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?"             if lang == "en" else "Hola, soy la asistente de GRHUSA Properties. ¿Cómo puedo ayudarte?"
        gather.say(greet, voice=voice_id, language=language_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    reply = generate_response(sid, speech, lang)

    resp.say(reply, voice=voice_id, language=language_code)
    gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST")
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/", methods=["GET"])
def health():
    return "✅ AI Receptionist Online", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
