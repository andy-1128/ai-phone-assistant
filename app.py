from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from langdetect import detect
import openai
import os

# Set your OpenAI and email keys
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

def generate_ai_response(prompt, lang='en'):
    system_instruction = "You are a smart, polite AI receptionist for a property management company. Respond naturally like a human and stay helpful."
    if lang == "es":
        system_instruction = "Eres una recepcionista inteligente y amable para una compañía de administración de propiedades. Responde naturalmente y de forma útil."

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content.strip()

@app.route("/voice", methods=["POST"])
def voice_reply():
    response = VoiceResponse()
    transcript = request.values.get("SpeechResult", "").strip()
    
    # Detect language or default to English
    try:
        lang = detect(transcript) if transcript else "en"
    except:
        lang = "en"

    # Greeting (only if call just started)
    if not transcript:
        response.say("Hello this is the AI assistant from GRHUSA Properties. You can talk to me like a human. How can I help you?", voice='Polly.Joanna')
        response.listen()
        return Response(str(response), mimetype="application/xml")

    # Special person routing
    if "liz" in transcript.lower() or "elsie" in transcript.lower():
        response.say("I'll forward this conversation to Liz or Elsie. Someone from our team will reach out to you shortly.", voice='Polly.Joanna' if lang == 'en' else 'Polly.Lupe')
        response.hangup()
        return Response(str(response), mimetype="application/xml")

    # Handle known scenarios quickly
    lower_text = transcript.lower()
    if "leak" in lower_text or "toilet" in lower_text or "pipe" in lower_text:
        msg = "Thanks for reporting the plumbing issue. We'll dispatch maintenance shortly."
    elif "rent" in lower_text or "pay" in lower_text:
        msg = "You can pay your rent on the Buildium tenant portal. Let us know if you need help logging in."
    elif "lease" in lower_text or "sign" in lower_text:
        msg = "We can help you with your lease signing. A team member will contact you shortly."
    else:
        msg = generate_ai_response(transcript, lang)

    response.say(msg, voice='Polly.Joanna' if lang == 'en' else 'Polly.Lupe')
    response.listen()
    return Response(str(response), mimetype="application/xml")

@app.route("/", methods=["GET"])
def home():
    return "GRHUSA AI Assistant is running."

if __name__ == "__main__":
    app.run(debug=True, port=5000)
