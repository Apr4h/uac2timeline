from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from backend.app.config import DB_PATH

# uac_parser.models must be imported BEFORE uac_parser.database to resolve the
# circular reference inside that package (database.py does `from . import models`
# at the top level, which only works when models is initialized first).
import uac_parser.models  # noqa: F401 - registers artifact models with Base
from uac_parser.database import Base  # safe: uac_parser.models already in sys.modules
import backend.app.models  # noqa: F401 - registers job-tracking models with Base


_DEFAULT_TAGS = [
    ("IOC",                  "red"),
    ("Suspicious",           "orange"),
    ("Benign",               "green"),
    ("Persistence",          "yellow"),
    ("Lateral Movement",     "purple"),
    ("Exfiltration",         "red"),
    ("Privilege Escalation", "orange"),
    ("Review Later",         "gray"),
]


def _seed_default_tags(eng) -> None:
    from sqlalchemy.orm import sessionmaker
    from backend.app.models import Tag
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    db = Session()
    try:
        for name, color in _DEFAULT_TAGS:
            if not db.query(Tag).filter_by(name=name).first():
                db.add(Tag(name=name, color=color, is_default=True))
        db.commit()
    finally:
        db.close()


def get_engine():
    eng = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    _seed_default_tags(eng)
    return eng


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def get_db() -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=engine(), autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
