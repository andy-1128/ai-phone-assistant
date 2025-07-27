import os
import time
from datetime import datetime
from flask import Flask, request, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
from TTS.api import TTS  # Coqui TTS

# -----------------------
# Config
# -----------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS      = int(os.getenv("MAX_TURNS", "6"))  # how many user/assistant turns to keep

# Paths
VOICE_SAMPLE_PATH = os.getenv("VOICE_SAMPLE_PATH", "voices/elevenlabs_sample.wav")
STATIC_DIR        = os.getenv("STATIC_DIR", "static")

# Make sure dirs exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.dirname(VOICE_SAMPLE_PATH), exist_ok=True)

# -----------------------
# Init
# -----------------------
app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Coqui TTS model once (slow to load)
# xtts_v2 supports multilingual + voice cloning
print("Loading Coqui TTS model (xtts_v2). This may take a while...")
tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

# Simple in-memory store: {call_sid: {"lang": "en"/"es", "history": []}}
memory = {}

# -----------------------
# Helpers
# -----------------------
def safe_detect_language(text: str, default="en"):
    try:
        lang = detect(text) if text else default
        return "es" if lang.startswith("es") else "en"
    except Exception:
        return default

def build_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde en español, con naturalidad, ritmo pausado y tono humano. Haz solo una pregunta a la vez. "
            "Detente si el usuario te interrumpe. Captura datos clave: dirección, número de apartamento, problema de mantenimiento. "
            "Si mencionan renta, recomiéndales usar el portal de Buildium al final. No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You're a smart, fluent, friendly, professional AI receptionist for a property management company. "
        "Respond in a natural, slow-paced, human tone. Only ask one question at a time. "
        "Stop talking if the caller interrupts and re-evaluate. "
        "Capture key info: property address, unit number, maintenance issue. "
        "If rent is mentioned, advise using the Buildium portal at the end. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input, lang, history):
    system_prompt = build_system_prompt(lang)
    trimmed = history[-MAX_TURNS*2:] if MAX_TURNS > 0 else history
    messages = [{"role": "system", "content": system_prompt}] + trimmed + [
        {"role": "user", "content": user_input}
    ]
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=200
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI error:", e)
        return "Sorry, I had trouble generating a response. Could you repeat that?" if lang == "en" \
               else "Lo siento, tuve un problema generando la respuesta. ¿Podrías repetir por favor?"

def synthesize_voice(text: str, lang: str) -> str:
    """
    Create a wav file with Coqui TTS using your downloaded ElevenLabs sample as the cloned speaker.
    Returns the absolute URL that Twilio can play.
    """
    ts = f"{time.time():.0f}"
    out_name = f"resp_{ts}.wav"
    out_path = os.path.join(STATIC_DIR, out_name)

    # Coqui xtts_v2 supports language code explicitly
    lang_code = "es" if lang == "es" else "en"

    try:
        tts_model.tts_to_file(
            text=text,
            speaker_wav=VOICE_SAMPLE_PATH,
            language=lang_code,
            file_path=out_path
        )
    except Exception as e:
        print("Coqui TTS error:", e)
        return ""

    # Build absolute URL Twilio can fetch
    return url_for("static", filename=out_name, _external=True)

# -----------------------
# Routes
# -----------------------
@app.route("/", methods=["GET"])
def health():
    return "✅ AI receptionist (with offline TTS) running", 200

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech   = (request.values.get("SpeechResult") or "").strip()

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": []}

    # Detect and lock language on first real user turn
    if speech:
        detected = safe_detect_language(speech, "en")
        if len(memory[call_sid]["history"]) == 0:
            memory[call_sid]["lang"] = detected

    lang = memory[call_sid]["lang"]
    resp = VoiceResponse()

    # First turn: greet & gather
    if not speech:
        greet = "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?" if lang == "es" \
            else "Hello, this is the AI assistant for GRHUSA Properties. How can I help you today?"

        # TTS greeting
        audio_url = synthesize_voice(greet, lang)
        if audio_url:
            resp.play(audio_url)
        else:
            # fallback
            resp.say(greet, language="es-ES" if lang == "es" else "en-US")

        gather = Gather(
            input="speech",
            timeout=8,
            speech_timeout="auto",
            action="/voice",   # loop back into same endpoint
            method="POST"
        )
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # user spoke - add to history
    memory[call_sid]["history"].append({"role": "user", "content": speech})

    # ask OpenAI
    reply = generate_response(speech, lang, memory[call_sid]["history"])
    memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    # TTS reply
    audio_url = synthesize_voice(reply, lang)
    if audio_url:
        resp.play(audio_url)
    else:
        resp.say(reply, language="es-ES" if lang == "es" else "en-US")

    # keep the conversation going
    gather = Gather(
        input="speech",
        timeout=8,
        speech_timeout="auto",
        action="/voice",
        method="POST"
    )
    resp.append(gather)
    return Response(str(resp), mimetype="application/xml")


if __name__ == "__main__":
    # Local run
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
