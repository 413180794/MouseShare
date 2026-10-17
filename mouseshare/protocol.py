"""Versioned, bounded JSON frames; only explicit input messages are accepted."""
import json
import math
import struct

VERSION = 1
DISCOVERY_PORT = 24871
INPUT_PORT = 24872
MULTICAST_GROUP = "239.255.77.77"
MAX_FRAME = 16384
SIDES = {"left", "right", "top", "bottom"}
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


class ProtocolError(ValueError):
    pass


def frame(message: dict) -> bytes:
    payload = json.dumps(message, separators=(",", ":"), allow_nan=False).encode()
    if not 0 < len(payload) <= MAX_FRAME:
        raise ProtocolError("Frame too large")
    return struct.pack("!I", len(payload)) + payload


def decode(payload: bytes) -> dict:
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("Invalid JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ProtocolError("Expected typed object")
    return value


class Decoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= 4:
            size = struct.unpack("!I", self.buffer[:4])[0]
            if not 0 < size <= MAX_FRAME:
                raise ProtocolError("Invalid frame length")
            if len(self.buffer) < size + 4:
                break
            messages.append(decode(bytes(self.buffer[4:4 + size])))
            del self.buffer[:4 + size]
        if len(self.buffer) > MAX_FRAME + 4:
            raise ProtocolError("Buffer limit exceeded")
        return messages


def number(value, lo, hi):
    return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi


def valid_input(message):
    kind = message.get("type")
    if kind == "move":
        return number(message.get("dx"), -8192, 8192) and number(message.get("dy"), -8192, 8192)
    if kind == "key":
        return type(message.get("key")) is int and 4 <= message["key"] <= 231 and type(message.get("down")) is bool
    if kind == "button":
        return type(message.get("button")) is int and 1 <= message["button"] <= 5 and type(message.get("down")) is bool
    if kind == "scroll":
        return number(message.get("dx"), -100, 100) and number(message.get("dy"), -100, 100)
    if kind == "enter":
        return message.get("edge") in SIDES and number(message.get("position"), 0, 1)
    if kind == "return":
        return "position" not in message or number(message["position"], 0, 1)
    return kind in {"entered", "release", "ping", "pong", "blocked", "available"}

