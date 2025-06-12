from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather, Say
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
    gather.say("Hi, this is the AI assistant for G-R-H-U-S-A Properties. Please talk to me like a human and let me know how I can help.", voice="Polly.Joanna", language="en-US")
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
                {"role": "system", "content": "You are a helpful, bilingual (English/Spanish) AI assistant for a property management company called G-R-H-U-S-A Properties. Speak like a professional woman with warmth, empathy, and clarity. Respond like a human would — acknowledge issues, ask polite follow-ups, and maintain the conversation. Always ask another question to keep it going."},
            ] + conversations[from_number]
        )

        reply = ai_reply.choices[0].message.content
        conversations[from_number].append({"role": "assistant", "content": reply})

        resp = VoiceResponse()
        gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto')
        gather.say(reply, voice="Polly.Joanna", language="en-US")
        resp.append(gather)
        resp.redirect('/voice')
        return str(resp)

    except Exception as e:
        resp = VoiceResponse()
        resp.say("I’m sorry, something went wrong with the system. Please try again later.", voice="Polly.Joanna", language="en-US")
        return str(resp)

@app.route("/end", methods=["POST"])
def end_call():
    from_number = request.form.get("From")
    history = conversations.get(from_number, [])

    if history:
        summary = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Summarize this tenant conversation in professional tone for internal staff."}] + history
        )
        email_body = summary.choices[0].message.content
        subject = "Tenant Conversation Summary - Grhusa Properties"

        recipients = os.getenv("EMAIL_TO", "").split(",")
        for recipient in recipients:
            send_email(subject=subject, body=email_body, to=recipient.strip())

        del conversations[from_number]

    return ('', 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
