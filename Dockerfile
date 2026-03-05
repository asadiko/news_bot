FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Persist data.json across restarts (mount a volume here)
VOLUME ["/app/data"]

# Run bot
CMD ["python", "bot.py"]
