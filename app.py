import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
import openai
from langdetect import detect

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
conversations = {}

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def generate_response(prompt, language="en"):
    system_msg = {
        "en": "You are a helpful, friendly, and professional AI receptionist for a property management company called GRHUSA Properties.",
        "es": "Eres un recepcionista de IA servicial, amigable y profesional para una empresa de administración de propiedades llamada GRHUSA Properties."
    }
    messages = [
        {"role": "system", "content": system_msg.get(language, system_msg["en"])},
        {"role": "user", "content": prompt}
    ]
    completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    return completion.choices[0].message.content.strip()

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form.get("CallSid")
    user_input = request.form.get("SpeechResult", "").strip()
    language = detect_language(user_input)

    if call_sid not in conversations:
        conversations[call_sid] = []
        intro = {
            "en": "Hello, this is the AI assistant from GRHUSA Properties. You can speak to me like a human. How can I help you?",
            "es": "Hola, soy el asistente de inteligencia artificial de GRHUSA Properties. Puedes hablar conmigo como si fuera una persona. ¿En qué puedo ayudarte?"
        }
        response = VoiceResponse()
        response.say(intro[language], voice="Polly.Joanna" if language == "en" else "Polly.Conchita", language="en-US" if language == "en" else "es-US")
        response.listen()
        return Response(str(response), mimetype="application/xml")

    conversations[call_sid].append(user_input)

    response_text = generate_response(user_input, language)
    if any(name in user_input.lower() for name in ["liz", "elsie"]):
        response_text = {
            "en": "Thank you, I will forward this conversation to Liz or Elsie. Someone from the team will reach out to you shortly.",
            "es": "Gracias, enviaré esta conversación a Liz o Elsie. Alguien del equipo se comunicará contigo pronto."
        }.get(language, response_text)

    response = VoiceResponse()
    response.say(response_text, voice="Polly.Joanna" if language == "en" else "Polly.Conchita", language="en-US" if language == "en" else "es-US")
    response.listen()
    return Response(str(response), mimetype="application/xml")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
