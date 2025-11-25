FROM python:3.12-slim

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set display port
ENV DISPLAY=:99

WORKDIR /app

COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

# Run Gunicorn server
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app