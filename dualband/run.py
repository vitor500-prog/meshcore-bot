import asyncio, sys, time

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from dualband.stats_db import StatsDB
from dualband.correlator import Correlator
from dualband.dashboard import start_dashboard

try:
    from meshcore import MeshCore
except ImportError:
    print("ERROR: meshcore library not found.")
    sys.exit(1)

with open("config.toml", "rb") as f:
    cfg = tomllib.load(f)

LOCATION  = cfg["general"]["location"]
CHANNELS  = cfg["general"]["channels"]
GRACE     = cfg["general"].get("cross_band_grace_seconds", 8)
DB_PATH   = cfg["database"]["path"]
DASH_HOST = cfg["dashboard"]["host"]
DASH_PORT = cfg["dashboard"]["port"]
BANDS     = cfg["bands"]

db   = StatsDB(DB_PATH)
corr = Correlator(window=GRACE)

replied_keys = {}
REPLY_WINDOW = 30

async def handle_band(band_cfg):
    name  = band_cfg["name"]
    label = band_cfg["label"]
    port  = band_cfg["port"]

    mc = await MeshCore.create_serial(port)
    await mc.connect()
    print(f"[{name}] Connected on {port}")

    async for event in mc.subscribe_channel_messages():
        try:
            p       = event.payload
            sender  = getattr(p, "sender",       "unknown")
            channel = getattr(p, "channel_name", "unknown")
            text    = (getattr(p, "text", "") or "").strip()
            hops    = getattr(p, "path_len",    None)

            if channel not in CHANNELS:
                continue

            print(f"[{name}] #{channel} | {sender}: {text} (hops={hops})")

            corr_key = corr.key(sender, channel, text)
            db.record_reception(corr_key, name, sender, channel, text, hops)

            if text.lower().startswith("!ping"):
                now  = time.time()
                last = replied_keys.get(corr_key, 0)
                if now - last > REPLY_WINDOW:
                    replied_keys[corr_key] = now
                    hops_str = str(hops) if hops is not None else "?"
                    reply = (
                        f"🏓 pong from {LOCATION}\n"
                        f"📡 Band: {label} ({name} MHz)\n"
                        f"↕️  Hops: {hops_str}"
                    )
                    await mc.send_channel_message(channel, reply)
                    print(f"[{name}] Replied via {label}")

        except Exception as e:
            print(f"[{name}] Error: {e}")

async def finalizer():
    while True:
        db.finalize_stale(GRACE)
        await asyncio.sleep(5)

async def main():
    start_dashboard(db, host=DASH_HOST, port=DASH_PORT)
    await asyncio.gather(*[handle_band(b) for b in BANDS], finalizer())

if __name__ == "__main__":
    asyncio.run(main())
