"""FastAPI 应用入口：REST API + 静态前端。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analysis import analyze
from .database import get_conn, init_db
from .models import (
    ClaimIn,
    ClaimUpdate,
    RelationIn,
    SourceIn,
    StatusIn,
    TopicIn,
)
from .report import build_markdown

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 启动时初始化数据库（建表 + 空库时写入演示数据）
    yield


app = FastAPI(title="采访事实核查工作台", version="1.0.0", lifespan=lifespan)


def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row(conn, sql: str, params: tuple, what: str):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what}不存在")
    return row


# ------------------------------------------------------------------ 健康检查

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------ 主题

@app.get("/api/topics")
def list_topics(conn=Depends(db)):
    rows = conn.execute(
        """
        SELECT t.*, COUNT(c.id) AS claim_count
        FROM topics t LEFT JOIN claims c ON c.topic_id = t.id
        GROUP BY t.id
        ORDER BY t.id
        """
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/topics", status_code=201)
def create_topic(body: TopicIn, conn=Depends(db)):
    try:
        cur = conn.execute(
            "INSERT INTO topics (name, description) VALUES (?, ?)",
            (body.name.strip(), body.description),
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="主题名称已存在") from exc
    return dict(_row(conn, "SELECT * FROM topics WHERE id = ?", (cur.lastrowid,), "主题"))


@app.delete("/api/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, conn=Depends(db)):
    _row(conn, "SELECT id FROM topics WHERE id = ?", (topic_id,), "主题")
    conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))  # 断言的 topic_id 置空
    return Response(status_code=204)


# ------------------------------------------------------------------ 来源

@app.get("/api/sources")
def list_sources(conn=Depends(db)):
    rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/sources", status_code=201)
def create_source(body: SourceIn, conn=Depends(db)):
    cur = conn.execute(
        "INSERT INTO sources (title, kind, publisher, url, excerpt) VALUES (?, ?, ?, ?, ?)",
        (body.title.strip(), body.kind, body.publisher, body.url, body.excerpt),
    )
    return dict(_row(conn, "SELECT * FROM sources WHERE id = ?", (cur.lastrowid,), "来源"))


@app.put("/api/sources/{source_id}")
def update_source(source_id: int, body: SourceIn, conn=Depends(db)):
    _row(conn, "SELECT id FROM sources WHERE id = ?", (source_id,), "来源")
    conn.execute(
        "UPDATE sources SET title = ?, kind = ?, publisher = ?, url = ?, excerpt = ? WHERE id = ?",
        (body.title.strip(), body.kind, body.publisher, body.url, body.excerpt, source_id),
    )
    return dict(_row(conn, "SELECT * FROM sources WHERE id = ?", (source_id,), "来源"))


@app.delete("/api/sources/{source_id}", status_code=204)
def delete_source(source_id: int, conn=Depends(db)):
    _row(conn, "SELECT id FROM sources WHERE id = ?", (source_id,), "来源")
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))  # 断言的 source_id 置空
    return Response(status_code=204)


# ------------------------------------------------------------------ 断言

CLAIM_SELECT = """
    SELECT c.*, t.name AS topic_name, s.title AS source_title, s.kind AS source_kind
    FROM claims c
    LEFT JOIN topics  t ON t.id = c.topic_id
    LEFT JOIN sources s ON s.id = c.source_id
