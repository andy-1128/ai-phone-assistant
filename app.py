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
    gather.say("Hi, this is the AI assistant for G-R-H-U-S-A Properties. Please talk to me like a human and let me know how I can help.", voice="Polly.Kimberly", language="en-US")
    resp.append(gather)
    resp.redirect('/voice')
    return str(resp)

@app.route("/gather", methods=["POST"])
def gather():
    speech_text = request.form.get("SpeechResult")
    from_number = request.form.get("From")

    if not speech_text:
        resp = VoiceResponse()
        resp.say("I'm sorry, I didn't catch that. Could you repeat it?", voice="Polly.Kimberly", language="en-US")
        resp.redirect('/voice')
        return str(resp)

    is_spanish = any(word in speech_text.lower() for word in ["baño", "agua", "problema", "grifo", "gotea", "reparar"])
    lang = 'es-ES' if is_spanish else 'en-US'
    voice = 'Polly.Conchita' if is_spanish else 'Polly.Kimberly'

    if from_number not in conversations:
        conversations[from_number] = []

    conversations[from_number].append({"role": "user", "content": speech_text})

    prompt = "You are an AI phone assistant for Grhusa Properties."
    if is_spanish:
        prompt += " You are Jennifer Lopez. Speak fluent Spanish clearly. Answer naturally and ask clarifying questions."
    else:
        prompt += " You are Kaley Cuoco. Speak fluent English, clearly and fast. Respond helpfully and conversationally."

    try:
        ai_reply = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt}
            ] + conversations[from_number]
        )
        reply = ai_reply.choices[0].message.content
    except Exception:
        reply = "Lo siento, ocurrió un error con la aplicación." if is_spanish else "Sorry, there was an application error."

    conversations[from_number].append({"role": "assistant", "content": reply})

    resp = VoiceResponse()
    gather = Gather(input='speech', action='/gather', method='POST', speechTimeout='auto')
    gather.say(reply, voice=voice, language=lang)
    resp.append(gather)
    resp.redirect('/voice')
    return str(resp)

@app.route("/end", methods=["POST"])
def end_call():
    from_number = request.form.get("From")
    history = conversations.get(from_number, [])

    if history:
        summary_prompt = "Please summarize this tenant call with important issues highlighted. Keep it professional."
        try:
            summary = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": summary_prompt}
                ] + history
            )
            email_body = summary.choices[0].message.content
            subject = "📞 Tenant Call Summary - GRHUSA Properties"
            send_email(subject=subject, body=email_body)
        except Exception:
            pass

        del conversations[from_number]

    return ('', 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
