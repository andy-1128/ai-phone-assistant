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
    gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto')
    gather.say("Hi, this is the AI assistant for G-R-H-U-S-A Properties. Please talk to me like a human and let me know how I can help.")
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

    ai_reply = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful and intelligent AI phone assistant for a property management company named G-R-H-U-S-A Properties. Your job is to have real, human-like conversations with tenants about their issues such as rent, repairs, noise complaints, lease questions, or emergencies. Always be clear, polite, and keep the conversation going until they confirm they are done."},
        ] + conversations[from_number]
    )

    reply = ai_reply.choices[0].message.content
    conversations[from_number].append({"role": "assistant", "content": reply})

    resp = VoiceResponse()
    gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto')
    gather.say(reply)
    resp.append(gather)
    resp.redirect('/voice')
    return str(resp)

@app.route("/end", methods=["POST"])
def end_call():
    from_number = request.form.get("From")
    history = conversations.get(from_number, [])

    if history:
        summary = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Summarize this tenant call clearly in a few sentences for the property team."}] + history
        )
        email_body = summary.choices[0].message.content
        subject = "Tenant Issue Summary - Grhusa Call"
        send_email(subject=subject, body=email_body)
        del conversations[from_number]

    return ('', 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
