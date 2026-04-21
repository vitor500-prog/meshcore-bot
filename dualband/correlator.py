import hashlib
import time


class Correlator:
    """
    Groups the same message received on multiple bands
    into a single correlation key using a time bucket window.
    """

    def __init__(self, window=8):
        self.window = window  # seconds

    def key(self, sender, channel, text):
        bucket = int(time.time() // self.window)
        raw = f"{sender}|{channel}|{text.strip()}|{bucket}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

