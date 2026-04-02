# Boobiki Architecture

Boobiki is a personal LAN device hub for WiFi network interactions. It discovers devices on the local network via mDNS, connects browser clients over WebSocket, and mediates file transfers between any pair of devices. No internet connection required.

- **Server**: Python 3.13, FastAPI + Uvicorn
- **Client**: Vanilla JS PWA served by FastAPI
- **Discovery**: AsyncZeroconf / mDNS (automatic)
- **Network**: WiFi LAN only

## Tech Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.13 |
| Web framework | FastAPI + Uvicorn |
| Device discovery | AsyncZeroconf (mDNS) |
| Frontend | Vanilla HTML/CSS/JS (PWA) |
| Package manager | uv |
| Build backend | hatchling |
| Linter/formatter | ruff (py313, line-length 99) |
| Type checker | mypy (strict mode) |
| Tests | pytest + pytest-asyncio |

## Dependencies (5 runtime)

- fastapi >= 0.115
- uvicorn[standard] >= 0.34
- zeroconf >= 0.146
- python-multipart >= 0.0.20
- pydantic-settings >= 2.8

## Project Structure

```
HomeProject/
  pyproject.toml
  main.py                          # Entry point
  src/boobiki/
    __init__.py                    # Package version
    app.py                         # App factory, lifespan, router wiring
    config.py                      # Settings (Pydantic BaseSettings, env prefix BOOBIKI_)
    models.py                      # Device, Transfer dataclasses; DeviceType, TransferStatus enums
    devices.py                     # DeviceRegistry — in-memory dict[UUID, Device]
    discovery.py                   # AsyncZeroconf service registration + AsyncServiceBrowser
    ws.py                          # ConnectionManager — WebSocket tracking + broadcast
    transfers.py                   # TransferManager — file storage, streaming, cleanup
    routes/
      __init__.py
      health.py                    # GET /livez, GET /readyz
      devices.py                   # GET /api/devices
      transfers.py                 # POST /api/transfers, GET /api/transfers, GET /api/transfers/{id}/download
      ws.py                        # WebSocket /ws endpoint
  static/
    index.html, manifest.json, sw.js, app.js, style.css, icons/
  tests/
  data/transfers/                  # Runtime file storage (gitignored)
```

## Configuration

Settings via environment variables (prefix `BOOBIKI_`):

| Variable | Default | Description |
|---|---|---|
| BOOBIKI_HOST | 0.0.0.0 | Server bind address |
| BOOBIKI_PORT | 8000 | Server port |
| BOOBIKI_DEVICE_NAME | (hostname) | Device display name |
| BOOBIKI_DATA_DIR | ./data | File storage directory |
| BOOBIKI_TRANSFER_TTL_HOURS | 24 | Auto-cleanup after N hours |
| BOOBIKI_MDNS_SERVICE_TYPE | _boobiki._tcp.local. | mDNS service type |

## REST API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /livez | Liveness probe -- returns `{"status": "ok"}` |
| GET | /readyz | Readiness probe -- returns `{"status": "ok"}` |
| GET | /api/devices | List all connected devices |
| POST | /api/transfers | Upload file (multipart: sender_id, receiver_id, file) -- returns 201 |
| GET | /api/transfers?device_id={uuid} | List transfers for a device |
| GET | /api/transfers/{id}/download | Download a transferred file (StreamingResponse) |

## WebSocket Protocol (/ws)

### Connection Flow

1. Client connects to `ws://<host>:<port>/ws`
2. Server accepts the connection
3. Client sends: `{"type": "register", "name": "My Device"}`
4. Server responds: `{"type": "registered", "device_id": "<uuid>"}`
5. Connection stays open for push messages

### Server-Pushed Events

- `{"type": "device_joined", "device_id": "...", "name": "..."}` -- new device connected
- `{"type": "device_left", "device_id": "...", "name": "..."}` -- device disconnected
- `{"type": "transfer_ready", "transfer_id": "...", "filename": "...", "size": N, "sender_id": "..."}` -- file available for download

### Keepalive

- Client sends `{"type": "ping"}` every 30 seconds
- Server responds `{"type": "pong"}`

## Data Models

**Device** (dataclass, slots=True):

- `id`: UUID
- `name`: str
- `device_type`: DeviceType (`server` | `browser`)
- `ip`: str
- `port`: int
- `last_seen`: datetime

**Transfer** (dataclass, slots=True):

- `id`: UUID
- `filename`: str
- `size`: int
- `sender_id`: UUID
- `receiver_id`: UUID
- `status`: TransferStatus
- `created_at`: datetime
- `file_path`: str

Transfer statuses: `pending`, `uploading`, `ready`, `downloaded`, `expired`.

## Architecture Flows

### Device Discovery (Zeroconf mDNS)

1. On startup, server registers `_boobiki._tcp.local.` service with its IP, port, device_id, device_name
2. AsyncServiceBrowser listens for other Boobiki servers on the LAN
3. When a new server appears, BoobikiServiceHandler adds it to DeviceRegistry as DeviceType.SERVER
4. When a server disappears, it is removed from the registry

### Browser Client Connection

1. PWA opens WebSocket to `/ws`
2. Sends register message with device name
3. Server creates Device(type=BROWSER), adds to registry, broadcasts device_joined
4. Connection equals presence -- disconnect removes the device

### Device Registry (Two Sources)

- **mDNS**: discovers Boobiki server instances (DeviceType.SERVER)
- **WebSocket**: browser/PWA clients (DeviceType.BROWSER)
- Both feed into a unified in-memory `dict[UUID, Device]`

### File Transfer Flow

1. Sender selects target device in UI, picks a file
2. PWA sends POST /api/transfers (multipart: sender_id, receiver_id, file)
3. Server creates Transfer record, writes file to `data/transfers/{uuid}/filename`
4. Server sends WebSocket notification to receiver: transfer_ready
5. Receiver sees notification, clicks download
6. GET /api/transfers/{id}/download streams file via StreamingResponse
7. Transfer marked as downloaded. Expired transfers cleaned up hourly.

### PWA Architecture

- Single-page app served at `/` (FileResponse)
- Service worker at `/sw.js` (cache-first for static, network-only for API/WS)
- `manifest.json` enables "Add to Home Screen" on mobile
- WebSocket for real-time updates, XHR for upload progress
- Device ID stored in localStorage for session persistence

## Design Decisions

**No database.** In-memory dicts + disk storage. Personal project, single server, no persistence needed across restarts.

**Flat modules, not vertical slices.** Under 5000 lines -- feature-driven architecture is premature. Modules can be reorganized later.

**Server-mediated file transfer.** Files route through the server, not peer-to-peer. Simpler, works reliably on all WiFi networks.

**AsyncZeroconf over sync Zeroconf.** Sync Zeroconf blocks the event loop. AsyncZeroconf integrates natively with FastAPI's asyncio.
