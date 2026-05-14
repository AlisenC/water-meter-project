# Water Meter Dashboard

A full-stack water meter tracking app with AI-powered analysis.

- **Frontend:** React 19 + Vite + Tailwind CSS
- **Backend:** FastAPI + SQLite

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

### Stop the stack

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

---

## Local development (without Docker)

**Backend**

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173, backend at http://localhost:8000.
