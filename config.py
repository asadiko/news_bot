import os

TOKEN = os.environ.get("TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

# Admin user IDs — get yours from @userinfobot on Telegram
# Leave empty [] to allow anyone (not recommended in production)
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(","))) if os.environ.get("ADMIN_IDS") else []

CHECK_INTERVAL_MINUTES = 5
MAX_MESSAGES_PER_CYCLE = 10        # Max posts per check cycle (flood protection)
MESSAGE_DELAY_SECONDS = 1.5        # Delay between sends
REQUEST_TIMEOUT_SECONDS = 15       # RSS fetch timeout
MAX_DB_AGE_DAYS = 30               # Purge seen links older than this
