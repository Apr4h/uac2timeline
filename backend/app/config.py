import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "uac.db"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads"))
PARSE_THRESHOLD = int(os.environ.get("PARSE_THRESHOLD", "75"))

Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
