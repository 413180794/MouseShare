import struct

import pytest

from mouseshare.protocol import Decoder, ProtocolError, frame, valid_input


def test_fragmented_and_combined_frames():
    messages = [{"type": "key", "key": 4, "down": True}, {"type": "move", "dx": 7, "dy": -9}]
    raw = b"".join(map(frame, messages))
    decoder = Decoder()
    output = []
    for byte in raw:
        output += decoder.feed(bytes([byte]))
    assert output == messages
    assert Decoder().feed(raw) == messages


@pytest.mark.parametrize("raw", [struct.pack("!I", 0), struct.pack("!I", 16385),
                                struct.pack("!I", 2) + b"[]", struct.pack("!I", 1) + b"{"])
def test_bad_frames(raw):
    with pytest.raises(ProtocolError):
        Decoder().feed(raw)


@pytest.mark.parametrize("message", [
    {"type": "key", "key": True, "down": True}, {"type": "key", "key": 4, "down": 1},
    {"type": "move", "dx": float("nan"), "dy": 0}, {"type": "move", "dx": 10000, "dy": 0},
    {"type": "enter", "edge": "north", "position": 0.5},
    {"type": "enter", "edge": "left", "position": -0.5},
    {"type": "button", "button": 8, "down": True}, {"type": "execute", "command": "anything"},
])
def test_input_validation(message):
    assert not valid_input(message)

