import os
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def generate_reply(text, lang="en", memory=[]):
    prompt = "You are a helpful AI receptionist. Respond kindly, ask 1 question at a time. Stop if interrupted. Only summarize at end."
    if lang == "es":
        prompt = "Eres una recepcionista de IA amable y profesional. Responde como humana, una pregunta a la vez. Para si te interrumpen."

    messages = [{"role": "system", "content": prompt}]
    for item in memory:
        messages.append(item)
    messages.append({"role": "user", "content": text})

    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.6,
        max_tokens=180
    )
    return response.choices[0].message.content.strip()
