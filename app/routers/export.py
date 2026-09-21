"""导出 Markdown 核查稿。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response

from ..database import db
from ..report import build_markdown

router = APIRouter(prefix="/api/export", tags=["export"])


def _filename(topic: str | None) -> str:
    base = "factcheck" if not topic else "factcheck-" + topic.replace("/", "-").replace(" ", "_")
    return quote(f"{base}.md")


@router.get("/markdown")
def export_markdown(topic: str | None = None):
    with db() as conn:
        content = build_markdown(topic, conn)
    fname = _filename(topic)
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )
