# TempAil REST API

REST API for [tempail.com](https://tempail.com) temporary email. Uses Selenium to automate the browser, Redis to cache inbox data, and a two-service architecture.

## Architecture

```
Client  →  Flask API (:5050)  →  Browser service (:5051)  →  tempail.com
                ↓
             Redis (:6379)
```

| Service | Port | Role |
|---------|------|------|
| **api** | 5050 | Public REST API |
| **browser** | 5051 | Selenium automation (internal) |
| **redis** | 6379 | Session and email cache |

---

## Design and implementation

### Why this architecture?

[tempail.com](https://tempail.com) is a JavaScript-heavy site with bot protection (Cloudflare / reCAPTCHA). There is no stable public API to create inboxes or read mail without a real browser session. The project therefore combines **browser automation**, a **REST API**, and **Redis caching** instead of a single monolithic script.

The work is split into three parts so each component has a clear job and can be deployed or scaled independently.

### Role of each component

#### API service (`app/`, port 5050)

The **public face** of the system. Clients only talk to this service.

Responsibilities:
- Expose the required REST endpoints (`/api/email`, `/api/inbox`, `/api/email/<id>`, `/api/email/refresh`, `/api/health`)
- Return JSON responses and map domain errors to HTTP status codes
- Orchestrate calls to the browser service when fresh data from tempail is needed
- Read and write cached data in Redis so repeated requests are fast and email bodies can be fetched by `id`

The API service **does not** run Chrome or Selenium. It stays lightweight and stateless aside from Redis.

#### Browser service (`browser_service/`, port 5051)

The **automation layer**. Internal only — not meant for direct client use.

Responsibilities:
- Keep one long-lived Chrome session open to tempail.com
- Navigate the page, read the current temp address, refresh inbox, open individual messages
- Expose a small internal HTTP API (`/internal/email`, `/internal/inbox`, etc.) consumed by the API service
- Handle page load timeouts, missing DOM elements, stale sessions, and CAPTCHA waits

Selenium is isolated here because it is slow, memory-heavy, and holds session state (cookies, `oturum`, open tabs). Crashes or restarts in Chrome should not take down the public API process.

#### Redis (port 6379)

The **cache and lookup store** between the API and the browser.

Responsibilities:
- Store the current session metadata (`email`, `oturum`)
- Cache inbox summaries after each `/api/inbox` call
- Cache full email content after `/api/email/<id>` is fetched once
- Enable `/api/email/<id>` to resolve messages by stable `id` without re-scraping the full body every time

Redis was chosen because the task explicitly requires caching emails by id, and tempail inbox rows are easier to reference from the API once they are stored with a known key.

### Approaches used

| Area | Approach | Reason |
|------|----------|--------|
| **Browser automation** | Selenium + real Chrome | tempail renders content in the browser; DOM selectors (`#eposta_adres`, inbox rows) are the reliable source of truth |
| **Service split** | API ↔ HTTP ↔ Browser service | Separates fast JSON API from slow/stateful browser work; matches Docker layout (two containers + Redis) |
| **API framework** | Flask | Simple REST over JSON, minimal boilerplate, easy to run locally and in Docker |
| **Caching** | Redis with TTL | Fast reads by email `id`; avoids clicking through inbox on every `/api/email/<id>` request |
| **Email lookup** | Layered resolution | 1) Redis full body → 2) Redis inbox → 3) live browser inbox → 4) scrape body and cache |
| **Browser session** | Singleton `BrowserManager` | tempail session lives in one Chrome instance; reusing it avoids re-navigation and repeated CAPTCHAs |
| **Concurrency** | `threaded=False` on browser service | Selenium WebDriver is not thread-safe; one request at a time prevents race conditions on the shared driver |
| **CAPTCHA** | Detect challenge page + poll up to 120s | tempail blocks bots; local dev opens visible Chrome so a human can solve reCAPTCHA when needed |
| **Errors** | Typed exceptions → HTTP codes | `EMAIL_NOT_FOUND` → 404, `CAPTCHA_BLOCKED` → 429, `BROWSER_CRASH` → 503 |
| **Configuration** | Separate `app/config.py` and `browser_service/config.py` | Each service only loads env vars it needs (Redis/URL vs Chrome/Selenium settings) |
| **Deployment** | Docker Compose (3 services) | API image is slim; browser image includes Chromium; Redis is a standard sidecar |

### Alternatives considered

**Playwright instead of Selenium** — viable, but Selenium was chosen for straightforward real-Chrome control and wide familiarity. Both require a browser process either way.

**Single process (API + Selenium in one app)** — simpler locally, but couples API uptime to Chrome crashes and makes Docker images heavier. The split keeps responsibilities clear.

