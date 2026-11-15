import asyncio


BLINK_INTERVAL_MS = 100
MQTT_BLINK_INTERVAL_MS = 500
RECONNECT_INTERVAL_MS = 10_000


async def sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


def update_status_led(led, wifi_connected, publisher=None):
    """Blink fast for Wi-Fi, slowly for MQTT, and stay off when ready."""
    if not wifi_connected:
        interval_ms = BLINK_INTERVAL_MS
    elif publisher is not None and not publisher.connected:
        interval_ms = MQTT_BLINK_INTERVAL_MS
    else:
        led.off()
        return BLINK_INTERVAL_MS
    led.value(not led.value())
    return interval_ms


async def connect_wifi(ssid, password, telemetry=None, publisher=None):
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
                interval_ms = update_status_led(status_led, True, publisher)
                await sleep_ms(interval_ms)
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

                interval_ms = update_status_led(status_led, False, publisher)
                print(".", end="")
                await sleep_ms(interval_ms)
    finally:
        status_led.off()


async def wifi_status_task(telemetry=None, wlan=None, publisher=None):
    """Show Wi-Fi/MQTT progress without starting a competing reconnect loop."""
    from machine import Pin
    if wlan is None:
        import network
        wlan = network.WLAN(network.STA_IF)
    led = Pin("LED", Pin.OUT)
    led.off()
    previous = None
    try:
        while True:
            connected = wlan.isconnected()
            if connected != previous:
                if telemetry is not None:
                    telemetry.emit("status", {"wifi_connected": connected})
                previous = connected
                print("Wi-Fi connected." if connected else "Wi-Fi disconnected.")
            interval_ms = update_status_led(led, connected, publisher)
            await sleep_ms(interval_ms)
    finally:
        led.off()


if __name__ == "__main__":
    test_ssid = input("Wi-Fi SSID: ")
    test_password = input("Wi-Fi password: ")

    try:
        asyncio.run(connect_wifi(test_ssid, test_password))
    except KeyboardInterrupt:
        print("\nWi-Fi test stopped.")
