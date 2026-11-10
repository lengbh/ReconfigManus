"""Publish controller state without making hardware tasks wait on the network.

The bundled mqtt_as client owns Wi-Fi and broker reconnection. This adapter
publishes each packet once: stale motion packets must not be retried after an
outage, because the fresh state snapshot supersedes them.
"""
import asyncio
import json


async def sleep_ms(duration_ms):
    if hasattr(asyncio, "sleep_ms"):
        await asyncio.sleep_ms(duration_ms)
    else:
        await asyncio.sleep(duration_ms / 1000)


def _bytes(value):
    if value is None:
        return b""
    return value if isinstance(value, bytes) else str(value).encode()


def _ipv4_address(value):
    parts = value.split(".")
    return len(parts) == 4 and all(
        part.isdigit() and 0 <= int(part) <= 255 for part in parts
    )


def _load_client():
    from mqtt_as import MQTTClient, MQTT_base, config

    class StateMQTTClient(MQTTClient):
        """Use upstream reconnection but discard interrupted publications."""

        def __init__(self, options):
            self._publisher_reader = None
            self._publisher_reconnector = None
            super().__init__(options)

        async def _handle_msg(self):
            self._publisher_reader = asyncio.current_task()
            try:
                await super()._handle_msg()
            finally:
                self._publisher_reader = None

        async def _keep_connected(self):
            self._publisher_reconnector = asyncio.current_task()
            try:
                await super()._keep_connected()
            finally:
                self._publisher_reconnector = None

        async def publish(self, topic, msg, retain=False, qos=0):
            if not self.isconnected():
                raise OSError("MQTT disconnected")
            try:
                return await MQTT_base.publish(self, topic, msg, retain, qos)
            except OSError:
                self._reconnect()
                raise

        def close(self):
            self._has_connected = False
            self._isconnected = False
            self._in_connect = False
            tasks = list(self._tasks)
            tasks.extend((self._publisher_reader, self._publisher_reconnector))
            for task in tasks:
                if task is not None:
                    task.cancel()
            self._tasks.clear()
            super().close()

    return StateMQTTClient, config


