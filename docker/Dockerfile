FROM ghcr.io/oracle/oraclelinux8-python:3.12-oracledb

# Install pip packages from requirements
# COPY requirements.txt /tmp/requirements.txt

# RUN python -m pip install  --upgrade pip setuptools wheel
#    python -m pip install  -r /tmp/requirements.txt

# Create a directory to store results and ensure it is owned by the non-root user.
WORKDIR /results
RUN chmod -R 777 /results

# Create application directory and a non-root user
WORKDIR /app
COPY . /app
RUN useradd -u 1000 -m opc && chown -R opc /app
USER opc

# Default command runs the app
CMD ["python3", "-m", "app.main"]