**Direct HTTP to tempail internal APIs** — tempail exposes endpoints like `/api/kontrol/`, but they require session cookies from a passed bot check. A browser bootstrap is still needed; pure HTTP clients fail without that session.

**No Redis** — possible for a minimal demo, but `/api/email/<id>` would require re-scraping the inbox or message body on every request, and ids would not persist across API restarts.

### Data flow example

```
GET /api/email/<id>
    │
    ├─► Redis: full email with body cached?  → return immediately
    │
    ├─► Redis: inbox entry with this id?   → ask browser for body only
    │
    └─► Browser: fetch live inbox            → find row, click, extract body
                                              → save to Redis → return JSON
```

---

## Quick start manually

Run everything on your machine (no Docker). You need **Python 3.12+**, **Google Chrome**, and **Redis** on the host.

### 1. Check Redis on the host

Redis must be running before the API starts.

```bash
# Is Redis installed and running?
redis-cli ping
# Expected: PONG
```

If you get `Could not connect`:

```bash
# macOS (Homebrew)
brew install redis
brew services start redis

# Or run in foreground
redis-server
```

Default URL used by the app: `redis://localhost:6379/0`

### 2. Create venv and install packages

```bash
cd /path/to/test-task

python3 -m venv venv
source venv/bin/activate

pip install -r requirements-api.txt -r requirements-browser.txt
```

### 3. Run two services (two terminals)

Keep Redis running from step 1.

**Terminal 1 — browser service** (Chrome opens here; solve CAPTCHA in this window if it appears):

```bash
source venv/bin/activate
HEADLESS=false python run_browser_service.py
```

**Terminal 2 — API**:

```bash
source venv/bin/activate
python run.py
```

| Service | URL |
|---------|-----|
| API | http://localhost:5050 |
| Browser (internal) | http://localhost:5051 |
| Redis | localhost:6379 |

### 4. Verify everything works

```bash
# Browser service
curl http://localhost:5051/health

# API + Redis + browser
curl http://localhost:5050/api/health

# Get temp email (may take up to 120s on first call; solve CAPTCHA in Chrome if needed)
curl http://localhost:5050/api/email

curl http://localhost:5050/api/inbox
```

Expected health response:

```json
{
  "status": "ok",
  "redis": "connected",
  "browser_service": "connected"
}
```

---

**Requirements:** Docker and Docker Compose

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

Services start on:
- API: `http://localhost:5050`
- Browser service: `http://localhost:5051` (internal)
- Redis: `localhost:6379`

Check health:

```bash
curl http://localhost:5050/api/health
```

**Before starting Docker:** stop local services if they already use ports `5050`, `5051`, or `6379`:

```bash
# Ctrl+C in terminals running run.py and run_browser_service.py
```

Docker images use slim dependency files (`requirements-api.txt`, `requirements-browser.txt`) — not the full local `requirements.txt` from `pip freeze`.

### Docker troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `port is already allocated` | Local `run.py` / Redis still running | Stop local processes, then `docker compose up` |
| `Cannot connect to Docker daemon` | Docker Desktop not started | Start Docker Desktop |
| `browser_service: disconnected` | Browser container not healthy yet | Wait 15–30s, retry `/api/health` |
| `CAPTCHA_BLOCKED` in Docker | Headless Chrome can't solve reCAPTCHA | Run browser service locally with `HEADLESS=false` instead |

Test after startup:

```bash
curl http://localhost:5050/api/health
curl http://localhost:5050/api/email    # may take 60–120s; may fail with CAPTCHA in Docker
curl http://localhost:5050/api/inbox
```

---

## Quick start with Docker

All responses are JSON. Base URL: `http://localhost:5050/api`

### `GET /api/health`

Check Redis and browser service connectivity.

```bash
curl http://localhost:5050/api/health
```

```json
{
  "status": "ok",
  "redis": "connected",
  "browser_service": "connected"
}
```

---

### `GET /api/email`

Returns the current temporary email address.

```bash
curl http://localhost:5050/api/email
```

```json
{ "email": "example@necub.com" }
```

**Note:** First call may take up to 60–120s while Chrome loads tempail.com.

---

### `GET /api/inbox`

Returns received emails. Each message includes an **`id`** used by `/api/email/<id>`.

```bash
curl http://localhost:5050/api/inbox
```

```json
{
  "emails": [
    {
      "id": "a1b2c3d4e5f6",
      "sender": "noreply@service.com",
      "subject": "Verify your account",
      "time": "2 min ago"
    }
  ],
  "count": 1
}
```