"""


@app.get("/api/claims")
def list_claims(
    topic_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    conn=Depends(db),
):
    sql, params = CLAIM_SELECT, []
    clauses = []
    if topic_id is not None:
        clauses.append("c.topic_id = ?")
        params.append(topic_id)
    if status:
        clauses.append("c.status = ?")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY c.id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


@app.post("/api/claims", status_code=201)
def create_claim(body: ClaimIn, conn=Depends(db)):
    _validate_refs(conn, body.topic_id, body.source_id)
    cur = conn.execute(
        "INSERT INTO claims (text, topic_id, source_id, notes) VALUES (?, ?, ?, ?)",
        (body.text.strip(), body.topic_id, body.source_id, body.notes),
    )
    return _get_claim(conn, cur.lastrowid)


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: int, conn=Depends(db)):
    return _get_claim(conn, claim_id)


@app.put("/api/claims/{claim_id}")
def update_claim(claim_id: int, body: ClaimUpdate, conn=Depends(db)):
    _row(conn, "SELECT id FROM claims WHERE id = ?", (claim_id,), "断言")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    _validate_refs(conn, data.get("topic_id"), data.get("source_id"))
    if "text" in data and data["text"] is not None:
        data["text"] = data["text"].strip()
    sets = ", ".join(f"{k} = ?" for k in data)
    conn.execute(
        f"UPDATE claims SET {sets}, updated_at = datetime('now') WHERE id = ?",
        (*data.values(), claim_id),
    )
    return _get_claim(conn, claim_id)


@app.patch("/api/claims/{claim_id}/status")
def update_status(claim_id: int, body: StatusIn, conn=Depends(db)):
    """状态流转：待核查 / 已确认 / 存疑 之间可任意流转。"""
    _row(conn, "SELECT id FROM claims WHERE id = ?", (claim_id,), "断言")
    conn.execute(
        "UPDATE claims SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (body.status, claim_id),
    )
    return _get_claim(conn, claim_id)


@app.delete("/api/claims/{claim_id}", status_code=204)
def delete_claim(claim_id: int, conn=Depends(db)):
    _row(conn, "SELECT id FROM claims WHERE id = ?", (claim_id,), "断言")
    conn.execute("DELETE FROM claims WHERE id = ?", (claim_id,))  # 关系级联删除
    return Response(status_code=204)


def _get_claim(conn, claim_id: int) -> dict:
    row = conn.execute(CLAIM_SELECT + " WHERE c.id = ?", (claim_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="断言不存在")
    return dict(row)


def _validate_refs(conn, topic_id, source_id) -> None:
    if topic_id is not None:
        _row(conn, "SELECT id FROM topics WHERE id = ?", (topic_id,), "主题")
    if source_id is not None:
        _row(conn, "SELECT id FROM sources WHERE id = ?", (source_id,), "来源")


# ------------------------------------------------------------------ 证据关系

@app.get("/api/relations")
def list_relations(topic_id: int | None = Query(default=None), conn=Depends(db)):
    if topic_id is None:
        rows = conn.execute("SELECT * FROM relations ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            """
            SELECT r.* FROM relations r
            JOIN claims a ON a.id = r.from_claim_id
            JOIN claims b ON b.id = r.to_claim_id
            WHERE a.topic_id = ? AND b.topic_id = ?
            ORDER BY r.id
            """,
            (topic_id, topic_id),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/relations", status_code=201)
def create_relation(body: RelationIn, conn=Depends(db)):
    if body.from_claim_id == body.to_claim_id:
        raise HTTPException(status_code=400, detail="不允许断言与自身建立关系")
    _row(conn, "SELECT id FROM claims WHERE id = ?", (body.from_claim_id,), "起始断言")
    _row(conn, "SELECT id FROM claims WHERE id = ?", (body.to_claim_id,), "目标断言")
    dup = conn.execute(
        "SELECT id FROM relations WHERE from_claim_id = ? AND to_claim_id = ? AND type = ?",
        (body.from_claim_id, body.to_claim_id, body.type),
    ).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail="相同的关系已存在")
    cur = conn.execute(
        "INSERT INTO relations (from_claim_id, to_claim_id, type, note) VALUES (?, ?, ?, ?)",
        (body.from_claim_id, body.to_claim_id, body.type, body.note),
    )
    return dict(_row(conn, "SELECT * FROM relations WHERE id = ?", (cur.lastrowid,), "关系"))


@app.delete("/api/relations/{relation_id}", status_code=204)
def delete_relation(relation_id: int, conn=Depends(db)):
    _row(conn, "SELECT id FROM relations WHERE id = ?", (relation_id,), "关系")
    conn.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
    return Response(status_code=204)


# ------------------------------------------------------------------ 图分析

@app.get("/api/analysis")
def analysis(topic_id: int | None = Query(default=None), conn=Depends(db)):
    if topic_id is not None:
        _row(conn, "SELECT id FROM topics WHERE id = ?", (topic_id,), "主题")
        claims = conn.execute(
            "SELECT * FROM claims WHERE topic_id = ? ORDER BY id", (topic_id,)
        ).fetchall()
        ids = {c["id"] for c in claims}
        relations = [
            r for r in conn.execute("SELECT * FROM relations ORDER BY id").fetchall()
            if r["from_claim_id"] in ids and r["to_claim_id"] in ids
        ]
    else:
        claims = conn.execute("SELECT * FROM claims ORDER BY id").fetchall()
        relations = conn.execute("SELECT * FROM relations ORDER BY id").fetchall()
    result = analyze([dict(c) for c in claims], [dict(r) for r in relations])
    result["topic_id"] = topic_id
    return result


# ------------------------------------------------------------------ 导出

@app.get("/api/export/markdown")
def export_markdown(topic_id: int | None = Query(default=None), conn=Depends(db)):
    if topic_id is not None:
        _row(conn, "SELECT id FROM topics WHERE id = ?", (topic_id,), "主题")
    md = build_markdown(conn, topic_id)
    filename = f"factcheck-{topic_id or 'all'}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------------------------------------------ 前端

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
