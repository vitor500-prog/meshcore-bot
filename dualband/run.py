import asyncio
import time
import sys

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from meshcore import MeshCore

# ── Load config ────────────────────────────────────────────────
with open("config.toml", "rb") as f:
    cfg = tomllib.load(f)

GRACE       = cfg["general"]["cross_band_grace_seconds"]  # 8
CHANNELS    = cfg["QSO"]["monitor_channels"]
BANDS       = cfg["bands"]
RESP_SINGLE = cfg["responses"]["ping"]
RESP_DUAL   = cfg["responses"]["ping_dual"]

# ── Correlator ─────────────────────────────────────────────────
correlator = {}
corr_lock  = asyncio.Lock()

# ── Helpers ────────────────────────────────────────────────────
def build_hops_label(hops: int) -> str:
    if hops == 0:
        return "direto"
    if hops == 1:
        return "1h"
    return f"{hops}h"


async def send_reply(mc, channel, sender, hops_label, first_band, path, second_band=None):
    if second_band:
        text = RESP_DUAL.format(
            sender      = sender,
            hops_label  = hops_label,
            first_band  = first_band,
            path        = path,
            second_band = second_band,
        )
    else:
        text = RESP_SINGLE.format(
            sender     = sender,
            hops_label = hops_label,
            first_band = first_band,
            path       = path,
        )
    await mc.send_channel_message(channel, text)
    print(f"  📤 Sent: {text}")


# ── Grace window timer ─────────────────────────────────────────
async def grace_timer(corr_key):
    """Wait GRACE seconds then fire the reply."""
    await asyncio.sleep(GRACE)

    async with corr_lock:
        entry = correlator.get(corr_key)
        if entry is None or entry["sent"]:
            return
        entry["sent"] = True

    print(f"\n[REPLY] Grace window expired for {entry['sender']}")
    await send_reply(
        entry["mc"],
        entry["channel"],
        entry["sender"],
        entry["hops_label"],
        entry["first_band"],
        entry["path"],
        entry["second_band"],   # None if only one band received
    )


# ── Message handler ────────────────────────────────────────────
async def handle_message(mc, band_name, p):
    try:
        text    = getattr(p, "text",     "").strip()
        sender  = getattr(p, "sender",   "unknown")
        hops    = getattr(p, "path_len", 0)
        path    = getattr(p, "path",     "")
        channel = getattr(p, "channel",  CHANNELS[0])
    except Exception as e:
        print(f"[{band_name}] ⚠️  Error reading message: {e}")
        return

    if channel not in CHANNELS:
        return

    if not text.lower().startswith("!ping"):
        return

    hops_label = build_hops_label(hops)
    corr_key   = (sender, hops, path)

    print(f"[{band_name}] #ping | {sender}: {text} (hops={hops}, path={path})")

    async with corr_lock:
        entry = correlator.get(corr_key)

        if entry is None:
            # ── First band to receive ──────────────────────────
            correlator[corr_key] = {
                "sender":      sender,
                "hops_label":  hops_label,
                "first_band":  band_name,
                "path":        path,
                "channel":     channel,
                "mc":          mc,
                "second_band": None,
                "sent":        False,
                "ts":          time.time(),
            }
            print(f"[{band_name}] ⏳ First band — waiting {GRACE}s...")
            asyncio.create_task(grace_timer(corr_key))

        elif not entry["sent"] and entry["second_band"] is None:
            # ── Second band arrives within grace window ────────
            entry["second_band"] = band_name
            print(f"[{band_name}] ✅ Second band confirmed — Bridge OK {band_name}")

        else:
            print(f"[{band_name}] ⏭️  Skipped — already processed")


# ── Band listener ──────────────────────────────────────────────
async def listen_band(band):
    name = band["name"]
    port = band["port"]
    baud = band["baud"]

    mc = MeshCore()
    print(f"[{name}] Connecting on {port}...")

    try:
        await mc.connect_serial(port, baud)
        print(f"[{name}] ✅ Connected on {port}")
    except Exception as e:
        print(f"[{name}] ❌ Failed to connect: {e}")
        return

    async for p in mc.messages():
        await handle_message(mc, name, p)


# ── Main ───────────────────────────────────────────────────────
async def main():
    print(f"\n🤖 {cfg['general']['node_name']} starting...")
    print(f"📡 Channels: {CHANNELS}")
    print(f"🔌 Bands: {[f\"{b['name']} on {b['port']}\" for b in BANDS]}")
    print(f"⏳ Grace window: {GRACE} seconds\n")

    await asyncio.gather(*[listen_band(b) for b in BANDS])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
        sys.exit(0)
