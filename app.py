import os
import logging
from datetime import datetime
from flask import Flask, request, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
import requests
from msal import ConfidentialClientApplication

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS = int(os.getenv("MAX_TURNS", "6"))

EMAIL_RECIPIENTS = [
    "manager1@outlook.com",
    "manager2@outlook.com",
    "manager3@outlook.com",
    "manager4@outlook.com"
]

MS365_CLIENT_ID = os.getenv("MS365_CLIENT_ID")
MS365_CLIENT_SECRET = os.getenv("MS365_CLIENT_SECRET")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
ELEVENLABS_GREETING_FILE = os.getenv("ELEVENLABS_GREETING_FILE")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-phone")

app = Flask(__name__, static_folder="static")
client = OpenAI(api_key=OPENAI_API_KEY)
memory = {}

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def get_access_token():
    authority = "https://login.microsoftonline.com/common"
    app = ConfidentialClientApplication(
        MS365_CLIENT_ID,
        authority=authority,
        client_credential=MS365_CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        return result["access_token"]
    raise Exception(f"Token error: {result}")

def send_email(subject, body):
    if not body.strip():
        body = "⚠️ Empty conversation. No speech recorded."

    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body
                },
                "toRecipients": [
                    {"emailAddress": {"address": addr}} for addr in EMAIL_RECIPIENTS
                ]
            },
            "saveToSentItems": "true"
        }
        response = requests.post(
            "https://graph.microsoft.com/v1.0/users/me/sendMail",
            headers=headers,
            json=email_data
        )
        if response.status_code >= 300:
            raise Exception(f"Graph email failed: {response.status_code} {response.text}")
    except Exception as e:
        log.error(f"EMAIL FAILED: {e}")

def post_to_n8n(payload):
    if not N8N_WEBHOOK_URL:
        return
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        log.exception("POST to n8n failed")

def safe_detect_language(text, default="en"):
    try:
        return "es" if detect(text).startswith("es") else "en"
    except:
        return default

def greeting_for(lang):
    return "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?" if lang == "es" else "Hello, this is the AI assistant for GRHUSA Properties. How can I help you today?"

def twilio_voice_for(lang):
    return "Polly.Conchita" if lang == "es" else "Polly.Joanna"

def twilio_language_code(lang):
    return "es-ES" if lang == "es" else "en-US"

def system_prompt(lang):
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde SIEMPRE en español. Recolecta dirección de propiedad, número de apartamento, problema de mantenimiento y contacto. "
            "Di que usen el portal de Buildium si mencionan renta. No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You are a professional AI receptionist for a property management company. Respond only in English. "
        "Collect address, unit number, issue, and contact info. If rent is mentioned, refer them to the Buildium portal. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input, lang, history):
    trimmed = history[-MAX_TURNS*2:] if MAX_TURNS > 0 else history
    messages = [{"role": "system", "content": system_prompt(lang)}] + trimmed + [{"role": "user", "content": user_input}]
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=220
        )
        return response.choices[0].message.content.strip()
    except:
        log.exception("OpenAI error")
        return "Lo siento, ¿puedes repetir?" if lang == "es" else "Sorry, can you say that again?"

def final_email_and_n8n(call_sid):
    data = memory.get(call_sid, {})
    if not data:
        log.warning(f"No memory found for callSid: {call_sid}")
        return

    lang = data.get("lang", "en")
    history = data.get("history", [])
    if not history:
        log.warning(f"No conversation history found for callSid: {call_sid}")
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = []
    for m in history:
        role = "TENANT" if m["role"] == "user" else "AI"
        lines.append(f"{role}: {m['content']}")

    body = f"""
📞 AI Tenant Call Summary  
Time: {now}  
Language: {lang.upper()}  
Call SID: {call_sid}

{'-'*40}
{chr(10).join(lines)}
"""

    log.info(f"Sending final email + posting to n8n for {call_sid}")
    send_email("📬 AI Receptionist – Final Call Summary", body)
    post_to_n8n({
        "callSid": call_sid,
        "timestamp": now,
        "lang": lang,
        "history": history,
        "summary": body
    })

# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "✅ AI receptionist running", 200

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech = (request.values.get("SpeechResult") or "").strip()
    if not call_sid:
        return Response("<Response></Response>", mimetype="application/xml")

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": [], "done": False}

    data = memory[call_sid]
    if speech and not data["history"]:
        data["lang"] = safe_detect_language(speech)

    lang = data["lang"]
    voice_name = twilio_voice_for(lang)
    lang_code = twilio_language_code(lang)

    resp = VoiceResponse()

    if data.get("done"):
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    if not speech:
        if ELEVENLABS_GREETING_FILE:
            try:
                greeting_url = url_for("static", filename=ELEVENLABS_GREETING_FILE, _external=True)
                resp.play(greeting_url)
            except:
                log.warning("Greeting file not found.")
        gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST", barge_in=True)
        gather.say(greeting_for(lang), voice=voice_name, language=lang_code)
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    if any(x in speech.lower() for x in ["bye", "goodbye", "thanks", "adios", "gracias"]):
        data["history"].append({"role": "user", "content": speech})
        reply = "Gracias por llamar. ¡Hasta luego!" if lang == "es" else "Thanks for calling. Goodbye!"
        data["history"].append({"role": "assistant", "content": reply})
        data["done"] = True
        final_email_and_n8n(call_sid)
        resp.say(reply, voice=voice_name, language=lang_code)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    data["history"].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, data["history"])
    data["history"].append({"role": "assistant", "content": reply})

    resp.say(reply, voice=voice_name, language=lang_code)
    gather = Gather(input="speech", timeout=6, speech_timeout="auto", action="/voice", method="POST", barge_in=True)
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")

@app.route("/status", methods=["POST"])
def status():
    call_sid = request.values.get("CallSid")
    call_status = request.values.get("CallStatus")
    log.info(f"Status callback {call_sid=} {call_status=}")
    if call_status == "completed" and call_sid in memory and not memory[call_sid].get("done"):
        final_email_and_n8n(call_sid)
        memory[call_sid]["done"] = True
    return ("", 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
