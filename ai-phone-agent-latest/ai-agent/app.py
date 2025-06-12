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
    speech_text = request.form.get('SpeechResult')
    from_number = request.form.get('From')

    if not speech_text:
        resp = VoiceResponse()
        resp.say("Sorry, I didn’t catch that. Please say it again.")
        resp.redirect('/voice')
        return str(resp)

    if from_number not in conversations:
        conversations[from_number] = []

    conversations[from_number].append({"role": "user", "content": speech_text})

    system_prompt = {
        "role": "system",
        "content": "You are a compassionate, intelligent property manager AI assistant working for Grhusa Properties. Help tenants with repair issues, complaints, lease info, and emergencies. Respond with empathy and keep the conversation flowing like a real human."
    }

    chat_history = [system_prompt] + conversations[from_number]

    try:
        ai_reply = openai.chat.completions.create(
            model="gpt-4o",
            messages=chat_history
        )
        reply = ai_reply.choices[0].message.content
    except Exception as e:
        reply = "Sorry, there's been an application error. A team member will contact you shortly."

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
            messages=[{
                "role": "system",
                "content": "Summarize this tenant call for the property management team in a few concise sentences. Highlight what action is needed."
            }] + history
        )
        subject = "Grhusa Property Tenant Summary"
        body = summary.choices[0].message.content
        send_email(subject=subject, body=body)
        del conversations[from_number]

    return ('', 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
