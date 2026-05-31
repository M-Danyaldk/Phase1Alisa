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
  recommended_next_topics TEXT,
  parent_summary TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS child_learning_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  child_id TEXT NOT NULL,
  subject TEXT NOT NULL,
  assessed_level TEXT NOT NULL,
  learning_gaps TEXT,
  strengths TEXT,
  recommended_next_steps TEXT,
  recommended_next_topics TEXT,
  last_assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(child_id, subject)
);
CREATE TABLE IF NOT EXISTS waitlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  source TEXT DEFAULT 'prelaunch_landing',
  status TEXT DEFAULT 'pending',
  metadata TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        if 'recommended_next_topics' not in columns:
            conn.execute('ALTER TABLE assessment_results ADD COLUMN recommended_next_topics TEXT')
        waitlist_columns = [row['name'] for row in conn.execute('PRAGMA table_info(waitlist)').fetchall()]
        if 'metadata' not in waitlist_columns:
            conn.execute('ALTER TABLE waitlist ADD COLUMN metadata TEXT')
        conn.commit()

def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_connection() as conn:
        cur = conn.execute(query, params)
        conn.commit()
        return int(cur.lastrowid or 0)

def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]
