import speech_recognition as sr
import pyttsx3
import serial
import tkinter as tk
from threading import Thread, Lock
import atexit
import time

# --- Configuration ---
PORT = 'COM6'  # Change to your port
BAUD = 9600

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    time.sleep(2)  # let the Arduino reset after the serial connection opens
    robot_online = True
    error_msg = ""
except Exception as e:
    robot_online = False
    error_msg = str(e)
    ser = None

# pyttsx3 is not thread-safe: the GUI thread (button clicks) and the voice
# thread (voice_loop) can both call speak() at the same time, which can
# crash or hang the engine. A lock serializes access.
tts_lock = Lock()
engine = pyttsx3.init()


def speak(text):
    print(f"Orion: {text}")
    with tts_lock:
        engine.say(text)
        engine.runAndWait()


# Initial Servo Positions
servos = {"base": 90, "shld": 90, "elb": 90, "pit": 90, "roll": 90, "grip": 10}


def send_to_robot():
    if not robot_online:
        return
    try:
        cmd = f"{servos['base']},{servos['shld']},{servos['elb']},{servos['pit']},{servos['roll']},{servos['grip']}\n"
        ser.write(cmd.encode())
    except serial.SerialException as e:
        print(f"Serial write failed: {e}")


@atexit.register
def cleanup():
    if ser is not None and ser.is_open:
        ser.close()


# --- Voice Logic ---
def process_voice_command(command, app):
    cmd = command.lower()

    if "can you communicate with arm" in cmd:
        if robot_online:
            speak("Yes, the connection to the arm is established and stable.")
        else:
            speak(f"No, I cannot communicate with the arm. The error is {error_msg}")

    elif "orion sleep" in cmd or "go to sleep" in cmd:
        app.is_awake = False
        app.status_label.config(text="SLEEPING (Say 'Orion wake up')", fg="blue")
        speak("Going to sleep.")

    elif "hello" in cmd:
        speak("The arm is saying hello.")
        for _ in range(2):
            servos["grip"] = 120
            send_to_robot()
            time.sleep(0.3)
            servos["grip"] = 10
            send_to_robot()
            time.sleep(0.3)

    elif "activate arm" in cmd:
        speak("Systems online. Initializing arm movement.")
        for _ in range(2):
            servos["pit"] = 140
            send_to_robot()
            time.sleep(0.3)
            servos["pit"] = 40
            send_to_robot()
            time.sleep(0.3)
        servos["pit"] = 90
        send_to_robot()

    elif "turn right" in cmd:
        speak("Turning right.")
        servos["base"] = min(180, servos["base"] + 30)
        servos["pit"] = 120
        send_to_robot()
        time.sleep(0.2)
        servos["pit"] = 60
        send_to_robot()

    elif "turn left" in cmd:
        speak("Turning left.")
        servos["base"] = max(0, servos["base"] - 30)
        servos["pit"] = 120
        send_to_robot()
        time.sleep(0.2)
        servos["pit"] = 60
        send_to_robot()

    elif "move up" in cmd or "higher" in cmd:
        speak("Moving up.")
        servos["shld"] = min(180, servos["shld"] + 20)
        servos["elb"] = min(180, servos["elb"] + 15)
        send_to_robot()

    elif "move down" in cmd or "lower" in cmd:
        speak("Lowering position.")
        servos["shld"] = max(0, servos["shld"] - 20)
        servos["elb"] = max(0, servos["elb"] - 15)
        send_to_robot()

    else:
        speak("Sorry, I didn't catch that command.")

    # Keep the sliders in sync so Manual Mode picks up wherever voice left off
    app.sync_sliders()


# --- GUI and Threading ---
class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.is_awake = False
        self.manual_mode = False
        speak("Orion is ready.")

        # UI Setup
        self.status_label = tk.Label(root, text="SLEEPING (Say 'Orion wake up')", fg="blue", font=("Arial", 14))
        self.status_label.pack(pady=10)

        if not robot_online:
            tk.Label(root, text=f"Arm offline: {error_msg}", fg="red").pack(pady=5)

        # Sliders (Hidden until Manual Mode)
        self.slider_frame = tk.Frame(root)
        self.sliders = {}
        for part in ["base", "shld", "elb", "pit", "roll", "grip"]:
            s = tk.Scale(
                self.slider_frame, from_=0, to=180, orient=tk.HORIZONTAL,
                label=part, command=lambda v, p=part: self.update_val(p, v)
            )
            s.set(servos[part])
            s.pack()
            self.sliders[part] = s

        self.mode_btn = tk.Button(root, text="Switch to Manual Mode", command=self.toggle_manual)
        self.mode_btn.pack(pady=10)

    def update_val(self, part, val):
        if self.manual_mode:
            servos[part] = int(val)
            send_to_robot()

    def sync_sliders(self):
        # Reflect the current servo dict onto the slider widgets without
        # triggering update_val (which would re-send to the robot).
        for part, s in self.sliders.items():
            s.set(servos[part])

    def toggle_manual(self):
        self.manual_mode = not self.manual_mode
        if self.manual_mode:
            self.sync_sliders()
            self.slider_frame.pack()
            self.mode_btn.config(text="Switch to Voice Mode")
            speak("Voice stopped. Manual mode active.")
        else:
            self.slider_frame.pack_forget()
            self.mode_btn.config(text="Switch to Manual Mode")
            speak("Manual mode disabled. Voice active.")


def voice_loop(app):
    r = sr.Recognizer()
    while True:
        try:
            with sr.Microphone() as source:
                audio = r.listen(source, timeout=5, phrase_time_limit=6)
            text = r.recognize_google(audio).lower()

            if "orion wake up" in text:
                app.is_awake = True
                app.status_label.config(text="LISTENING...", fg="green")
                speak("I am awake. How can I help?")

            elif "stop voice mode" in text:
                app.toggle_manual()

            elif app.is_awake and not app.manual_mode:
                process_voice_command(text, app)

        except sr.WaitTimeoutError:
            pass  # no speech detected within the timeout window; keep listening
        except sr.UnknownValueError:
            pass  # speech was heard but not understood; keep listening
        except sr.RequestError as e:
            print(f"Speech recognition service error: {e}")
            time.sleep(2)  # avoid hammering the API if it's down
        except OSError as e:
            # e.g. microphone unplugged / unavailable
            print(f"Microphone error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("ORION Arm Control")
    app = RobotGUI(root)
    Thread(target=voice_loop, args=(app,), daemon=True).start()
    root.mainloop()