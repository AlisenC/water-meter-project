# Water Meter Dashboard

A full-stack water meter tracking and analysis app with AI-powered analysis.

- **Frontend:** React 19 + Vite + Tailwind CSS
- **Backend:** FastAPI + PostgreSQL (primary store)
- **AI:** Anthropic Claude or OpenAI GPT-4o (your API key, never stored on server)

---

## Features

### Core
- Import PDF water bills using AI extraction (Claude or GPT-4o)
- Import meter readings from CSV files (multi-file, format auto-detection, preview step)
- Dashboard with consumption, cost, and spike summary cards
- Usage charts and anomaly/spike detection across all meters
- Household sum verification against billing statements, plus a "Money Lost to Unaccounted Water" chart showing the $ gap between billed and summed household consumption
- Manual reading entry, search/filter, and CSV export

### Daily Leak Detection
A short-term workspace for spotting leaks between bills, kept completely separate from the monthly billing data above — nothing imported here touches the `Readings` table or billing statements.

- Import daily **submeter** readings and daily **main meter** readings (AMI "range export" CSV) into an active session
- Automatic daily-delta comparison: sums all submeter deltas and checks them against the main meter's delta for the same period
- Flags a **potential leak** whenever the submeter total exceeds the main meter, with a comparison line chart and a per-day table
- Below that comparison, an **SFPUC / EyeOnWater Main Meter Rules** section runs three official leak-detection rules against the main meter's own readings — 24h continuous flow, 48h/72h volume threshold, and nighttime usage ratio — main meter only, since submeter data is manually read and too sparse for these rules to ever apply
- **Archive Session** clears the active workspace for a fresh investigation while keeping the archived data viewable
- **Restore** brings an archived session back as the active workspace at any time

