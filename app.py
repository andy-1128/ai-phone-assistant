import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
from openai import OpenAI

openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
conversations = {}

def generate_ai_response(message):
    prompt = (
        "You are an AI receptionist named 'GRHUSA Assistant' for a real estate company."
        " Speak in a friendly, fast, and clear FEMALE voice."
        " You can handle tenant complaints, rent payment instructions, and escalate requests to Liz or Elsie."
        " You automatically detect if the caller is speaking Spanish and reply fluently in Spanish if so."
        " Be helpful and keep responses under 80 words.\n\n"
        f"User: {message}\nAI:"
    )

    completion = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": prompt}]
    )

    return completion.choices[0].message.content.strip()

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.values.get("CallSid")
    speech_result = request.values.get("SpeechResult", "").strip()
    conversations.setdefault(call_sid, []).append(speech_result)

    lang = detect(speech_result) if speech_result else "en"
    vr = VoiceResponse()

    # Initial greeting
    if len(conversations[call_sid]) == 1:
        greeting = ("Hola, soy la asistente virtual de GRHUSA Properties. "
                    "Puedes hablarme como a un humano. ¿Cómo puedo ayudarte?")
        english = ("Hello, this is the AI assistant from GRHUSA Properties. "
                   "You can speak to me like a human. How can I help?")
        vr.say(greeting if lang == "es" else english, voice="Polly.Joanna", language="es-ES" if lang == "es" else "en-US")
        vr.gather(input="speech", action="/voice", timeout=5)
        return Response(str(vr), mimetype="application/xml")

    # AI handles conversation
    response_text = generate_ai_response(speech_result)

    # Special keywords and routing
    if any(word in speech_result.lower() for word in ["toilet", "leak", "broken", "pipe", "water"]):
        response_text += "\nWe’ve logged your maintenance issue and will escalate it to Liz or Elsie immediately."
    if "rent" in speech_result.lower():
        response_text += "\nPlease pay through the Buildium tenant portal app—it’s fast and secure!"
    if any(name in speech_result.lower() for name in ["liz", "elsie"]):
        response_text += "\nI will forward this call to Liz or Elsie. They will reach out via phone or email."

    vr.say(response_text, voice="Polly.Joanna", language="es-ES" if lang == "es" else "en-US")
    vr.gather(input="speech", action="/voice", timeout=5)
    return Response(str(vr), mimetype="application/xml")

@app.route("/")
def index():
    return "GRHUSA Property AI Assistant is live."

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
