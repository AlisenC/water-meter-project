FROM ghcr.io/oracle/oraclelinux8-python:3.12-oracledb

WORKDIR /app
COPY . /app

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

RUN useradd -u 1000 -m opc && chown -R opc /app
USER opc

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
