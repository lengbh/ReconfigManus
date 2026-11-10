"""Bounded synchronous hand-off from control tasks to the MQTT publisher.

Progress coalesces; important transitions and part detections use a bounded FIFO.
Reconnection discards historical transitions and republishes current snapshots.
"""
import time


def ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def ticks_diff(new, old):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(new, old)
    return new - old


class Telemetry:
    TOPICS = ("rotation/state", "claw/state", "conveyor/state", "placement/state", "part/event", "status")

    def __init__(self, publish_hz=20, event_capacity=32, device_id=None, topics=None, clock_ms=None):
        if not 0 < publish_hz <= 1000:
            raise ValueError("publish_hz must be between 0 and 1000")
        if event_capacity < 1:
            raise ValueError("event_capacity must be positive")
        self.publish_interval_ms = max(1, int(round(1000 / publish_hz)))
        self.event_capacity = int(event_capacity)
        self.device_id = device_id or "pico"
        self.topics = tuple(topics) if topics is not None else self.TOPICS
        self._latest = {}
        self._pending = {}
        self._events = []
        self._sequence = 0
        self._clock_ms = clock_ms or ticks_ms
        self._last_tick = self._clock_ms()
        self._uptime_ms = 0
        self.dropped_events = 0

    def emit(self, topic, payload, event=None, force=False):
        """Merge/record a state or event without waiting for network I/O.

        Reserved envelope fields are generated here. Producers on the same
        state topic may update separate fields without erasing one another.
        """
        if topic not in self.topics:
            raise ValueError("Unknown telemetry topic: " + str(topic))
        if not isinstance(payload, dict):
            raise TypeError("Telemetry payload must be a dictionary")
        now = self._clock_ms()
        self._uptime_ms += max(0, ticks_diff(now, self._last_tick))
        self._last_tick = now
        self._sequence += 1
        is_event_topic = topic.endswith("/event")
        message = {} if is_event_topic else dict(self._latest.get(topic, {}))
        message.update(payload)
        message.update(schema_version=1, device_id=self.device_id, seq=self._sequence,
                       uptime_ms=self._uptime_ms, event=event or "state")
        if not is_event_topic:
            self._latest[topic] = message
            self._pending[topic] = message["seq"]
        if force or is_event_topic:
            if len(self._events) >= self.event_capacity:
                self._events.pop(0)
                self.dropped_events += 1
            self._events.append((topic, message))
        return dict(message)

    def next_pending(self):
        """Return (topic, message) or None, retaining data until acknowledged."""
        if self._events:
            topic, message = self._events[0]
            return topic, dict(message)
        if not self._pending:
            return None
        topic = min(self._pending, key=lambda item: self._pending[item])
        return topic, dict(self._latest[topic])

    def acknowledge(self, topic, seq):
        """Acknowledge one version without dropping newer producer data."""
        for index, (event_topic, message) in enumerate(self._events):
            if event_topic == topic and message["seq"] == seq:
                self._events.pop(index)
                break
        if self._pending.get(topic) == seq:
            del self._pending[topic]

    def mark_all_pending(self, clear_events=True):
        """Republish current snapshots after reconnect, without stale replay."""
        if clear_events:
            self._events.clear()
        self._pending = {topic: message["seq"] for topic, message in self._latest.items()}

    def snapshot(self):
        return {topic: dict(message) for topic, message in self._latest.items()}
