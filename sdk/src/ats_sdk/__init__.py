"""ATS-Mini CBOR-RPC Communication SDK."""

from .rpc import SerialRpcClient, WebSocketRpcClient
from .framing import SWITCH_BYTE, decode_frame, encode_frame

__all__ = [
    "SerialRpcClient",
    "WebSocketRpcClient",
    "SWITCH_BYTE",
    "encode_frame",
    "decode_frame",
]

__version__ = "0.1.0"