See [Using Daily Leak Detection](#using-daily-leak-detection) below for the full workflow.

### AI Assistant
Chat with AI about your data using Claude or GPT-4o — natural language Q&A against your readings, bills, and leak detection sessions.

---

## Running with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A PostgreSQL database (e.g. a managed instance like AWS RDS) and its connection string

### Set up the database

Recommended: one Postgres instance, a separate database per environment (prod, dev, test), each owned by its own role — so a misconfigured `DATABASE_URL` on a dev machine can't accidentally read or write real data. `PUBLIC`'s default `CONNECT` privilege on the prod database is revoked, so only the intended role can even open a connection to it.

```sql
-- One-time, run as the instance's admin/master user:
CREATE ROLE dev_app LOGIN PASSWORD '<random>';
GRANT dev_app TO <admin_user>;              -- RDS requires this before OWNER TO below
CREATE DATABASE water_meter_dev OWNER dev_app;

CREATE ROLE test_app LOGIN PASSWORD '<random>';
GRANT test_app TO <admin_user>;
CREATE DATABASE water_meter_test OWNER test_app;

REVOKE CONNECT ON DATABASE water_meter FROM PUBLIC;
GRANT CONNECT ON DATABASE water_meter TO <admin_user>;
```

Then:

1. Copy `.env.example` to `.env`. Set `DATABASE_URL` to the `dev_app`/`water_meter_dev` connection string for local dev, and `TEST_DATABASE_URL` to `test_app`/`water_meter_test`. `.env` is gitignored — never commit real credentials.
2. Create the schema with Alembic, once per database:
   ```bash
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   ```
   Re-run this after pulling changes that add a new Alembic revision, and again for any new database (test, a teammate's dev database, etc.).
3. The real deployment's `DATABASE_URL` points at `water_meter` using its own role — not `dev_app`/`test_app`, which are deliberately unable to reach it.

### Start the stack

```bash
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend API: http://localhost:8500

Readings, billing statements, and leak detection data live in Postgres. Imported PDF statements and Oracle wallet files are persisted in a bind-mounted `./data` directory (mapped to `/app/data` in the backend container), so they survive container restarts and rebuilds.

### Stop

```bash
docker compose down
```

### Rebuild after code changes

```bash
docker compose up --build
```

### Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Requires `TEST_DATABASE_URL` in `.env` (or exported) pointing at a dedicated Postgres database — see `.env.example`. It must hold no real data: every test run truncates all app tables in it. It needs its schema created the same way as the main database (`alembic upgrade head` against it) before the first run.

### Reset all data

```bash
docker compose down -v
```

> The `-v` flag only removes the `ollama_data` volume (the pulled local model). To reset app data: truncate the tables in Postgres (or drop and re-run `alembic upgrade head`) for readings/statements/leak sessions, and delete the `./data` directory yourself for imported PDFs and Oracle wallets.

---

## Configuration

### AI provider (required for AI chat; PDF import falls back to a local model)

Open **Settings → AI Provider Settings** in the app and paste your API key.

| Provider | Key type | Models used |
|----------|----------|-------------|
| Anthropic (default) | `sk-ant-...` | Claude for chat/NL2SQL, Voyage for embeddings |
| OpenAI | `sk-...` | GPT-4o for chat/NL2SQL, `text-embedding-3-small` for embeddings |

Keys are stored in your browser's localStorage and sent directly to the backend per-request. They are never written to disk or a database.

### Local model fallback (Ollama)

If no API key is configured, `POST /import-billing` automatically falls back to a local
model via [Ollama](https://ollama.com) instead of requiring a cloud key. This is
text-only extraction: the PDF's text layer is pulled out with `pypdf` and sent to the
model as a prompt. Scanned/image-only statements have no text layer, so those still
require a cloud API key. AI chat / NL2SQL (`ai_agent.py`, `oracle_ai.py`) is unaffected
and always requires a cloud key.

`docker compose up` runs Ollama as its own service and automatically pulls the default
model (`llama3.1`) on first run — no separate install needed, though the first pull
downloads several GB and takes a while. It runs CPU-only unless you add GPU passthrough
to the `ollama` service yourself.

| Env var | Default | Where |
|---------|---------|-------|
| `OLLAMA_BASE_URL` | `http://ollama:11434` (docker-compose) | Where the backend looks for Ollama |
| `OLLAMA_MODEL` | `llama3.1` | Model used for extraction, and what `ollama-pull` fetches in Docker |

---

## Using Daily Leak Detection

Open the **Leak Detection** tab in the sidebar. It always shows one **active session** — a clean workspace for the leak investigation currently in progress — plus a list of **archived sessions** from past investigations.

### 1. Import daily submeter readings

Take a daily photo of each submeter and transcribe it into a CSV (MVP is manual entry; an AI-assisted photo importer is planned for later):

```csv
mi,reading,record_date,unit
Unit1,100.0,2026-08-01,1
Unit2,50.0,2026-08-01,1
```

- `mi` — the household/submeter identifier
- `reading` — the cumulative meter reading
- `record_date` — `YYYY-MM-DD`
- `unit` — `1` if the meter reads in units of water (CCF), `0` if it reads in gallons (converted automatically at `1 unit = 748 gallons`)

Upload it under **Import Daily Submeter Readings**, review the preview (row count / errors), then **Confirm Import**. Repeat this daily to build up a run of readings.

### 2. Import daily main meter readings

Export a "range export" CSV from your main meter's AMI provider (columns: `Account_ID, Meter_ID, Meter_SN, Read_Time, Timezone, Read, Read_Unit, Read_Method, Flow_Time, Flow_Unit, Flow, Register`) and upload it under **Import Daily Main Meter Readings**. Readings must be in `CCF`; each row's `Flow` value is used directly as that period's main-meter delta.

### 3. Review the comparison

Once both sides have at least two days of data, the active session shows a line chart and a table comparing the **main meter flow** against the **summed submeter deltas** for each matching period. Any day where the submeter total exceeds the main meter's flow is highlighted red and marked **Potential Leak**.

### 4. Review the SFPUC / EyeOnWater rules

Below the comparison, a **Property Profile** panel shows the submeter household count and which volume-threshold window applies — **Standard** (48h) for fewer than 6 households, **Multi-Family** (72h) at 6 or more. The **Main Meter** card underneath evaluates three rules against the main meter's own readings only:

| Rule | Triggers when |
|------|---------------|
| **Continuous Flow** | Flow stays above a low threshold continuously for 24+ hours |
| **Volume Threshold** | Flow stays above a higher threshold continuously for 48h (72h if Multi-Family) |
| **Nighttime Ratio** | A night's usage (12am–5am) exceeds 2x the median of prior nights |

Each rule lists its alerts in a table; an alert still in effect as of the most recent reading is tagged **Ongoing** next to its end time, otherwise it's already resolved. Submeter readings are excluded from these rules since they're sparse, manually-transcribed entries that would never satisfy a continuous-coverage check.

### 5. Archive when the investigation is done

Click **Archive Session** and confirm. The active workspace resets to empty for the next investigation, while the archived session (and all its data) stays viewable under the **Archived Sessions** tab. Click **Restore** on an archived session to bring it back as the active workspace at any time — if the current active workspace has data of its own, it's archived first so nothing is lost.

---

## Project structure

```
water-meter/
├── backend/
│   ├── main.py              # FastAPI app, routes
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # DB engine and session (reads DATABASE_URL)
│   ├── alembic/              # Schema migrations
│   ├── ai_agent.py          # AI chat and PDF bill extraction
│   ├── csv_parser.py        # CSV import with format detection
│   ├── units.py             # Shared gallons↔units-of-water conversion
│   ├── leak_detection.py    # /leak/* endpoints (sessions, imports, analysis)
│   ├── leak_rules.py        # SFPUC/EyeOnWater rule engine (continuous flow, volume threshold, nighttime ratio, historical deviation)
│   ├── main_meter_csv.py    # AMI "range export" main meter CSV parser
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
│           ├── MoneyLostChart.jsx         # $ gap between billed and summed household usage
│           ├── DataQuality.jsx            # Anomaly details
│           ├── StatementUpload.jsx        # PDF bill import
│           ├── StatementsList.jsx         # Billing statements table
│           ├── ImportWizard.jsx           # CSV import wizard
│           ├── ReadingTable.jsx           # Readings table with search + export
│           ├── LeakDetectionTool.jsx      # Daily Leak Detection tab (active/archived sessions)
│           ├── LeakSessionView.jsx        # Leak session comparison chart + table
│           ├── LeakDifferenceBarChart.jsx # Per-day submeter-vs-main-meter difference chart
│           ├── LeakRawDataTable.jsx       # Raw submeter / main meter reading tables
│           ├── LeakCsvImport.jsx          # Single-file CSV preview → confirm widget
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
| GET | `/anomalies` | Spike detection: flags a household whose current daily usage rate is 2.5x+ its rolling 90-day baseline |
| GET | `/billing-statements` | List imported bills |
| POST | `/import-billing` | Upload and AI-extract a PDF bill (cloud key if set, else local Ollama) |
| DELETE | `/billing-statements/{id}` | Delete a bill |
| GET | `/billing-verify` | Household sum vs bill verification |
| POST | `/import-csv/preview` | Preview a household meter reading CSV import |
| POST | `/import-csv/confirm` | Import a household meter reading CSV |
| GET | `/leak/sessions` | List all daily leak detection sessions |
| GET | `/leak/sessions/active` | Get (or create) the active leak detection session |
| GET | `/leak/sessions/{id}/analysis` | Per-day main-meter-vs-submeter comparison and leak flags, plus SFPUC/EyeOnWater rule results for the main meter |
| POST | `/leak/submeter/import/preview` | Preview a daily submeter CSV |
| POST | `/leak/submeter/import/confirm` | Import a daily submeter CSV into the active session |
| POST | `/leak/main-meter/import/preview` | Preview a daily main meter (AMI) CSV |
| POST | `/leak/main-meter/import/confirm` | Import a daily main meter CSV into the active session |
| POST | `/leak/sessions/{id}/archive` | Archive the active session, starting a fresh workspace |
| POST | `/leak/sessions/{id}/restore` | Restore an archived session as the active workspace |
| POST | `/ai/ask` | Chat with AI about your data |
| GET | `/oracle/status` | Oracle connection health check |
| POST | `/oracle/init` | Create Oracle tables |
| POST | `/oracle/sync` | Sync Postgres → Oracle |
| POST | `/oracle/embed-sync` | Generate and store embeddings |
| POST | `/oracle/vector-search` | Semantic similarity search |
| POST | `/oracle/ask` | NL2SQL query against Oracle |

AI endpoints accept `X-Api-Key` and `X-Api-Provider`.
