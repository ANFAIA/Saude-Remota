import asyncio
from bleak import BleakScanner, BleakClient

ESP32_ADDRESS = "94:3C:C6:32:F0:6A"

async def main():
    print("Buscando ESP32...")

    device = await BleakScanner.find_device_by_address(
        ESP32_ADDRESS,
        timeout=20.0
    )

    if device is None:
        print("NO ENCONTRADO")
        return

    print("Encontrado:", device.address)
    print("Intentando conectar...")

    try:
        async with BleakClient(device, timeout=30.0) as client:
            print("CONECTADO:", client.is_connected)

            print("Servicios GATT:")
            for service in client.services:
                print(service)

    except Exception as e:
        print("ERROR:")
        print(type(e).__name__)
        print(repr(e))

asyncio.run(main())