class MqttPublisher:
    """One background publisher; no network work is done by emit() callers.

    client_factory/client_defaults are injectable for host-side tests. The
    normal controller uses the pinned mqtt_as module bundled in this folder.
    """

    def __init__(self, telemetry, settings, client_factory=None, client_defaults=None):
        self.telemetry = telemetry
        self.settings = settings
        self.client = None
        self.connected = False
        self._closed = False
        self._needs_snapshot = True
        self._connection_epoch = 0
        self._was_online = False
        self.disabled_reason = None
        self.enabled = False
        self.owns_wifi = False
        self._factory = client_factory
        self._defaults = client_defaults or {}
        self._last_sent = {}
        self._configure()

    def _configure(self):
        self.host = str(getattr(self.settings, "MQTT_HOST", "") or "").strip()
        self.prefix = str(getattr(self.settings, "TOPIC_PREFIX", "gripper_conveyor")).strip("/")
        self.retry_ms = max(100, int(getattr(self.settings, "MQTT_RETRY_MS", 5000)))
        self.publish_timeout_ms = max(100, int(getattr(self.settings, "MQTT_PUBLISH_TIMEOUT_MS", 2000)))
        self.connect_timeout_ms = max(100, int(getattr(self.settings, "MQTT_CONNECT_TIMEOUT_MS", 15000)))
        self.interval_ms = max(1, int(self.telemetry.publish_interval_ms))
        if not self.host:
            self.disabled_reason = "broker_not_configured"
        elif not _ipv4_address(self.host):
            # mqtt_as resolves hostnames synchronously. Numeric LAN addresses
            # avoid a DNS lookup pausing the cooperative hardware scheduler.
            self.disabled_reason = "broker_requires_numeric_ipv4"
        elif not getattr(self.settings, "WIFI_SSID", ""):
            self.disabled_reason = "wifi_not_configured"
        elif not self.prefix or "+" in self.prefix or "#" in self.prefix:
            self.disabled_reason = "invalid_topic_prefix"
        else:
            try:
                port = int(getattr(self.settings, "MQTT_PORT", 1883))
                if not 1 <= port <= 65535:
                    raise ValueError("Invalid MQTT port")
                self.port = port
                if self._factory is None:
                    self._factory, self._defaults = _load_client()
                self.client = self._factory(self._options())
                self.enabled = True
                self.owns_wifi = True
            except (ImportError, AttributeError, ValueError, OSError):
                self.disabled_reason = "mqtt_client_unavailable_or_invalid_config"
        if self.disabled_reason:
            print("MQTT disabled:", self.disabled_reason)
            self.telemetry.emit("status", {
                "online": False, "mqtt_connected": False,
                "mqtt_enabled": False, "reason": self.disabled_reason,
            }, event="offline", force=True)

    def _options(self):
        options = dict(self._defaults)
        prefix = getattr(self.settings, "MQTT_CLIENT_ID_PREFIX", "gripper-conveyor")
        device_id = getattr(self.telemetry, "device_id", None) or prefix
        will = {
            "schema_version": 1, "device_id": device_id,
            # A broker-generated will has no controller sample time or seq.
            "seq": None, "uptime_ms": None, "event": "offline",
            "online": False, "mqtt_connected": False,
            "reason": "connection_lost",
        }
        options.update({
            "server": self.host, "port": self.port,
            "client_id": _bytes(device_id),
            "ssid": self.settings.WIFI_SSID,
            "wifi_pw": getattr(self.settings, "WIFI_PASSWORD", ""),
            "user": _bytes(getattr(self.settings, "MQTT_USER", None)),
            "password": _bytes(getattr(self.settings, "MQTT_PASSWORD", None)),
            "keepalive": int(getattr(self.settings, "MQTT_KEEPALIVE", 30)),
            "clean_init": True, "clean": True, "queue_len": 0,
            "mqttv5": False,
            "response_time": max(1, self.publish_timeout_ms // 1000),
            "max_repubs": 0,
            "will": (_bytes(self.prefix + "/status"), json.dumps(will).encode(), True, 0),
            "wifi_coro": self._link_changed,
            "connect_coro": self._broker_connected,
            "subs_cb": lambda *_: None,
        })
        return options

    async def _link_changed(self, connected):
        if not connected:
            self.connected = False
            self._needs_snapshot = True
            self._connection_epoch += 1
            self.telemetry.emit("status", {
                "online": False, "mqtt_connected": False,
                "mqtt_enabled": True, "reason": "reconnecting",
            }, event="offline", force=True)

    async def _broker_connected(self, client):
        if not self.connected:
            self._needs_snapshot = True
        self.connected = True

    async def _publish(self, suffix, message):
        epoch = self._connection_epoch
        retained = suffix != "part/event"
        qos = 0 if retained else 1
        try:
            await asyncio.wait_for(
                self.client.publish(
                    _bytes(self.prefix + "/" + suffix),
                    json.dumps(message).encode(), retain=retained, qos=qos,
                ),
                self.publish_timeout_ms / 1000,
            )
            return epoch == self._connection_epoch and self.client.isconnected()
        except (OSError, asyncio.TimeoutError):
            self.connected = False
            self._needs_snapshot = True
            if hasattr(self.client, "_reconnect"):
                self.client._reconnect()
            return False

    async def _refresh_snapshot(self):
        # Do not replay old trajectories or NFC events after an outage.
        self.telemetry.mark_all_pending(clear_events=True)
        self._last_sent.clear()
        online = self.telemetry.emit("status", {
            "online": True, "mqtt_connected": True,
            "mqtt_enabled": True, "reason": "connected",
        }, event="online", force=False)
        if not await self._publish("status", online):
            return False
        self.telemetry.acknowledge("status", online["seq"])
        self._last_sent["status"] = online["seq"]
        self._needs_snapshot = False
        return True

    async def run(self):
        try:
            if not self.enabled:
                while not self._closed:
                    await sleep_ms(1000)
                return
            # Only the first connection is made here. mqtt_as starts its own
            # reconnection task after it succeeds, so there is one Wi-Fi owner.
            established = False
            while not self._closed and not established:
                try:
                    await asyncio.wait_for(self.client.connect(), self.connect_timeout_ms / 1000)
                    established = True
                    self.connected = self.client.isconnected()
                    self._needs_snapshot = True
                except (OSError, asyncio.TimeoutError):
                    self.connected = False
                    if hasattr(self.client, "_in_connect"):
                        self.client._in_connect = False
                    if hasattr(self.client, "_close"):
                        self.client._close()
                    print("MQTT connection retry; local control continues.")
                    await sleep_ms(self.retry_ms)

            while not self._closed:
                self.connected = self.client.isconnected()
                if not self.connected:
                    self._needs_snapshot = True
                    await sleep_ms(min(self.retry_ms, 250))
                    continue
                if self._needs_snapshot and not await self._refresh_snapshot():
                    await sleep_ms(min(self.retry_ms, 250))
                    continue

                # At most one packet per topic in each reporting period. Force
                # events and live samples can share a topic, but cannot cause a
                # burst of repeated updates on that topic.
                sent_topics = set()
                for _ in range(8):
                    pending = self.telemetry.next_pending()
                    if pending is None:
                        break
                    suffix, message = pending
                    if suffix in sent_topics:
                        break
                    seq = message["seq"]
                    if seq <= self._last_sent.get(suffix, -1):
                        self.telemetry.acknowledge(suffix, seq)
                        continue
                    if not await self._publish(suffix, message):
                        break
                    self.telemetry.acknowledge(suffix, seq)
                    self._last_sent[suffix] = seq
                    sent_topics.add(suffix)
                await sleep_ms(self.interval_ms)
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.connected = False
        if self.client is not None:
            try:
                self.client.close()
            except OSError:
                pass
