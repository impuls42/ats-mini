def encode_frame(payload: bytes) -> bytes:
    length = len(payload)
    return length.to_bytes(4, "big") + payload


def decode_frame(message: bytes) -> bytes:
    if len(message) < 4:
        raise ValueError("Frame too short")
    length = int.from_bytes(message[:4], "big")
    payload = message[4:]
    if length != len(payload):
        raise ValueError("Length mismatch")
    return payload
