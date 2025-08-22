import asyncio
from bleak import BleakScanner

async def main():
    print("🔎 Escaneando BLE 12 s…")
    devs = await BleakScanner.discover(timeout=12.0)
    if not devs:
        print("No se detectó ningún dispositivo BLE.")
        return
    for d in devs:
        # bleak 0.22.x: name y address están siempre
        print(f"- {d.name!r:25}  {d.address}")
        # algunos backends exponen uuids en metadata
        md = getattr(d, "metadata", {}) or {}
        uuids = md.get("uuids") or []
        if uuids:
            print("   uuids:", uuids)

if __name__ == "__main__":
    asyncio.run(main())
