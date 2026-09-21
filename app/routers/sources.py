"""来源文档与逐字稿片段 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..database import db
from ..models import Source, SourceCreate, SourceUpdate

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[Source])
def list_all():
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY id")]


@router.post("", response_model=Source, status_code=201)
def create(body: SourceCreate):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO sources (title, publisher, doc_date, url, content) VALUES (?,?,?,?,?)",
            (body.title.strip(), body.publisher, body.doc_date, body.url, body.content),
        )
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


@router.get("/{source_id}", response_model=Source)
def detail(source_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            raise HTTPException(404, "来源不存在")
        return dict(row)


@router.patch("/{source_id}", response_model=Source)
def update(source_id: int, body: SourceUpdate):
    fields, params = [], []
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "title" and value is not None:
            value = value.strip()
        fields.append(f"{key} = ?")
        params.append(value)
    if not fields:
        raise HTTPException(400, "没有需要更新的字段")
    params.append(source_id)
    with db() as conn:
        if not conn.execute("SELECT id FROM sources WHERE id = ?", (source_id,)).fetchone():
            raise HTTPException(404, "来源不存在")
        conn.execute(f"UPDATE sources SET {', '.join(fields)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row)


@router.delete("/{source_id}", status_code=204)
def delete(source_id: int):
    with db() as conn:
        if not conn.execute("SELECT id FROM sources WHERE id = ?", (source_id,)).fetchone():
            raise HTTPException(404, "来源不存在")
        conn.execute("DELETE FROM evidences WHERE kind = 'source' AND ref_id = ?", (source_id,))
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
