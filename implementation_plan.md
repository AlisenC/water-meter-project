# Implementation Plan

[Overview]
Refactor and stabilize the full frontend↔backend flow for reading creation, listing, and CSV import so behavior is consistent, resilient, and contract-aligned.

This implementation focuses on end-to-end correctness rather than adding new product features. Right now, the stack has drift between frontend request payloads and backend expectations (`mi/reading` vs `household/amount`), weak error-state behavior, and duplicated async orchestration spread across components. Those issues cause unstable UX and brittle integrations under normal failures (bad inputs, network errors, malformed CSV rows).

The high-level approach is to normalize contracts at the API boundary, centralize orchestration in the page container, simplify child components into controlled interaction layers, and enforce safe backend transaction/session patterns. This reduces mismatch bugs and stabilizes data round-trips without changing the project’s core architecture.

[Types]
Establish explicit request/response and UI state data contracts across frontend and backend.

Detailed definitions:
- Frontend normalized model (`ReadingViewModel`):
  - `id: number`
  - `mi: string`
  - `reading: number`
  - `record_date?: string`
  - `unit?: number`
- Frontend request model for add-reading form:
  - `mi: string` (trimmed, required)
  - `reading: number` (finite, `>= 0`)
- Backend create input model (keep single canonical API contract):
  - Option A (recommended): `household: str`, `amount: float`
  - Option B: migrate to `mi: str`, `reading: float`
  - Plan will enforce one canonical mapping and remove ambiguity.
- UI async status shape:
  - `isLoadingReadings`, `isSubmittingReading`, `isUploadingCsv`
  - `loadError`, `submitError`, `uploadError`, `uploadSuccess`

Validation rules:
- Reject empty household/mi and negative/non-finite reading values.
- CSV row parser validates required columns and type conversions before insert.

[Files]
Modify backend and frontend integration points to remove contract drift and async instability.

Detailed breakdown:
- Existing files to modify:
  - `backend/main.py`
    - Standardize POST `/readings` request parsing.
    - Add robust CSV parsing + per-row validation/error capture.
    - Improve DB session handling and exception safety (`try/except/finally`).
  - `backend/models.py`
    - Verify model field usage consistency; optionally add non-null constraints where safe.
  - `frontend/src/api.js`
    - Add canonical mapper functions for request/response shape normalization.
  - `frontend/src/App.jsx`
    - Centralize async orchestration (`fetchReadings`, create, upload), state transitions, and retries.
  - `frontend/src/components/ReadingTable.jsx`
    - Use parent callback flow, input validation, loading disable, stable keys.
  - `frontend/src/components/DashboardSummary.jsx`
    - Harden summary computation against malformed values.
- New files (optional but recommended):
  - `frontend/src/utils/readingMapper.js` (if separating mapping concerns)
- Files deleted/moved:
  - None required.
- Config updates:
  - None mandatory.

[Functions]
Refactor function boundaries to isolate contracts, validation, and side effects.

Detailed breakdown:
- New functions:
  - `fetchReadings()` in `frontend/src/App.jsx`
  - `createReading(input)` in `frontend/src/api.js`
  - `importCsv(file)` in `frontend/src/api.js`
  - `normalizeReading(record)` in `frontend/src/api.js` (or mapper util)
  - `validateReadingInput(input)` in `frontend/src/components/ReadingTable.jsx` (or shared util)
- Modified functions:
  - `add_reading()` in `backend/main.py`
  - `import_csv()` in `backend/main.py`
  - `App()` in `frontend/src/App.jsx`
  - `handleSubmit()` in `frontend/src/components/ReadingTable.jsx`
  - `DashboardSummary()` in `frontend/src/components/DashboardSummary.jsx`
- Removed/replaced behaviors:
  - Direct API POST logic inside child table component (moved to centralized orchestration)
  - Implicit payload guessing between layers

[Classes]
Class-level changes are minimal and limited to backend model consistency.

Detailed breakdown:
- New classes:
  - None.
- Modified classes:
  - `Reading` in `backend/models.py` (only if adding safe constraints/indexes).
- Removed classes:
  - None.

[Dependencies]
No new package dependencies are required for stabilization.

If needed, optional improvements can be made without dependency expansion (built-in validation and existing FastAPI/Pydantic/SQLAlchemy patterns are sufficient).

[Testing]
Test the full flow under both happy and failure scenarios to verify stabilization.

Validation strategy:
- Backend API checks:
  - `POST /readings` with valid and invalid payloads.
  - `GET /readings` after inserts/import.
  - `POST /import-csv` with valid CSV, malformed rows, wrong columns.
- Frontend behavior checks:
  - Initial load states: loading/success/error.
  - Add-reading validation and disabled-button behavior.
  - CSV upload success/failure messaging and refresh correctness.
- End-to-end consistency:
  - Created reading appears in table and summary.
  - CSV imported records appear consistently with expected fields.

[Implementation Order]
Execute contract alignment first, then orchestration refactor, then UX stabilization and verification.

1. Decide and lock canonical create-reading contract (`household/amount` vs `mi/reading`).
2. Update backend `add_reading` and `import_csv` for validation + safe transaction handling.
3. Update frontend API layer to canonicalize request/response mapping.
4. Refactor `App.jsx` to centralize async flow and statuses.
5. Refactor `ReadingTable.jsx` + `DashboardSummary.jsx` for robust UI behavior.
6. Run end-to-end verification across create/list/import flows and edge cases.

## End-to-End Workflow Graph

```mermaid
flowchart TD
    U[User] --> FE[Frontend React App\nApp.jsx]

    subgraph Frontend
      FE --> RT[ReadingTable\nAdd Reading Form]
      FE --> CSV[CSV Upload Control]
      FE --> DS[DashboardSummary]
      FE --> API[Axios Client\napi.js]
    end

    RT -->|POST /readings\n{household, amount}| API
    CSV -->|POST /import-csv\nmultipart/form-data| API
    FE -->|GET /readings| API

    API --> BE[FastAPI Backend\nmain.py]

    subgraph Backend
      BE --> AR[add_reading()]
      BE --> IR[import_csv()]
      BE --> GR[get_readings()]
    end

    AR --> ORM[SQLAlchemy ORM\nReading model]
    IR --> ORM
    GR --> ORM

    ORM --> DB[(SQLite Database)]

    DB --> ORM
    ORM --> GR
    GR -->|JSON readings list| API
    API --> FE

    AR -->|Created reading response| API
    IR -->|Import status message| API

    FE -->|Update table + summary| U
```