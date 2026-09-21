"""证据图数据与全量核查分析（循环、冲突、无来源）。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import graph as graphlib
from ..serializers import load_tables

router = APIRouter(prefix="/api", tags=["analysis"])


def _filter(assertions, relations, topic):
    if not topic:
        return assertions, relations
    keep = {a["id"] for a in assertions if a["topic"] == topic}
    return (
        [a for a in assertions if a["id"] in keep],
        [r for r in relations if r["src_id"] in keep and r["dst_id"] in keep],
    )


@router.get("/graph")
def graph(topic: str | None = None):
    assertions, relations, _ = load_tables()
    assertions, relations = _filter(assertions, relations, topic)
    return graphlib.build_graph(assertions, relations)


@router.get("/analysis")
def analysis(topic: str | None = None):
    assertions, relations, evidences = load_tables()
    assertions, relations = _filter(assertions, relations, topic)
    keep = {a["id"] for a in assertions}
    evidences = [e for e in evidences if e["assertion_id"] in keep]
    return graphlib.run_analysis(assertions, relations, evidences)
