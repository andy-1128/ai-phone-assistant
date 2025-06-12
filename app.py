
import os
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import openai
from outlook_email import send_email
import langdetect

openai.api_key = os.getenv("OPENAI_API_KEY")
app = Flask(__name__)
conversations = {}

def detect_language(text):
    try:
        lang = langdetect.detect(text)
        return lang
    except:
        return 'en'

@app.route("/voice", methods=['POST'])
def voice():
    response = VoiceResponse()
    response.say("Hi, this is the AI assistant for Grhusa Properties. Please talk to me like a human and let me know how I can help.", voice='en-US-JennyMultilingualNeural')
    gather = Gather(input="speech", action="/gather", method="POST", speechTimeout="auto", language="en-US")
    response.append(gather)
    return str(response)

@app.route("/gather", methods=['POST'])
def gather():
    user_input = request.values.get('SpeechResult', '').strip()
    call_sid = request.values.get("CallSid")

    if not user_input:
        return str(VoiceResponse().say("I didn't catch that. Please try again."))

    lang = detect_language(user_input)
    voice = 'es-MX-DaliaNeural' if lang == 'es' else 'en-US-JennyMultilingualNeural'

    prompt = f"The user said: {user_input}. Respond in a friendly and helpful tone suitable for a property management assistant."
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        ai_reply = completion.choices[0].message['content']
    except Exception as e:
        return str(VoiceResponse().say("Sorry, there was an application error. Please try again later.", voice=voice))

    # Track conversation
    if call_sid not in conversations:
        conversations[call_sid] = []
    conversations[call_sid].append({"user": user_input, "ai": ai_reply})

    response = VoiceResponse()
    gather = Gather(input="speech", action="/gather", method="POST", speechTimeout="auto", language=lang)
    gather.say(ai_reply, voice=voice)
    response.append(gather)

    # If user says "goodbye" or similar
    if any(bye in user_input.lower() for bye in ["bye", "adios", "goodbye", "gracias"]):
        summary_prompt = "Summarize this conversation briefly and highlight important issues."
" + str(conversations[call_sid])
        try:
            summary = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": summary_prompt}]
            ).choices[0].message['content']
            send_email("Tenant Call Summary", summary)
        except:
            pass
        response.say("Thank you for calling. We’ll follow up shortly.", voice=voice)
        response.hangup()

    return str(response)
