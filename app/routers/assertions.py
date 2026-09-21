"""断言 CRUD、状态流转、证据挂载、断言间关系。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..database import db
from ..models import (
    Assertion,
    AssertionCreate,
    AssertionUpdate,
    Evidence,
    EvidenceCreate,
    Relation,
    RelationCreate,
)
from ..serializers import (
    all_for_graph,
    evidence_with_refs,
    get_assertion,
    list_assertions,
    relations_for,
    touch_assertion,
)
from .. import graph as graphlib

router = APIRouter(prefix="/api/assertions", tags=["assertions"])


@router.get("", response_model=list[Assertion])
def list_all(topic: str | None = None, status: str | None = Query(default=None)):
    with db() as conn:
        return list_assertions(conn, topic, status)


@router.get("/topics")
def topics():
    with db() as conn:
        rows = conn.execute(
            "SELECT topic, COUNT(*) AS n FROM assertions GROUP BY topic ORDER BY topic"
        ).fetchall()
    return [{"topic": r["topic"], "count": r["n"]} for r in rows]


@router.post("", response_model=Assertion, status_code=201)
def create(body: AssertionCreate):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
            (body.claim.strip(), body.topic.strip(), body.status, body.note),
        )
        row = conn.execute("SELECT * FROM assertions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


@router.get("/{assertion_id}")
def detail(assertion_id: int):
    with db() as conn:
        a = get_assertion(conn, assertion_id)
        if not a:
            raise HTTPException(404, "断言不存在")
        ev = evidence_with_refs(conn, assertion_id)
        outgoing, incoming = relations_for(conn, assertion_id)
        assertions, relations, direct_ev = all_for_graph(conn)
        closure = graphlib.evidence_closure(assertion_id, relations, _group_ev(direct_ev))
        by_id = {x["id"]: x for x in assertions}
        closure["chains"] = [
            [{"id": i, "claim": by_id[i]["claim"], "status": by_id[i]["status"]} for i in chain]
            for chain in closure["chains"]
        ]
    return {
        "assertion": a,
        "evidence": ev,
        "outgoing_relations": outgoing,
        "incoming_relations": incoming,
        "evidence_closure": closure,
    }


def _group_ev(evs):
    grouped: dict[int, list[dict]] = {}
    for e in evs:
        grouped.setdefault(e["assertion_id"], []).append(e)
    return grouped


@router.patch("/{assertion_id}", response_model=Assertion)
def update(assertion_id: int, body: AssertionUpdate):
    fields, params = [], []
    for key, value in body.model_dump(exclude_unset=True).items():
        if key in ("claim", "topic") and value is not None:
            value = value.strip()
        fields.append(f"{key} = ?")
        params.append(value)
    if not fields:
        raise HTTPException(400, "没有需要更新的字段")
    fields.append("updated_at = datetime('now')")
    params.append(assertion_id)
    with db() as conn:
        if not get_assertion(conn, assertion_id):
            raise HTTPException(404, "断言不存在")
        conn.execute(f"UPDATE assertions SET {', '.join(fields)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM assertions WHERE id = ?", (assertion_id,)).fetchone()
        return dict(row)


@router.delete("/{assertion_id}", status_code=204)
def delete(assertion_id: int):
    with db() as conn:
        if not get_assertion(conn, assertion_id):
            raise HTTPException(404, "断言不存在")
        conn.execute("DELETE FROM assertions WHERE id = ?", (assertion_id,))


# ---------------- 证据挂载 ----------------

@router.post("/{assertion_id}/evidence", response_model=Evidence, status_code=201)
def add_evidence(assertion_id: int, body: EvidenceCreate):
    with db() as conn:
        if not get_assertion(conn, assertion_id):
            raise HTTPException(404, "断言不存在")
        table = "sources" if body.kind == "source" else "transcripts"
        exists = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (body.ref_id,)).fetchone()
        if not exists:
            raise HTTPException(400, "引用的来源/逐字稿不存在")
        try:
            cur = conn.execute(
                "INSERT INTO evidences (assertion_id, kind, ref_id, quote) VALUES (?,?,?,?)",
                (assertion_id, body.kind, body.ref_id, body.quote),
            )
        except Exception as exc:  # UNIQUE 冲突
            raise HTTPException(409, "该证据已挂载到此断言") from exc
        touch_assertion(conn, assertion_id)
        row = conn.execute("SELECT * FROM evidences WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


@router.delete("/{assertion_id}/evidence/{evidence_id}", status_code=204)
def remove_evidence(assertion_id: int, evidence_id: int):
    with db() as conn:
        cur = conn.execute(
            "DELETE FROM evidences WHERE id = ? AND assertion_id = ?",
            (evidence_id, assertion_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "证据不存在")
        touch_assertion(conn, assertion_id)


# ---------------- 断言间关系 ----------------

@router.post("/relations", response_model=Relation, status_code=201)
def create_relation(body: RelationCreate):
    if body.src_id == body.dst_id:
        raise HTTPException(400, "断言不能与自身建立关系")
    with db() as conn:
        if not get_assertion(conn, body.src_id):
            raise HTTPException(404, "起始断言不存在")
        if not get_assertion(conn, body.dst_id):
            raise HTTPException(404, "目标断言不存在")
        try:
            cur = conn.execute(
                "INSERT INTO relations (src_id, dst_id, rel_type, rationale) VALUES (?,?,?,?)",
                (body.src_id, body.dst_id, body.rel_type, body.rationale),
            )
        except Exception as exc:
            raise HTTPException(409, "这两个断言之间已存在同类型关系") from exc
        touch_assertion(conn, body.src_id)
        touch_assertion(conn, body.dst_id)
        row = conn.execute("SELECT * FROM relations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


@router.delete("/relations/{relation_id}", status_code=204)
def delete_relation(relation_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM relations WHERE id = ?", (relation_id,)).fetchone()
        if not row:
            raise HTTPException(404, "关系不存在")
        conn.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
        touch_assertion(conn, row["src_id"])
        touch_assertion(conn, row["dst_id"])
