"""Versioned, bounded JSON frames; only explicit input messages are accepted."""
import json
import math
import re
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
    from .displays import valid_point
    if 'point' in message and not valid_point(message['point']):
        return False
    def token(key, length=32):
        return isinstance(message.get(key), str) and re.fullmatch('[0-9a-f]{'+str(length)+'}', message[key]) is not None
    if 'flow' in message and not token('flow'):
        return False
    kind = message.get("type")
    if kind == 'screen':
        from .displays import validate_screen
        return bool(validate_screen(message.get('screen')))
    if kind == 'layout':
        from .topology import validate_layout
        try:
            validate_layout(message.get('layout'))
            return True
        except (ValueError, TypeError):
            return False
    if kind == 'route':
        return token('flow') and token('target', 64) and message.get('edge') in SIDES and number(message.get('position'), 0, 1)
    if kind == 'standby':
        return token('flow')
    if kind == 'paste_ready':
        return type(message.get('ready')) is bool
    if kind == 'clipboard_action':
        return token('flow') and message.get('action') in {'copy', 'paste'}
    if kind == 'file_offer':
        names = message.get('names')
        return (token('offer') and type(message.get('count')) is int and 1 <= message['count'] <= 4096
                and isinstance(names, list) and 1 <= len(names) <= 12
                and all(isinstance(n, str) and 1 <= len(n) <= 255 and not any(ord(c)<32 for c in n) for n in names))
    if kind == 'file_clear':
        return token('offer')
    if kind == 'file_request':
        return token('offer') and token('request')
    if kind == 'file_error':
        return token('request') and isinstance(message.get('message'), str) and len(message['message']) <= 160
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

