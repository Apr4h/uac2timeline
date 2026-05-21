import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DB_PATH       = os.environ.get("DB_PATH",    str(BASE_DIR / "uac.db"))
UPLOAD_DIR    = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads"))
BROKER_DIR    = os.environ.get("BROKER_DIR", str(BASE_DIR / "broker"))
RESULTS_DIR   = os.environ.get("RESULTS_DIR", str(BASE_DIR / "broker" / "results"))
PARSE_THRESHOLD = int(os.environ.get("PARSE_THRESHOLD", "75"))

Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(BROKER_DIR).mkdir(parents=True, exist_ok=True)
Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)
