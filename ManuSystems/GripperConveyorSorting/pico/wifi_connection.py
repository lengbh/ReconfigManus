import asyncio


BLINK_INTERVAL_MS = 250
RECONNECT_INTERVAL_MS = 10_000


async def sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


async def connect_wifi(ssid, password, telemetry=None):
    import network
    from machine import Pin

    wlan = network.WLAN(network.STA_IF)
    status_led = Pin("LED", Pin.OUT)
    status_led.off()
    wlan.active(True)

    was_connected = wlan.isconnected()
    if telemetry is not None:
        telemetry.emit("status", {"wifi_connected": was_connected})
    if was_connected:
        print("Wi-Fi connected:", wlan.ifconfig()[0])

    # Physical tasks keep running while this task blinks and retries forever.
    try:
        while True:
            if wlan.isconnected():
                if not was_connected:
                    print("\nWi-Fi connected:", wlan.ifconfig()[0])
                    if telemetry is not None:
                        telemetry.emit("status", {"wifi_connected": True})
                was_connected = True
                status_led.off()
                await sleep_ms(BLINK_INTERVAL_MS)
                continue

            if was_connected:
                print("Wi-Fi disconnected.")
                if telemetry is not None:
                    telemetry.emit("status", {"wifi_connected": False})
            was_connected = False

            if ssid:
                print("Connecting to Wi-Fi", end="")
                try:
                    wlan.disconnect()
                    wlan.connect(ssid, password)
                except Exception as error:
                    print("\nWi-Fi connection attempt failed:", error)
            else:
                print("Wi-Fi SSID is empty.")

            retry_checks = RECONNECT_INTERVAL_MS // BLINK_INTERVAL_MS
            for _ in range(retry_checks):
                if wlan.isconnected():
                    break

                status_led.value(not status_led.value())
                print(".", end="")
                await sleep_ms(BLINK_INTERVAL_MS)
    finally:
        status_led.off()


async def wifi_status_task(telemetry=None, wlan=None):
    """Observe MQTT-owned Wi-Fi without starting a competing reconnect loop."""
    from machine import Pin
    if wlan is None:
        import network
        wlan = network.WLAN(network.STA_IF)
    led = Pin("LED", Pin.OUT)
    previous = None
    try:
        while True:
            connected = wlan.isconnected()
            if connected != previous:
                if telemetry is not None:
                    telemetry.emit("status", {"wifi_connected": connected})
                previous = connected
                print("Wi-Fi connected." if connected else "Wi-Fi disconnected.")
            if connected:
                led.off()
            else:
                led.value(not led.value())
            await sleep_ms(BLINK_INTERVAL_MS)
    finally:
        led.off()


if __name__ == "__main__":
    test_ssid = input("Wi-Fi SSID: ")
    test_password = input("Wi-Fi password: ")

    try:
        asyncio.run(connect_wifi(test_ssid, test_password))
    except KeyboardInterrupt:
        print("\nWi-Fi test stopped.")
