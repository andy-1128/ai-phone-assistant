import datetime
import webbrowser
import wikipedia
import sys

# Initialize the text-to-speech engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)  # Select female voice; use voices[0] for male

def speak(text):
    """Convert text to speech."""
    engine.say(text)
    engine.runAndWait()

def greet_user():
    """Greet the user based on the time of day."""
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        speak("Good morning! Welcome to our office.")
    elif 12 <= hour < 17:
        speak("Good afternoon! Welcome to our office.")
    else:
        speak("Good evening! Welcome to our office.")
    speak("How may I assist you today?")

def listen_command():
    """Listen for a command from the user and return it as text."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.pause_threshold = 1
        audio = recognizer.listen(source)
    try:
        print("Recognizing...")
        command = recognizer.recognize_google(audio, language='en-US')
        print(f"User said: {command}")
    except sr.UnknownValueError:
        speak("I'm sorry, I didn't catch that. Could you please repeat?")
        return ""
    except sr.RequestError:
        speak("Sorry, I'm having trouble connecting to the service.")
        return ""
    return command.lower()

def process_command(command):
    """Process the user's command and perform actions."""
    if 'your name' in command:
        speak("I am your virtual receptionist.")
    elif 'time' in command:
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The current time is {current_time}.")
    elif 'date' in command:
        current_date = datetime.datetime.now().strftime("%B %d, %Y")
        speak(f"Today's date is {current_date}.")
    elif 'open website' in command:
        speak("Which website would you like me to open?")
        website = listen_command()
        if website:
            url = f"https://{website}"
            webbrowser.open(url)
            speak(f"Opening {website}")
    elif 'search wikipedia' in command:
        speak("What would you like to know from Wikipedia?")
        query = listen_command()
        if query:
            try:
                summary = wikipedia.summary(query, sentences=2)
                speak(f"According to Wikipedia, {summary}")
            except wikipedia.exceptions.DisambiguationError as e:
                speak("There are multiple entries for that topic. Please be more specific.")
            except wikipedia.exceptions.PageError:
                speak("I couldn't find any information on that topic.")
    elif 'exit' in command or 'quit' in command:
        speak("Thank you for visiting. Have a great day!")
        sys.exit()
    else:
        speak("I'm sorry, I didn't understand that command.")

if __name__ == "__main__":
    greet_user()
    while True:
        user_command = listen_command()
        if user_command:
            process_command(user_command)
            send_email(
    subject="Tenant Concern Summary",
    body=email_body
)
