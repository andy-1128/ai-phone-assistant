
import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from outlook_email import send_email

app = Flask(__name__)
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

conversation_history = []

def detect_language(text):
    if any(word in text.lower() for word in ["hola", "baño", "problema", "gracias"]):
        return "spanish"
    return "english"

def get_voice(language):
    return "es-US-JennyMultilingualNeural" if language == "spanish" else "en-US-KalebNeural"

def generate_ai_response(prompt, language="english"):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are a helpful AI receptionist for a property management company named GRHUSA Properties."},
                  {"role": "user", "content": prompt}]
    )
    reply = response.choices[0].message.content.strip()
    conversation_history.append(f"User: {prompt}\nAI: {reply}")
    return reply

@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    response.say("Hi, this is the AI assistant for GRHUSA Properties. Please talk to me like a human and let me know how I can help.", voice="en-US-KalebNeural", language="en-US")
    gather = Gather(input="speech", action="/gather", speechTimeout="auto", language="en-US")
    gather.say("I'm listening.", voice="en-US-KalebNeural")
    response.append(gather)
    return Response(str(response), mimetype="application/xml")

@app.route("/gather", methods=["POST"])
def gather():
    speech_result = request.form.get("SpeechResult", "")
    language = detect_language(speech_result)
    voice = get_voice(language)
    ai_response = generate_ai_response(speech_result, language)

    response = VoiceResponse()
    if speech_result:
        gather = Gather(input="speech", action="/gather", speechTimeout="auto", language="es-US" if language == "spanish" else "en-US")
        gather.say(ai_response, voice=voice)
        response.append(gather)
    else:
        response.say("I'm sorry, I didn't catch that.", voice=voice)

    if "bye" in speech_result.lower() or "adiós" in speech_result.lower():
        summary_prompt = "Summarize this conversation briefly and highlight important issues."
        summary = generate_ai_response(summary_prompt)
        send_email("Tenant Call Summary", summary)
        response.say("Thank you for calling. We will follow up shortly.", voice=voice)
        response.hangup()
        summary_prompt = "Summarize this conversation briefly and highlight important issues: " + str(conversations[call_sid])

    return Response(str(response), mimetype="application/xml")

    if __name__ == "__main__":
        app.run(debug=True)
    if __name__ == "__main__":
        from waitress import serve
        serve(app, host="0.0.0.0", port=10000)
