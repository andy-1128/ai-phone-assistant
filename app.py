import os
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from openai import OpenAI
from outlook_email import send_email

app = Flask(__name__)
conversations = {}

@app.route("/voice", methods=["POST"])
def voice():
    call_sid = request.form["CallSid"]
    response = VoiceResponse()
    response.say("Hola, gracias por llamar a Grhusa Properties. ¿Cómo puedo ayudarte hoy?", voice="Polly.Joanna", language="es-ES")
    response.gather(input="speech", action="/gather", method="POST")
    return Response(str(response), mimetype="application/xml")

@app.route("/gather", methods=["POST"])
def gather():
    call_sid = request.form["CallSid"]
    speech_result = request.form.get("SpeechResult", "")
    conversations.setdefault(call_sid, []).append(speech_result)
    response = VoiceResponse()

    # Simple language detection
    if any(word in speech_result.lower() for word in ["hola", "baño", "gracias", "tengo", "problema"]):
        voice = "Polly.Jennifer"
        response.say("Lo siento escuchar eso. ¿Puedes darme más detalles por favor?", voice=voice, language="es-ES")
    else:
        voice = "Polly.Kimberly"
        response.say("I'm sorry to hear that. Could you please tell me more?", voice=voice)

    response.gather(input="speech", action="/gather", method="POST")
    return Response(str(response), mimetype="application/xml")

@app.route("/end", methods=["POST"])
def end():
    call_sid = request.form["CallSid"]
    summary = "Summarize this conversation briefly and highlight important issues: " + str(conversations.get(call_sid, []))

    response = VoiceResponse()
    response.say("Thank you for calling. We will follow up shortly.", voice="Polly.Kimberly")
    response.hangup()

    send_email("Tenant Call Summary", summary)
    return Response(str(response), mimetype="application/xml")

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=10000)
