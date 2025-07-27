import os
import json
import queue
import threading
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Start
from elevenlabs import generate, save, set_api_key
from openai import OpenAI
from langdetect import detect
from datetime import datetime

# Initialize Flask
app = Flask(__name__)

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
set_api_key(ELEVENLABS_API_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)

# Memory to store conversation state
call_memory = {}
audio_queue = {}

# Detect language (Spanish or English)
def detect_language(text):
    try:
        return "es" if detect(text) == "es" else "en"
    except:
        return "en"

# Build system prompt for each language
def build_system_prompt(lang):
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de gestión de propiedades. "
            "Habla como una persona real, responde de forma natural y profesional. "
            "Haz solo una pregunta a la vez y escucha atentamente al usuario. "
            "Si mencionan alquiler, recomiéndales usar el portal de Buildium al final. "
            "No cuelgues hasta que digan 'adiós'."
        )
    else:
        return (
            "You are a friendly, professional AI receptionist for a property management company. "
            "Speak naturally like a real person. Only ask one question at a time. "
            "If rent is mentioned, recommend using the Buildium portal at the end. "
            "Do not hang up unless the caller says 'bye'."
        )

# Generate GPT response
def generate_response(user_input, lang, history):
    system_prompt = build_system_prompt(lang)
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": user_input}
    ]
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.5,
        max_tokens=150
    )
    return completion.choices[0].message.content.strip()

# Convert text to speech using ElevenLabs
def synthesize_voice(text, lang):
    voice_name = "Rachel" if lang == "en" else "Marina"
    audio = generate(
        text=text,
        voice=voice_name,
        model="eleven_multilingual_v2"
    )
    filename = f"static/tts_{datetime.now().timestamp()}.mp3"
    save(audio, filename)
    return filename

# Media stream endpoint (real-time audio streaming)
@app.route("/media", methods=["POST"])
def media_stream():
    data = json.loads(request.data.decode("utf-8"))
    event = data.get("event")

    call_sid = data.get("streamSid")
    if call_sid not in audio_queue:
        audio_queue[call_sid] = queue.Queue()

    if event == "media":
        # Incoming audio chunk
        audio_queue[call_sid].put(data["media"]["payload"])
    return Response("OK", status=200)

# Voice webhook (Twilio entry point)
@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get("CallSid")
    if call_sid not in call_memory:
        call_memory[call_sid] = {"lang": "en", "history": []}

    resp = VoiceResponse()
    start = Start()
    start.stream(url=f"{request.url_root}media")
    resp.append(start)

    greeting = "Hello, this is GRHUSA Properties AI Assistant. How can I help you today?"
    filename = synthesize_voice(greeting, "en")
    resp.play(filename)
    return Response(str(resp), mimetype="application/xml")

# Endpoint for handling user messages
@app.route("/process", methods=["POST"])
def process_input():
    call_sid = request.form.get("CallSid")
    user_input = request.form.get("SpeechResult", "")

    lang = detect_language(user_input)
    call_memory[call_sid]["lang"] = lang
    call_memory[call_sid]["history"].append({"role": "user", "content": user_input})

    reply = generate_response(user_input, lang, call_memory[call_sid]["history"])
    call_memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    filename = synthesize_voice(reply, lang)
    return Response(f"<Play>{filename}</Play>", mimetype="application/xml")

@app.route("/", methods=["GET"])
def health_check():
    return "✅ AI Phone Assistant Running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
