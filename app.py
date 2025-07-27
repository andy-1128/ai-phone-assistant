import os
import time
from datetime import datetime
from flask import Flask, request, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from langdetect import detect
from TTS.api import TTS  # Coqui XTTS v2 (voice cloning)

# ------------- Config -------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TURNS      = int(os.getenv("MAX_TURNS", "6"))

# point this to your uploaded ElevenLabs sample
VOICE_SAMPLE_PATH = os.getenv("VOICE_SAMPLE_PATH", "Voices/elevenlabs_sample.wav")

STATIC_DIR = os.getenv("STATIC_DIR", "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# ------------- Init -------------
app = Flask(__name__, static_folder=STATIC_DIR)
client = OpenAI(api_key=OPENAI_API_KEY)

print("Loading Coqui XTTS v2 model (this may take a while)...")
tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

# memory: { call_sid: { "lang": "en"/"es", "history": [ {role, content}, ... ] } }
memory = {}

# ------------- Helpers -------------
def safe_detect_language(text: str, default="en"):
    try:
        lang = detect(text) if text else default
        return "es" if lang.startswith("es") else "en"
    except Exception:
        return default

def system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una recepcionista de IA profesional para una empresa de administración de propiedades. "
            "Responde SIEMPRE en español, con naturalidad, ritmo pausado y tono humano. "
            "Haz solo una pregunta a la vez. Captura dirección, número de apartamento y problema de mantenimiento. "
            "Si mencionan renta, recomiéndales usar el portal de Buildium al final. No cuelgues hasta que digan 'adiós'."
        )
    return (
        "You're a smart, fluent, friendly, professional AI receptionist for a property management company. "
        "Respond ONLY in English, in a natural, slow-paced, human tone. Ask one question at a time. "
        "Capture the address, unit number, and maintenance issue. If rent is mentioned, advise using the Buildium portal at the end. "
        "Do not hang up unless they say 'bye'."
    )

def generate_response(user_input, lang, history):
    trimmed = history[-MAX_TURNS*2:] if MAX_TURNS > 0 else history
    messages = [{"role": "system", "content": system_prompt(lang)}] + trimmed + [
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
        return (
            "Lo siento, tuve un problema generando la respuesta. ¿Podrías repetir, por favor?"
            if lang == "es"
            else "Sorry, I had trouble generating a response. Could you repeat that?"
        )

def synthesize_voice(text: str, lang: str) -> str:
    """
    Clone the downloaded ElevenLabs voice with Coqui (offline) and
    write an audio wav in /static so Twilio can <Play> it.
    Returns absolute URL to the audio file, or "" on error.
    """
    ts = f"{time.time():.0f}"
    filename = f"reply_{ts}.wav"
    out_path = os.path.join(STATIC_DIR, filename)

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

    return url_for("static", filename=filename, _external=True)

# ------------- Routes -------------
@app.route("/", methods=["GET"])
def health():
    return "✅ AI receptionist (offline TTS) is running", 200

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech   = (request.values.get("SpeechResult") or "").strip()

    if call_sid not in memory:
        memory[call_sid] = {"lang": "en", "history": []}

    # detect language on first real utterance
    if speech:
        detected = safe_detect_language(speech, "en")
        if len(memory[call_sid]["history"]) == 0:  # lock only at first user turn
            memory[call_sid]["lang"] = detected

    lang = memory[call_sid]["lang"]
    resp = VoiceResponse()

    # First round: greet & gather
    if not speech:
        greet = (
            "Hola, soy la asistente de GRHUSA Properties. ¿En qué puedo ayudarte hoy?"
            if lang == "es"
            else "Hello, this is the AI assistant for GRHUSA Properties. How can I help you today?"
        )
        audio_url = synthesize_voice(greet, lang)
        if audio_url:
            resp.play(audio_url)
        else:
            resp.say(greet, language="es-ES" if lang == "es" else "en-US")

        gather = Gather(
            input="speech",
            timeout=8,
            speech_timeout="auto",
            action="/voice",
            method="POST"
        )
        resp.append(gather)
        return Response(str(resp), mimetype="application/xml")

    # user spoke
    memory[call_sid]["history"].append({"role": "user", "content": speech})
    reply = generate_response(speech, lang, memory[call_sid]["history"])
    memory[call_sid]["history"].append({"role": "assistant", "content": reply})

    audio_url = synthesize_voice(reply, lang)
    if audio_url:
        resp.play(audio_url)
    else:
        resp.say(reply, language="es-ES" if lang == "es" else "en-US")

    # keep gathering
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
