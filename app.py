import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
import openai

app = Flask(__name__)

# Load keys securely from environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")

conversations = {}

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def generate_ai_response(prompt, lang):
    system_prompt = {
        "en": "You are a helpful property management assistant for GRHUSA Properties. Speak in clear, friendly American English.",
        "es": "Eres un asistente útil de administración de propiedades para GRHUSA Properties. Habla en español claro y profesional."
    }
    full_prompt = f"{system_prompt.get(lang, system_prompt['en'])} The user said: {prompt}"
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": full_prompt}
        ]
    )
    return completion.choices[0].message['content']

@app.route("/voice", methods=['POST'])
def voice():
    call_sid = request.form['CallSid']
    speech_result = request.form.get("SpeechResult", "")

    lang = detect_language(speech_result) if speech_result else "en"
    voice = "es-US-SofiaNeural" if lang == "es" else "en-US-JennyNeural"

    response = VoiceResponse()

    if call_sid not in conversations:
        conversations[call_sid] = []
        greeting = "Hola, soy el asistente virtual de GRHUSA Properties. Puedes hablarme como si fuera una persona, ¿cómo puedo ayudarte?" if lang == "es" else "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help you today?"
        response.say(greeting, voice=voice)
        response.listen()
        return Response(str(response), mimetype="application/xml")

    conversations[call_sid].append(speech_result.lower())

    if any(name in speech_result.lower() for name in ["liz", "elsie", "lys", "lease lady", "office lady"]):
        reply = "I'll forward this message to Liz or Elsie and someone from our team will follow up by phone or email."
    elif "toilet" in speech_result.lower() or "leak" in speech_result.lower() or "pipe" in speech_result.lower():
        reply = "I’m sorry to hear about the leak. We’ll forward this to maintenance immediately. Can you describe the issue further?"
    elif "power" in speech_result.lower():
        reply = "It sounds like you're experiencing a power outage. We’ll notify the maintenance team to investigate."
    elif "pay rent" in speech_result.lower() or "rent" in speech_result.lower():
        reply = "You can pay rent through the Buildium Tenant Portal App at any time. Let me know if you need help logging in."
    else:
        reply = generate_ai_response(speech_result, lang)

    response.say(reply, voice=voice)
    response.listen()
    return Response(str(response), mimetype="application/xml")

if __name__ == "__main__":
    app.run(debug=True)
