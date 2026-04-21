import hashlib
import time

class Correlator:
    def __init__(self, window=8):
        self.window = window

    def key(self, sender, channel, text):
        bucket = int(time.time() // self.window)
        raw = f"{sender}|{channel}|{text.strip()}|{bucket}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]
