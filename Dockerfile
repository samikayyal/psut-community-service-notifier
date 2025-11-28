FROM python:3.12-slim

# Install Chromium, Driver, and specific font/audio libs required for Headless
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Set Environment Variables
# ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=true

WORKDIR /app

COPY requirements.txt .

# FIX: Python 3.12 requires '--break-system-packages' to install globally
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

# Run the application
CMD ["python", "main.py"]