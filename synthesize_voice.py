import boto3
import os

def synthesize_text(text, voice_id="Joanna", lang="en-US"):
    polly = boto3.client("polly",
                         aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                         aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                         region_name="us-east-1")
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice_id,
        LanguageCode=lang
    )
    audio_stream = response["AudioStream"].read()
    return audio_stream
