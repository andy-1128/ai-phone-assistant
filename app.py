if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
from outlook_email import send_email
import os
from dotenv import load_dotenv
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse

# Load environment variables
load_dotenv()

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "✅ AI Phone Assistant is running"

@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    resp.say("Hello! This is the AI assistant. How can I help you?")
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
load_dotenv()
app = Flask(__name__)
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/", methods=["GET"])
def index():
    return "✅ AI Phone Assistant is running"

conversations = {}

@app.route("/voice", methods=["POST"])
def voice():
    from_number = request.form.get("From")
    conversations[from_number] = []

    resp = VoiceResponse()
    gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto')
    gather.say("Hi, this is the AI assistant for property management. How can I help you today?")
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

    ai_reply = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful real estate property manager AI. Keep conversations short and clear."}
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
            messages=[{"role": "system", "content": "Summarize this tenant call for an email to staff."}] + history
        )
        email_body = summary.choices[0].message.content
        send_email(subject="Tenant Issue: " + email_body.split('.')[0], body=email_body)
        del conversations[from_number]
    
    return ('', 204)
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
