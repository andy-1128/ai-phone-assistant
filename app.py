from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from outlook_email import send_email
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
conversations = {}

@app.route("/", methods=["GET"])
def index():
    return "✅ AI Phone Assistant for Grhusa Properties is running"

@app.route("/voice", methods=["POST"])
def voice():
    from_number = request.form.get("From")
    conversations[from_number] = []

    resp = VoiceResponse()
    gather = Gather(
        input='speech', 
        action='/gather', 
        method='POST', 
        speechTimeout='auto', 
        language='es-ES', 
        voice='Polly.Conchita'
    )
    gather.say("Hola, soy la asistente de inteligencia artificial para Grhusa Properties. Por favor, háblame como si fuera una persona real y dime cómo puedo ayudarte hoy.")
    resp.append(gather)
    resp.redirect('/voice')
    return str(resp)

@app.route("/gather", methods=["POST"])
def gather():
    speech_text = request.form.get("SpeechResult")
    from_number = request.form.get("From")

    if from_number not in conversations:
        conversations[from_number] = []

    conversations[from_number].append({"role": "user", "content": speech_text})

    try:
        ai_reply = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a warm, caring, intelligent AI phone assistant for a property management company named Grhusa Properties. Speak in fluent Spanish and sound like a professional Spanish-speaking human. Handle tenant concerns clearly, especially about issues like leaking toilets, broken AC, rent delays, or noisy neighbors. Always acknowledge their emotion and offer helpful responses. Keep the conversation going until they indicate they are done."},
            ] + conversations[from_number]
        )

        reply = ai_reply.choices[0].message.content
        conversations[from_number].append({"role": "assistant", "content": reply})

        resp = VoiceResponse()
        gather = Gather(
            input='speech', 
            action='/gather', 
            method='POST', 
            speechTimeout='auto', 
            language='es-ES', 
            voice='Polly.Conchita'
        )
        gather.say(reply)
        resp.append(gather)
        resp.redirect('/voice')
        return str(resp)

    except Exception as e:
        resp = VoiceResponse()
        resp.say("Lo siento, ha ocurrido un error de aplicación. Intentémoslo de nuevo más tarde.")
        return str(resp)

@app.route("/end", methods=["POST"])
def end_call():
    from_number = request.form.get("From")
    history = conversations.get(from_number, [])

    if history:
        summary = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Summarize this tenant conversation clearly in Spanish. Stress important issues or requests made by the tenant. Format the summary like a report for the Grhusa Properties team."}
            ] + history
        )
        email_body = summary.choices[0].message.content
        subject = "Resumen de llamada de inquilino - Grhusa Properties"
        send_email(subject=subject, body=email_body)
        del conversations[from_number]

    return ('', 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
