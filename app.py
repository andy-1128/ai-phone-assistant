
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
import openai
import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "AI receptionist is live."

@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    response.say(
        "Hello, this is the AI assistant from GRHUSA Properties. "
        "You can talk to me like a human. How can I help you today?",
        voice='Polly.Matthew',
        language='en-US'
    )
    response.listen(timeout=5)
    response.say("Thank you. A team member will follow up with you shortly.")
    return Response(str(response), mimetype='application/xml')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv("PORT", 5000)))

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

conversations = {}

def detect_language(text):
    try:
        return detect(text)
    except:
        return 'en'

def generate_response(prompt, language):
    system_prompt = "You are a professional, polite, and helpful AI receptionist for GRHUSA Properties. Help with maintenance, lease, or rent questions. If the caller mentions Liz or Elsie, respond you'll notify the team."
    if language == 'es':
        system_prompt = "Eres un recepcionista de IA profesional, cortés y servicial para GRHUSA Properties. Ayuda con mantenimiento, contrato de arrendamiento o pagos de renta. Si mencionan a Liz o Elsie, responde que notificarás al equipo."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    try:
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return response.choices[0].message.content.strip()
    except:
        return "I'm sorry, I'm currently experiencing a technical issue."

@app.route("/voice", methods=['POST'])
def voice():
    call_sid = request.form['CallSid']
    speech_result = request.form.get('SpeechResult', '')
    language = detect_language(speech_result)

    if call_sid not in conversations:
        conversations[call_sid] = []
        greeting = "Hello, this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help?"
        voice = 'Joanna'
        if language == 'es':
            greeting = "Hola, soy el asistente virtual de GRHUSA Properties. Puedes hablar conmigo como si fuera una persona. ¿En qué puedo ayudarte?"
            voice = 'Conchita'
        resp = VoiceResponse()
        gather = resp.gather(input="speech", action="/voice", method="POST", timeout=5)
        gather.say(greeting, voice=voice)
        return Response(str(resp), mimetype='application/xml')

    conversations[call_sid].append(speech_result)
    language = detect_language(speech_result)
    reply = generate_response(speech_result, language)
    voice = 'Joanna' if language == 'en' else 'Conchita'

    resp = VoiceResponse()
    resp.say(reply, voice=voice)
    resp.hangup()
    return Response(str(resp), mimetype='application/xml')

if __name__ == "__main__":
    app.run(debug=True)
