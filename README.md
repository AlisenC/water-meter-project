# Water Meter Dashboard

A full-stack water meter tracking and analysis app with AI-powered analysis and optional Oracle 26ai integration.

- **Frontend:** React 19 + Vite + Tailwind CSS
- **Backend:** FastAPI + SQLite (primary store)
- **AI:** Anthropic Claude or OpenAI GPT-4o (your API key, never stored on server)
- **Optional:** Oracle AI Database 26ai — vector search, NL2SQL, mirrored data store

---

## Features

### Core
- Import PDF water bills using AI extraction (Claude or GPT-4o)
- Import meter readings from CSV files (multi-file, format auto-detection, preview step)
- Dashboard with consumption, cost, and spike summary cards
- Usage charts and anomaly/spike detection across all meters
- Household sum verification against billing statements
- Manual reading entry, search/filter, and CSV export

### AI Assistant
Three tabs in one section — no Oracle required for Chat:

| Tab | What it does |
|-----|-------------|
| **Chat** | Natural language Q&A against your data using Claude or GPT-4o |
| **Ask Oracle** | NL2SQL — type a question, get a generated SQL query run against Oracle and an AI explanation |
| **Semantic Search** | Find meter readings similar to a text query using Oracle vector embeddings |

### Oracle 26ai (optional)
Oracle is fully config-ready — the app works without it. When connected, it enables Ask Oracle and Semantic Search.

- Connect by entering credentials in **Settings → Oracle 26ai Connection** (stored in browser localStorage, sent as request headers — never persisted on server)
- Or set server-side env vars for production deployments (see below)
- Once connected: initialize tables, sync SQLite data to Oracle, generate embeddings

---

## Running with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Start the stack

```bash
docker compose up --build
```

- Frontend: http://localhost
- Backend API: http://localhost:8000

Data is persisted in a Docker volume (`water_meter_data`) so it survives container restarts.

### Stop

```bash
docker compose down
```

### Rebuild after code changes

```bash
docker compose up --build
```

### Reset all data

```bash
docker compose down -v
```

> The `-v` flag removes the volume, wiping the SQLite database.

### Oracle env vars in Docker

Add to the `backend` service in `docker-compose.yml`:

```yaml
environment:
  - DATABASE_URL=sqlite:////app/data/water_meter.db
  - ALLOWED_ORIGINS=http://localhost
  - ORACLE_DSN=hostname:1521/service_name
  - ORACLE_USER=wm_user
  - ORACLE_PASSWORD=your_password
```

---

## Local development (without Docker)

**Backend**

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# venv/bin/activate          # macOS/Linux
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173 · Backend: http://localhost:8000

---

## Configuration

### AI provider (required for PDF import and AI chat)

Open **Settings → AI Provider Settings** in the app and paste your API key.

| Provider | Key type | Models used |
|----------|----------|-------------|
| Anthropic (default) | `sk-ant-...` | Claude for chat/NL2SQL, Voyage for embeddings |
| OpenAI | `sk-...` | GPT-4o for chat/NL2SQL, `text-embedding-3-small` for embeddings |

Keys are stored in your browser's localStorage and sent directly to the backend per-request. They are never written to disk or a database.

### Oracle 26ai (optional)

**Option A — Browser UI (recommended for development)**

Go to **Settings → Oracle 26ai Connection**, enter your DSN, username, and password, then click **Save & Test Connection**. Credentials are stored in localStorage and sent as `X-Oracle-*` request headers.

**Option B — Server-side env vars (recommended for production)**

Set these on the host running the backend before starting:

```bash
ORACLE_DSN=hostname:1521/service_name
ORACLE_USER=wm_user
ORACLE_PASSWORD=your_password
```

Both options can coexist — UI credentials take priority over env vars when provided.

**First-time Oracle setup (after connecting)**

1. **Initialize Tables** — creates `wm_readings`, `wm_billing_statements`, `wm_readings_vectors` in Oracle (safe to run multiple times)
2. **Sync Data** — upserts all SQLite readings and bills into Oracle using MERGE
3. **Generate Embeddings** — generates AI embeddings for each reading and stores them in Oracle `VECTOR` columns (required for Semantic Search)

---

## Project structure

```
water-meter/
├── backend/
│   ├── main.py              # FastAPI app, routes, SQLite ORM
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # DB engine and session
│   ├── ai_agent.py          # AI chat and PDF bill extraction
│   ├── csv_parser.py        # CSV import with format detection
│   ├── oracle_connection.py # Oracle connection pool + per-request creds
│   ├── oracle_ai.py         # /oracle/* endpoints (status, sync, NL2SQL, vector search)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx                        # Root layout, state, routing
│       └── components/
│           ├── Sidebar.jsx                # Collapsible dark sidebar
│           ├── DashboardSummary.jsx       # Stat cards + spike list
│           ├── UsageCharts.jsx            # Consumption charts
│           ├── DataQuality.jsx            # Anomaly details
│           ├── BillingImport.jsx          # PDF import + billing table
│           ├── ImportWizard.jsx           # CSV import wizard
│           ├── ReadingTable.jsx           # Readings table with search + export
│           ├── AIAssistant.jsx            # Chat / Ask Oracle / Semantic Search tabs
│           ├── ApiKeySettings.jsx         # AI provider key management
│           └── OracleSettings.jsx         # Oracle credential entry + sync actions
├── docker-compose.yml
└── README.md
```

---

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/readings` | List all meter readings |
| POST | `/readings` | Add a reading |
| DELETE | `/readings/{id}` | Delete a reading |
| GET | `/anomalies` | Spike/anomaly detection results |
| GET | `/billing-statements` | List imported bills |
| POST | `/import-billing` | Upload and AI-extract a PDF bill |
| DELETE | `/billing-statements/{id}` | Delete a bill |
| GET | `/billing-verify` | Household sum vs bill verification |
| POST | `/import-csv` | Import meter readings from CSV |
| POST | `/ai/ask` | Chat with AI about your data |
| GET | `/oracle/status` | Oracle connection health check |
| POST | `/oracle/init` | Create Oracle tables |
| POST | `/oracle/sync` | Sync SQLite → Oracle |
| POST | `/oracle/embed-sync` | Generate and store embeddings |
| POST | `/oracle/vector-search` | Semantic similarity search |
| POST | `/oracle/ask` | NL2SQL query against Oracle |

All `/oracle/*` endpoints accept optional `X-Oracle-Dsn`, `X-Oracle-User`, `X-Oracle-Password` headers. AI endpoints accept `X-Api-Key` and `X-Api-Provider`.
