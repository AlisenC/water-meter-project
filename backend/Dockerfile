FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source into /app/backend/ so `uvicorn backend.main:app` resolves correctly
COPY . ./backend/

ENV DATABASE_URL=sqlite:////app/data/water_meter.db

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
