# ATS-Mini Communication SDK

CBOR-RPC communication library for ATS-Mini radio device.

## Installation

```bash
pip install -e .
```

With testing:
```bash
pip install -e ".[test]"
```

## Components

- **SerialRpcClient** - Serial port RPC communication
- **WebSocketRpcClient** - WebSocket RPC communication  
- **Framing utilities** - CBOR frame encoding/decoding

## Testing

```bash
pytest
```
