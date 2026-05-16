import sqlite3
from pathlib import Path
from typing import Any
from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  grade INTEGER NOT NULL,
  math_level TEXT,
  ela_level TEXT,
  writing_level TEXT,
  confidence TEXT,
  focus_notes TEXT,
  parent_notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS assessment_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  child_id TEXT,
  student_name TEXT,
  subject TEXT,
  estimated_level TEXT,
  learning_gaps TEXT,
  recommended_progression TEXT,
  parent_summary TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS llm_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT,
  model TEXT,
  purpose TEXT,
  fallback_used INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        columns = [row['name'] for row in conn.execute('PRAGMA table_info(assessment_results)').fetchall()]
        if 'child_id' not in columns:
            conn.execute('ALTER TABLE assessment_results ADD COLUMN child_id TEXT')
        conn.commit()

def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_connection() as conn:
        cur = conn.execute(query, params)
        conn.commit()
        return int(cur.lastrowid or 0)

def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]
