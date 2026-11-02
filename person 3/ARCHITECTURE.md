Client
   ↓
Central Coordinator
   ├── API Layer
   ├── Peer Registry
   ├── Matchmaker
   ├── Scheduler
   ├── Signaling Gateway
   └── Trust & Accounting
            ↓
       PostgreSQL
            ↓
       Worker Daemon
       ├── GPU Monitor
       ├── Sandbox Engine
       ├── Task Executor
       └── Streaming Engine
            ↓
       NVIDIA GPU


       p2p path:Client
   ↕
WebRTC / ICE / STUN / TURN
   ↕
Worker