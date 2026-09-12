"""Database setup — one SQLite file per data mode.

Real and Demo Mode are physically separated (CONTEXT.md: "Demo Mode"):
  data/real.db  — real measurements from the Google Health API
  data/demo.db  — generated demo data
Demo data can therefore never leak into real Baselines or scores.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models import Base

# Overridable for hosting: point at a persistent volume (e.g. /data on Fly).
DATA_DIR = Path(os.environ.get("SIGNALS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))


class DataMode(str, Enum):
    REAL = "real"
    DEMO = "demo"


_engines: dict[DataMode, object] = {}
_sessionmakers: dict[DataMode, sessionmaker] = {}


def get_engine(mode: DataMode):
    if mode not in _engines:
        DATA_DIR.mkdir(exist_ok=True)
        engine = create_engine(f"sqlite:///{DATA_DIR / (mode.value + '.db')}", future=True)
        Base.metadata.create_all(engine)
        _engines[mode] = engine
        _sessionmakers[mode] = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _engines[mode]


def get_session(mode: DataMode) -> Session:
    get_engine(mode)
    return _sessionmakers[mode]()
