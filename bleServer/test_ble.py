import asyncio
from bleak import BleakScanner

async def main():
    print("Escaneando BLE durante 30 segundos...")

    devices = await BleakScanner.discover(
        timeout=30.0,
        return_adv=True
    )

    print("Dispositivos encontrados:", len(devices))

    for device, adv in devices.values():
        name = adv.local_name or device.name or ""
        print(
            "Nombre:", repr(name),
            "| Dirección:", device.address
        )

asyncio.run(main())