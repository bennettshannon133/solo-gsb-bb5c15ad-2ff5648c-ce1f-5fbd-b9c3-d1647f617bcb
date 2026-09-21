"""SQLite 连接与 schema 初始化（应用启动时执行）。"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("FC_DATABASE", "/data/factcheck.db"))
if not os.access(DB_PATH.parent, os.W_OK):
    # 开发环境下回退到仓库内 data/ 目录
    DB_PATH = Path(__file__).resolve().parent.parent / "data" / "factcheck.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assertions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    claim       TEXT NOT NULL,
    topic       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'confirmed', 'doubtful')),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_assertions_topic ON assertions(topic);
CREATE INDEX IF NOT EXISTS idx_assertions_status ON assertions(status);

CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    publisher   TEXT NOT NULL DEFAULT '',
    doc_date    TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcripts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    speaker      TEXT NOT NULL,
    interviewed  TEXT NOT NULL DEFAULT '',
    recorded_at  TEXT NOT NULL DEFAULT '',
    snippet      TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    assertion_id INTEGER NOT NULL REFERENCES assertions(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('source', 'transcript')),
    ref_id       INTEGER NOT NULL,
    quote        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (assertion_id, kind, ref_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_assertion ON evidences(assertion_id);

CREATE TABLE IF NOT EXISTS relations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id      INTEGER NOT NULL REFERENCES assertions(id) ON DELETE CASCADE,
    dst_id      INTEGER NOT NULL REFERENCES assertions(id) ON DELETE CASCADE,
    rel_type    TEXT NOT NULL CHECK (rel_type IN ('supports', 'refutes', 'derived_from')),
    rationale   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (src_id, dst_id, rel_type),
    CHECK (src_id <> dst_id)
);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_id);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
