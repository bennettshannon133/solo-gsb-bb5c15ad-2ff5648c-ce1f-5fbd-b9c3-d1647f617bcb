"""采访逐字稿片段 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..database import db
from ..models import Transcript, TranscriptCreate, TranscriptUpdate

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.get("", response_model=list[Transcript])
def list_all():
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM transcripts ORDER BY id")]


@router.post("", response_model=Transcript, status_code=201)
def create(body: TranscriptCreate):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO transcripts (speaker, interviewed, recorded_at, snippet) VALUES (?,?,?,?)",
            (body.speaker.strip(), body.interviewed, body.recorded_at, body.snippet),
        )
        row = conn.execute("SELECT * FROM transcripts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


@router.get("/{transcript_id}", response_model=Transcript)
def detail(transcript_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,)).fetchone()
        if not row:
            raise HTTPException(404, "逐字稿片段不存在")
        return dict(row)


@router.patch("/{transcript_id}", response_model=Transcript)
def update(transcript_id: int, body: TranscriptUpdate):
    fields, params = [], []
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "speaker" and value is not None:
            value = value.strip()
        fields.append(f"{key} = ?")
        params.append(value)
    if not fields:
        raise HTTPException(400, "没有需要更新的字段")
    params.append(transcript_id)
    with db() as conn:
        if not conn.execute("SELECT id FROM transcripts WHERE id = ?", (transcript_id,)).fetchone():
            raise HTTPException(404, "逐字稿片段不存在")
        conn.execute(f"UPDATE transcripts SET {', '.join(fields)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,)).fetchone()
        return dict(row)


@router.delete("/{transcript_id}", status_code=204)
def delete(transcript_id: int):
    with db() as conn:
        if not conn.execute("SELECT id FROM transcripts WHERE id = ?", (transcript_id,)).fetchone():
            raise HTTPException(404, "逐字稿片段不存在")
        conn.execute(
            "DELETE FROM evidences WHERE kind = 'transcript' AND ref_id = ?", (transcript_id,)
        )
        conn.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
