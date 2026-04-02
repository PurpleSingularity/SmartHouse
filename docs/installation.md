# Boobiki -- Installation & Running Guide

## Prerequisites

- **Python 3.13** or later
- **uv** package manager -- install via `pip install uv` or the [standalone installer](https://docs.astral.sh/uv/getting-started/installation/)
- All devices must be on the **same WiFi network**

## Installation

1. Clone or download the project:

   ```
   git clone <repository-url>
   ```

2. Navigate to the project directory:

   ```
   cd HomeProject
   ```

3. Install dependencies:

   ```
   uv sync
   ```

   This installs all runtime and dev dependencies from `pyproject.toml` into the `.venv`.

## Running the Server

Basic (using uvicorn directly):

```
uv run uvicorn boobiki.app:create_app --factory --host 0.0.0.0 --port 8000
```

Or via the entry point:

```
uv run python main.py
```

The server:

- Binds to `0.0.0.0:8000` by default (accessible from other devices on the LAN)
- Registers itself via mDNS as `_boobiki._tcp.local.`
- Serves the PWA at the root URL

## Accessing Boobiki

1. **On the server PC** -- open `http://localhost:8000` in a browser.

2. **On other devices** (phone, tablet, other PC) -- open `http://<server-ip>:8000` in a browser.
   - Find the server IP: run `ipconfig` (Windows) or `ip addr` (Linux) on the server machine.
   - Example: `http://192.168.1.100:8000`

3. **Install as PWA** (mobile) -- in the browser, tap "Add to Home Screen" for a native-like experience.

## Configuration

All settings are via environment variables with the `BOOBIKI_` prefix:

| Variable | Default | Description |
|---|---|---|
| `BOOBIKI_HOST` | `0.0.0.0` | Server bind address |
| `BOOBIKI_PORT` | `8000` | Server port |
| `BOOBIKI_DEVICE_NAME` | *(auto: hostname)* | How this server appears to other devices |
| `BOOBIKI_DATA_DIR` | `./data` | Where uploaded files are stored |
| `BOOBIKI_TRANSFER_TTL_HOURS` | `24` | Auto-delete transfers after N hours |

Example with custom settings:

```
BOOBIKI_PORT=9000 BOOBIKI_DEVICE_NAME="Living Room PC" uv run python main.py
```

Or create a `.env` file in the project root (pydantic-settings reads it automatically):

```
BOOBIKI_PORT=9000
BOOBIKI_DEVICE_NAME=Living Room PC
```

## Development

Run linter:

```
uv run ruff check src/
```

Run type checker:

```
uv run mypy src/
```

Run tests:

```
uv run pytest
```

Format code:

```
uv run ruff format src/
```

## File Storage

- Uploaded files are stored in `./data/transfers/<uuid>/<filename>`.
- Files are automatically cleaned up after 24 hours (configurable via `BOOBIKI_TRANSFER_TTL_HOURS`).
- The `data/` directory is gitignored.
- Files are stored with in-memory metadata and on-disk content. Restarting the server clears the transfer list, but files remain on disk until manual cleanup.

## Troubleshooting

### "Cannot connect from phone/other device"

- Ensure both devices are on the same WiFi network.
- Check Windows Firewall: allow inbound connections on port 8000 (TCP).
  - Windows: Settings > Windows Security > Firewall > Advanced Settings > Inbound Rules > New Rule > Port > TCP 8000 > Allow
- Try accessing by IP address, not hostname.

### "mDNS discovery not working"

- Windows Firewall may block UDP port 5353 (mDNS).
- Add firewall rule: allow inbound UDP on port 5353.
- This only affects server-to-server discovery. Browser clients connect directly via URL.

### "WebSocket disconnects on mobile"

- This is normal when the phone screen locks -- the OS suspends the browser.
- The app automatically reconnects when you return to it.
- The reconnection uses exponential backoff (1s, 2s, 4s... up to 15s).

### "Port already in use"

- Another process is using port 8000.
- Either stop that process or use a different port:

  ```
  BOOBIKI_PORT=8001 uv run python main.py
  ```

### "ModuleNotFoundError: No module named 'boobiki'"

- Run `uv sync` to install the package in development mode.
- The project uses a `src/` layout which requires the package to be installed.
