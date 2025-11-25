FROM python:3.12-slim

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set environment variables
ENV DISPLAY=:99
ENV IS_DOCKER=true
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose port (Cloud Run uses PORT env var)
EXPOSE 8080

# Run Gunicorn server with timeout for long-running scrapes
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 main:app