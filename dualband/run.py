import asyncio
import sys
import time

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from dualband.stats_db   import StatsDB
from dualband.correlator import Correlator
from dualband.dashboard  import start_dashboard

try:
    from meshcore import MeshCore
except ImportError:
    print("ERROR: meshcore library not found. Run: pip install meshcore")
    sys.exit(1)

# ── Load config ────────────────────────────────────────────────────────────────
with open("config.toml", "rb") as f:
    cfg = tomllib.load(f)

BOT_NAME  = cfg["general"]["bot_name"]
LOCATION  = cfg["general"]["location"]
CHANNELS  = cfg["general"]["monitor_channels"]
GRACE     = cfg["general"].get("cross_band_grace_seconds", 8)
DB_PATH   = cfg["database"]["path"]
DASH_HOST = cfg["dashboard"]["host"]
DASH_PORT = cfg["dashboard"]["port"]
BANDS     = cfg["bands"]
RESPONSES = cfg["responses"]

# ── Init DB & correlator ────────────────────────────────────────────────────────
db   = StatsDB(DB_PATH)
corr = Correlator(window=GRACE)

# Deduplicate replies: don't reply twice to same message on both bands
replied_keys  = {}
REPLY_WINDOW  = 30  # seconds


def build_hops_label(hops):
    """Convert hop count to Portuguese label — matches your original style."""
    if hops is None or hops == 0:
        return "direto"
    elif hops == 1:
        return "1 salto"
    else:
        return f"{hops} saltos"


def build_reply(template_key, sender, channel, band_label, first_band, hops):
    """Format a response template from config.toml with all variables."""
    template   = RESPONSES.get(template_key, "")
    hops_label = build_hops_label(hops)

    return template.format(
        sender      = sender,
        hops_label  = hops_label,
        path        = band_label,           # e.g. "433 MHz"
        band        = band_label,
        first_band  = first_band,           # which band received it first
        hops        = hops if hops is not None else "?",
        channel     = channel,
        location    = LOCATION,
        bot_name    = BOT_NAME,
    )


async def handle_band(band_cfg):
    name  = band_cfg["name"]   # "433" or "868"
    label = band_cfg["label"]  # "433 MHz" or "868 MHz"
    port  = band_cfg["port"]   # "/dev/ttyUSB0" etc.

    print(f"[{name}] Connecting on {port}...")

    mc = await MeshCore.create_serial(port)
    await mc.connect()
    print(f"[{name}] ✅ Connected on {port}")

    async for event in mc.subscribe_channel_messages():
        try:
            p       = event.payload
            sender  = getattr(p, "sender",       "unknown")
            channel = getattr(p, "channel_name", "unknown")
            text    = (getattr(p, "text", "") or "").strip()
            hops    = getattr(p, "path_len",     None)

            # Only process monitored channels
            if channel not in CHANNELS:
                continue

            print(f"[{name}] #{channel} | {sender}: {text} (hops={hops})")

            # Record in DB (returns True if first reception of this message)
            corr_key   = corr.key(sender, channel, text)
            is_first   = db.record_reception(corr_key, name, sender, channel, text, hops)
            first_band = label if is_first else "?"

            # ── Ping response ──────────────────────────────────────────────────
            if text.lower().startswith("!ping"):
                now  = time.time()
                last = replied_keys.get(corr_key, 0)

                if now - last > REPLY_WINDOW:
                    replied_keys[corr_key] = now

                    reply = build_reply(
                        template_key = "ping",
                        sender       = sender,
                        channel      = channel,
                        band_label   = label,
                        first_band   = label,
                        hops         = hops,
                    )

                    await mc.send_channel_message(channel, reply)
                    print(f"[{name}] 📤 Replied: {reply}")
                else:
                    print(f"[{name}] ⏩ Skipped duplicate reply (already replied {int(now-last)}s ago)")

        except Exception as e:
            print(f"[{name}] ⚠️ Error: {e}")


async def finalizer():
    """Periodically mark stale messages as finalized in DB."""
    while True:
        db.finalize_stale(GRACE)
        await asyncio.sleep(5)


async def main():
    print(f"🤖 {BOT_NAME} starting...")
    print(f"📡 Monitoring channels: {CHANNELS}")
    print(f"🔌 Bands: {[b['label'] + ' on ' + b['port'] for b in BANDS]}")

    start_dashboard(db, host=DASH_HOST, port=DASH_PORT)

    await asyncio.gather(
        *[handle_band(b) for b in BANDS],
        finalizer()
    )


if __name__ == "__main__":
    asyncio.run(main())
