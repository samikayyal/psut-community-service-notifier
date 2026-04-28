FROM python:3.12-slim

# Install Chromium, ChromeDriver, Xvfb (virtual display), and required libs.
# Xvfb lets Chrome run in headful mode (needed for reCAPTCHA v3) without a real display.
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libfontconfig1 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Set Environment Variables
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=gcp

WORKDIR /app

COPY requirements.txt .

# FIX: Python 3.12 requires '--break-system-packages' to install globally
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

# Expose the port
EXPOSE 8080

# Timeout increased to 300s (5 mins) because scraping takes time
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 main:app