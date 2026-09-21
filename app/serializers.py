"""行序列化与聚合查询辅助。"""
from __future__ import annotations

from .database import db


def assertion_dict(row) -> dict:
    return {
        "id": row["id"],
        "claim": row["claim"],
        "topic": row["topic"],
        "status": row["status"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def source_dict(row) -> dict:
    return {k: row[k] for k in ("id", "title", "publisher", "doc_date", "url", "content", "created_at")}


def transcript_dict(row) -> dict:
    return {k: row[k] for k in ("id", "speaker", "interviewed", "recorded_at", "snippet", "created_at")}


def evidence_dict(row) -> dict:
    return {k: row[k] for k in ("id", "assertion_id", "kind", "ref_id", "quote", "created_at")}


def relation_dict(row) -> dict:
    return {k: row[k] for k in ("id", "src_id", "dst_id", "rel_type", "rationale", "created_at")}


def get_assertion(conn, assertion_id: int):
    row = conn.execute("SELECT * FROM assertions WHERE id = ?", (assertion_id,)).fetchone()
    return assertion_dict(row) if row else None


def list_assertions(conn, topic: str | None = None, status: str | None = None):
    sql = "SELECT * FROM assertions"
    where, params = [], []
    if topic:
        where.append("topic = ?")
        params.append(topic)
    if status:
        where.append("status = ?")
        params.append(status)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    return [assertion_dict(r) for r in conn.execute(sql, params)]


def all_for_graph(conn):
    assertions = [assertion_dict(r) for r in conn.execute("SELECT * FROM assertions ORDER BY id")]
    relations = [relation_dict(r) for r in conn.execute("SELECT * FROM relations ORDER BY id")]
    evidences = [evidence_dict(r) for r in conn.execute("SELECT * FROM evidences ORDER BY id")]
    return assertions, relations, evidences


def evidence_with_refs(conn, assertion_id: int):
    rows = conn.execute(
        "SELECT * FROM evidences WHERE assertion_id = ? ORDER BY id", (assertion_id,)
    ).fetchall()
    out = []
    for r in rows:
        item = evidence_dict(r)
        if r["kind"] == "source":
            ref = conn.execute("SELECT * FROM sources WHERE id = ?", (r["ref_id"],)).fetchone()
            item["ref"] = source_dict(ref) if ref else None
        else:
            ref = conn.execute("SELECT * FROM transcripts WHERE id = ?", (r["ref_id"],)).fetchone()
            item["ref"] = transcript_dict(ref) if ref else None
        out.append(item)
    return out


def relations_for(conn, assertion_id: int):
    outgoing = [
        relation_dict(r)
        for r in conn.execute(
            "SELECT * FROM relations WHERE src_id = ? ORDER BY id", (assertion_id,)
        )
    ]
    incoming = [
        relation_dict(r)
        for r in conn.execute(
            "SELECT * FROM relations WHERE dst_id = ? ORDER BY id", (assertion_id,)
        )
    ]
    return outgoing, incoming


def touch_assertion(conn, assertion_id: int) -> None:
    conn.execute("UPDATE assertions SET updated_at = datetime('now') WHERE id = ?", (assertion_id,))


def load_tables():
    with db() as conn:
        return all_for_graph(conn)
