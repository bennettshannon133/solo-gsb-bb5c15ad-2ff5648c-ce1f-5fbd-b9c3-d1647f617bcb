"""SQLite 数据访问层：连接管理、建表与演示数据初始化。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "factcheck.db"
DB_PATH = os.environ.get("FACTCHECK_DB", str(DEFAULT_DB))

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'document' CHECK (kind IN ('document', 'transcript')),
    publisher  TEXT NOT NULL DEFAULT '',
    url        TEXT NOT NULL DEFAULT '',
    excerpt    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS claims (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    topic_id   INTEGER REFERENCES topics(id)  ON DELETE SET NULL,
    source_id  INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'doubtful')),
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS relations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    to_claim_id   INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    type          TEXT NOT NULL CHECK (type IN ('supports', 'refutes', 'derives')),
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (from_claim_id, to_claim_id, type)
);

CREATE INDEX IF NOT EXISTS idx_claims_topic    ON claims(topic_id);
CREATE INDEX IF NOT EXISTS idx_claims_status   ON claims(status);
CREATE INDEX IF NOT EXISTS idx_relations_from  ON relations(from_claim_id);
CREATE INDEX IF NOT EXISTS idx_relations_to    ON relations(to_claim_id);
"""


def get_conn() -> sqlite3.Connection:
    """每个请求使用独立连接，启用外键约束。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """启动时调用：建表；若库为空则写入一组演示数据。"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM claims").fetchone()["c"]
        if count == 0:
            _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    """演示数据：包含一处冲突、一处循环引用与两条无来源断言，便于展示分析能力。"""
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO topics (name, description) VALUES (?, ?)",
        [
            ("发布会声明核查", "某品牌新品发布会中的关键声明"),
            ("城市交通政策", "新一轮交通拥堵治理政策的效果评估"),
        ],
    )

    cur.executemany(
        "INSERT INTO sources (title, kind, publisher, url, excerpt) VALUES (?, ?, ?, ?, ?)",
        [
            (
                "新品发布会逐字稿（节选）",
                "transcript",
                "现场速记",
                "",
                "主持人：……我们的测试显示，满电续航可达 22 小时，这是实验室标准工况下的结果……",
            ),
            (
                "官方新闻稿：X9 正式发布",
                "document",
                "品牌公关部",
                "https://example.com/press/x9",
                "X9 续航长达 22 小时，重新定义行业标准。",
            ),
            (
                "第三方评测报告·第 14 期",
                "document",
                "独立评测实验室",
                "https://example.com/review/14",
                "在模拟日常使用的综合测试中，X9 实测续航为 17 小时。",
            ),
            (
                "市交通委季度通报",
                "document",
                "市交通委员会",
                "",
                "新政实施季度内，核心区高峰拥堵指数同比下降 12%。",
            ),
        ],
    )

    # claims: (text, topic_id, source_id, status, notes)
    cur.executemany(
        "INSERT INTO claims (text, topic_id, source_id, status, notes) VALUES (?, ?, ?, ?, ?)",
        [
            ("官方宣称 X9 续航达 22 小时", 1, 2, "confirmed", "新闻稿原文表述"),
            ("第三方实测 X9 续航为 17 小时", 1, 3, "confirmed", "评测报告综合工况"),
            ("官方 22 小时数据基于实验室标准工况", 1, 1, "confirmed", "逐字稿中主持人自述"),
            ("官方续航宣传对消费者具有误导性", 1, None, "pending", "评论性断言，需补充依据"),
            ("实际续航与官方宣传明显不符", 1, None, "pending", ""),
            ("新政使核心区高峰拥堵指数下降 12%", 2, 4, "confirmed", "交通委通报口径"),
            ("拥堵指数下降主要源于同期地铁新线开通", 2, None, "doubtful", "缺乏数据支撑，存疑"),
        ],
    )

    # relations: (from, to, type, note)
    cur.executemany(
        "INSERT INTO relations (from_claim_id, to_claim_id, type, note) VALUES (?, ?, ?, ?)",
        [
            (2, 1, "refutes", "实测 17 小时与宣传 22 小时差距显著"),
            (3, 4, "supports", "实验室工况与日常使用差距是误导性判断的依据"),
            (4, 5, "derives", "误导性结论派生自「宣传与实际不符」"),
            (5, 4, "derives", "反向派生：构成循环论证示例"),
            (7, 6, "refutes", "对因果归因提出质疑"),
        ],
    )