If `count` is `0`, no mail has arrived yet — send an email to the address from `/api/email`, wait, and call again.

---

### `GET /api/email/<id>`

Returns full email content (sender, subject, time, body).

Use the `id` from `/api/inbox`:

```bash
curl http://localhost:5050/api/email/a1b2c3d4e5f6
```

```json
{
  "id": "a1b2c3d4e5f6",
  "sender": "noreply@service.com",
  "subject": "Verify your account",
  "time": "2 min ago",
  "body": "Click here to verify..."
}
```

---

### `POST /api/email/refresh`

Generates a new temporary email and clears cached inbox.

```bash
curl -X POST http://localhost:5050/api/email/refresh
```

```json
{
  "email": "newaddress@necub.com",
  "message": "New temporary email generated"
}
```

---

## Typical workflow

```bash
# 1. Get temp address
curl http://localhost:5050/api/email

# 2. Send a real email to that address (from Gmail, etc.)

# 3. Poll inbox until a message appears
curl http://localhost:5050/api/inbox

# 4. Fetch full body using id from step 3
curl http://localhost:5050/api/email/<id>
```

---

## Error responses

| HTTP | Code | Meaning |
|------|------|---------|
| 404 | `EMAIL_NOT_FOUND` | Unknown email id |
| 429 | `CAPTCHA_BLOCKED` | Bot protection not cleared in time |
| 503 | `BROWSER_CRASH` | Browser service down or crashed |
| 500 | `INTERNAL_ERROR` | Unexpected error |

Example:

```json
{ "error": "Blocked by bot protection, retry later", "code": "CAPTCHA_BLOCKED" }
```

---

## Environment variables

### API (`run.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `BROWSER_SERVICE_URL` | `http://localhost:5051` | Browser service URL |
| `EMAIL_CACHE_TTL` | `3600` | Email cache TTL (seconds) |

### Browser service (`run_browser_service.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPAIL_URL` | `https://tempail.com/ua/` | Tempail page URL |
| `HEADLESS` | `false` (local), `true` (Docker) | Run Chrome headless |
| `MANUAL_CAPTCHA_TIMEOUT` | `120` | Seconds to wait for manual CAPTCHA |
| `PAGE_LOAD_TIMEOUT` | `60` | Page load timeout (seconds) |
| `ELEMENT_TIMEOUT` | `30` | Element wait timeout (seconds) |
| `BROWSER_SERVICE_PORT` | `5051` | Service port |
| `CHROME_BIN` | — | Chrome binary (set in Docker) |
| `CHROMEDRIVER_PATH` | — | Chromedriver path (set in Docker) |

---

## Project structure

```
app/
  api/routes.py          # Public REST endpoints
  services/
    browser_client.py    # HTTP client → browser service
    redis_store.py       # Redis cache
browser_service/
  app.py                 # Internal Flask API
  browser.py             # Chrome session manager
  tempail.py             # tempail.com scraper
run.py                   # Start API
run_browser_service.py   # Start browser service
docker-compose.yml         # Full stack: redis + api + browser (headless)
docker-compose.dev.yml     # Hybrid: redis + api in Docker, browser on host
Dockerfile.api
Dockerfile.browser
requirements-api.txt     # Docker: API deps only
requirements-browser.txt # Docker: browser deps only
requirements.txt         # Local venv (full pip freeze)
```

---

## CAPTCHA and Docker

**Why no Chrome window in Docker?**

Docker containers have **no screen**. Chrome runs with `HEADLESS=true` — there is nothing to show and no way to click reCAPTCHA manually. The log message *"solve it in the Chrome window"* only applies when running the browser service **on your Mac** with `HEADLESS=false`.

| Setup | Chrome window | CAPTCHA |
|-------|---------------|---------|
| Local: `python run_browser_service.py` | Visible | You can solve manually |
| Full Docker: `docker compose up` | None (headless) | Usually `CAPTCHA_BLOCKED` |
| **Hybrid (recommended)** | Visible on host | You can solve manually |

### Recommended: hybrid Docker (API + Redis in Docker, browser on host)

```bash
# Terminal 1 — API + Redis only
docker compose -f docker-compose.dev.yml up --build

# Terminal 2 — browser with visible Chrome
source venv/bin/activate
HEADLESS=false python run_browser_service.py
```

Then call the API as usual:

```bash
curl http://localhost:5050/api/health
curl http://localhost:5050/api/email   # solve CAPTCHA in the Chrome window if it appears
```

The API container reaches your local browser via `host.docker.internal:5051`.

---

## Stop Docker

```bash
docker compose down
```

Remove volumes and images:

```bash
docker compose down --rmi local
```
