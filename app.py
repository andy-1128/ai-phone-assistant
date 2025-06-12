from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import openai
import os
from dotenv import load_dotenv
from outlook_email import send_email

load_dotenv()
app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
conversations = {}

@app.route("/", methods=["GET"])
def index():
    return "✅ AI Phone Assistant for Grhusa Properties is running"

@app.route("/voice", methods=["POST"])
def voice():
    from_number = request.form.get("From")
    conversations[from_number] = []

    resp = VoiceResponse()
    gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto', voice='Polly.Joanna')
    gather.say("Hello! This is the AI assistant for G-R-H-U-S-A Properties. Please talk to me like a human and let me know how I can help. You can speak in English or Spanish.")
    resp.append(gather)
    resp.redirect('/voice')
    return str(resp)

@app.route("/gather", methods=["POST"])
def gather():
    speech_text = request.form.get('SpeechResult')
    from_number = request.form.get('From')

    if from_number not in conversations:
        conversations[from_number] = []

    conversations[from_number].append({"role": "user", "content": speech_text})

    try:
        ai_reply = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional, helpful, and kind bilingual AI assistant for a property management company called GRHUSA Properties."
                        "Speak clearly and fast with a friendly tone, like a human assistant."
                        "Handle tenant complaints, questions about leases, payments, and emergencies."
                        "Always ask follow-ups and keep the conversation going until the tenant ends the call."
                        "Example: If a tenant says 'Hi, my toilet is leaking', reply 'I'm sorry to hear that! When did the leak start?' and continue from there."
                    )
                }
            ] + conversations[from_number]
        )

        reply = ai_reply.choices[0].message['content']
        conversations[from_number].append({"role": "assistant", "content": reply})

        resp = VoiceResponse()
        gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto', voice='Polly.Joanna')
        gather.say(reply)
        resp.append(gather)
        resp.redirect('/voice')
        return str(resp)

    except openai.error.OpenAIError as e:
        resp = VoiceResponse()
        resp.say("I'm very sorry. There was a technical issue with the assistant. Please try again later.")
        return str(resp)

@app.route("/end", methods=["POST"])
def end_call():
    from_number = request.form.get("From")
    history = conversations.get(from_number, [])

    if history:
        summary = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Summarize this tenant conversation clearly for the property management team. List any problems and tenant needs."}
            ] + history
        )
        email_body = summary.choices[0].message['content']
        subject = "📋 Tenant Call Summary - Grhusa AI Assistant"

        # Send to multiple recipients
        recipients = os.getenv("EMAIL_TO").split(',')
        for recipient in recipients:
            send_email(subject=subject, body=email_body, to=recipient.strip())

        del conversations[from_number]

    return ('', 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
