Optimized CBOR-RPC frame encoding to use persistent buffers in RemoteState, eliminating frequent heap allocations for stats events and large responses like settings.get
