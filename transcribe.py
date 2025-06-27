import asyncio
import websockets
import base64
import json
import tempfile
import whisper
from generate_response import generate_reply
from synthesize_voice import synthesize_text
from pydub import AudioSegment

model = whisper.load_model("base")

async def handle_audio(websocket):
    memory = []
    while True:
        msg = await websocket.recv()
        payload = json.loads(msg)
        if payload["event"] == "media":
            audio_bytes = base64.b64decode(payload["media"]["payload"])
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                f.write(audio_bytes)
                f.flush()
                result = model.transcribe(f.name)
                text = result["text"]
                if text.strip():
                    print("Transcribed:", text)
                    reply = generate_reply(text, memory=memory)
                    memory.append({"role": "user", "content": text})
                    memory.append({"role": "assistant", "content": reply})
                    mp3_data = synthesize_text(reply)
                    await websocket.send(json.dumps({
                        "event": "media",
                        "media": {
                            "payload": base64.b64encode(mp3_data).decode("utf-8")
                        }
                    }))

def start_websocket():
    asyncio.get_event_loop().run_until_complete(
        websockets.serve(handle_audio, "0.0.0.0", 8765)
    )
    asyncio.get_event_loop().run_forever()
