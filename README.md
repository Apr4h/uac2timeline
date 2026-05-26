# uac2timeline

A web application for parsing and analysing [UAC (Unix Artifacts Collector)](https://github.com/tclahr/uac) forensic collections. Upload a UAC archive, let the background workers parse each artifact type in parallel, then explore the results through a filterable timeline and per-artifact views.

## Features

- **Upload & parse** — accepts UAC collections as `.zip` or `.tar.gz` archives; parsing runs in the background via Celery workers with per-artifact status tracking
- **Unified timeline** — merges processes, authentications, command history, and syslog into a single chronological view with date range and column-level filtering
- **Per-artifact tabs** — dedicated views for each artifact type with their full field sets
- **Column filters** — per-column include/exclude rules with optional regex support; multiple rules are combined with AND logic
- **Tagging** — tag individual rows or bulk-tag selections with named, colour-coded tags; tags persist across sessions
- **Notes** — attach free-text notes to individual rows or bulk-apply to a selection
- **Excel export** — export tagged rows to `.xlsx`; produces a unified timeline sheet and a separate sheet per artifact type, with notes included
- **File preview** — inline preview of RC scripts, cron files, systemd unit files, and shell history files
- **Theme** — Tokyo Night colour scheme with Night, Storm, and Light variants and four accent colour options
- **Timezone handling** — timestamps are normalised to UTC using the timezone captured in the UAC collection metadata

## Parsers

| Artifact | Source in UAC collection | Notes |
|----------|--------------------------|-------|
| **Processes** | `live_response/process/` | Correlates fields across multiple output formats using grok patterns; configurable match threshold |
| **Network connections** | `live_response/network/` | Active connections and listening sockets |
| **Authentications** | `live_response/system/`, `[root]/var/log/` | Parses auth/secure logs; supports `auth.log`, `secure`, and PAM-style entries |
| **Command history** | User home directories | Covers bash, zsh, sh, csh, tcsh, fish, mysql, psql, sqlite3, Python, IPython, Node.js REPL, Ruby, R, GHCi, and others |
| **Users** | `[root]/etc/passwd` (Linux), DSLocal plist files (macOS) | UID, GID, home directory, shell |
| **Files** | `bodyfile/bodyfile.txt` | Parsed from UAC bodyfile (macOS-compatibility format); captures MAC timestamps, size, permissions, and MD5 |
| **Cron** | `/etc/cron*`, `/var/spool/cron/` | System crontabs, per-user crontabs, and periodic script directories; cross-platform paths for Linux, macOS, and Solaris |
| **Systemd services** | `etc/systemd/`, `usr/lib/systemd/` | Unit files (`.service`, `.timer`, `.socket`, `.mount`, `.path`, `.target`) from system and user scopes |
| **RC scripts** | `etc/rc*`, `etc/init.d/`, `etc/profile.d/`, home dotfiles | SysV init scripts, BSD rc.d, and user shell startup files; stores a content snippet for each file |
| **Syslog** | `[root]/var/log/` (Linux), `[root]/private/var/log/` (macOS) | Supports BSD, ISO-8601, and RFC 5424 formats; handles rotated and gzip-compressed log files; year inference from file modification time |

## Architecture

```
┌───────────────────────────────┐
│      Vue 3 + Vite (frontend/) │  http://localhost:5173
└──────────────┬────────────────┘
               │ /api  (proxied in dev)
┌──────────────▼────────────────┐
│    FastAPI   (backend/app/)   │  http://localhost:8000
└──────┬───────────────┬────────┘
       │               │
   SQLite (uac.db)  filesystem broker (broker/)
       │               │
       │  ┌────────────▼────────────┐
       └──│   Celery workers        │
          │  (per-artifact tasks)   │
          └─────────────────────────┘
```

The Celery broker uses the local filesystem — no Redis or RabbitMQ is required.

## Requirements

- Python 3.10+
- Node.js 18+ *(only needed if you intend to modify and rebuild the frontend)*

## Installation

```bash
# Clone the repository
git clone https://github.com/adamaprahamian/uac2timeline.git
cd uac2timeline

# Install Python dependencies (includes honcho)
pip install -r requirements.txt
```

## Running

### Option A — honcho (recommended)

```bash
honcho start
```

This starts both processes defined in `Procfile`:

| Process | Address |
|---------|---------|
| FastAPI API server | http://localhost:8000 |
| Celery worker | — |

Open http://localhost:8000 in your browser. FastAPI serves the pre-built frontend directly.

### Option B — manually

```bash
# Terminal 1: API server (run from repo root)
uvicorn backend.app.main:app --reload --port 8000

# Terminal 2: Celery worker
celery -A backend.app.tasks.celery_app worker --loglevel=info
```

### Frontend development

If you need to modify the frontend, Node.js 18+ is required:

```bash
cd frontend && npm install && npm run dev
```

This starts the Vite dev server at http://localhost:5173 (proxies `/api` to port 8000). After making changes, rebuild and commit the output:

```bash
cd frontend && npm run build
```

## Configuration

All settings can be overridden with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `uac.db` (repo root) | Path to the SQLite database |
| `UPLOAD_DIR` | `uploads/` (repo root) | Where uploaded archives and extracted collections are stored |
| `BROKER_DIR` | `broker/` (repo root) | Celery filesystem broker directory |
| `PARSE_THRESHOLD` | `75` | Minimum percentage of lines that must match a grok pattern for that pattern to be used (applies to process and network parsers) |

## Usage

1. Open the app and go to **Collections**.
2. Click **Upload** and select a UAC collection archive (`.zip` or `.tar.gz`).
3. The collection card shows parsing progress per artifact type. Parsing runs in the background; the UI polls for updates automatically.
4. Once parsing is complete, click **Analyze** to open the analysis view.
5. Use the **Timeline** tab for a unified chronological view across artifact types. Use the sidebar to add column filters.
6. Use the per-artifact tabs (Processes, Network, Auth, etc.) to explore individual artifact types.
7. Select rows and click **Tag selected** to apply a colour-coded tag. Tags can be managed from the **Tags** page.
8. Right-click a row to add a note.
9. Click **Export** on a collection card to download tagged rows as an Excel spreadsheet.
