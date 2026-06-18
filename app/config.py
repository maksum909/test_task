import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BROWSER_SERVICE_URL = os.getenv("BROWSER_SERVICE_URL", "http://localhost:5051")
EMAIL_CACHE_TTL = int(os.getenv("EMAIL_CACHE_TTL", "3600"))
