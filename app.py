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
    return "✅ AI Phone Assistant for GRHUSA Properties is active"

@app.route("/voice", methods=["POST"])
def voice():
    from_number = request.form.get("From")
    conversations[from_number] = []

    resp = VoiceResponse()
    gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto')
    gather.say("Hi, this is the AI assistant for GRHUSA Properties. Please talk to me like a human and let me know how I can help you.")
    resp.append(gather)
    resp.redirect('/voice')
    return str(resp)

@app.route("/gather", methods=["POST"])
def gather():
    speech_text = request.form.get('SpeechResult')
    from_number = request.form.get('From')

    if not speech_text:
        resp = VoiceResponse()
        resp.say("Sorry, I didn't catch that. Please try again.")
        resp.redirect('/voice')
        return str(resp)

    if from_number not in conversations:
        conversations[from_number] = []

    conversations[from_number].append({"role": "user", "content": speech_text})

    ai_reply = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an experienced and friendly property management assistant at GRHUSA. Help tenants with unit issues, rent, maintenance, and schedule follow-ups. Keep responses professional and clear."}
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
            messages=[{"role": "system", "content": "Summarize the following tenant call for a property management team. Include problems mentioned and tone of call."}] + history
        )
        email_body = summary.choices[0].message.content
        send_email(
            subject="New Tenant Issue Logged",
            body=email_body
        )
        del conversations[from_number]

    resp = VoiceResponse()
    resp.say("Thank you. This conversation will be escalated to a GRHUSA team member who will follow up with you shortly. Goodbye.")
    resp.hangup()
    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
