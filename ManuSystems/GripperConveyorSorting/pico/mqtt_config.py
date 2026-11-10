"""Edit MQTT_HOST to enable MQTT; local credentials live in secrets.py."""

try:
    import secrets as _secrets
except ImportError:
    _secrets = None

WIFI_SSID = getattr(_secrets, "WIFI_SSID", "")
WIFI_PASSWORD = getattr(_secrets, "WIFI_PASSWORD", "")
MQTT_USER = getattr(_secrets, "MQTT_USER", None)
MQTT_PASSWORD = getattr(_secrets, "MQTT_PASSWORD", None)

# Mosquitto is not set up yet. Use its numeric LAN IPv4 address, not localhost.
MQTT_HOST = ""
MQTT_PORT = 1883
MQTT_CLIENT_ID_PREFIX = "gripper-conveyor"
TOPIC_PREFIX = "gripper_conveyor"
MQTT_KEEPALIVE = 30
MQTT_RETRY_MS = 5000
MQTT_CONNECT_TIMEOUT_MS = 15000
MQTT_PUBLISH_TIMEOUT_MS = 2000

TELEMETRY_HZ = 20
TELEMETRY_EVENT_CAPACITY = 32
COMMAND_INTERVAL_MS = 20
SERVO_MOVE_MS = 1500
BASE_LOAD_ANGLE = 180
BASE_DROP_ANGLE = 12
CLAW_OPEN_ANGLE = 90
CLAW_CLOSED_ANGLE = 180

# Measured travel from fully open toward fully closed. Until calibrated, send
# normalized closure and servo angle, with travel_mm=null.
CLAW_STROKE_MM = None
