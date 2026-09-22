"""Markdown 核查稿导出：按主题组织断言，附证据链与分析摘要。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .analysis import analyze
from .models import KIND_LABELS, REL_LABELS, STATUS_LABELS

STATUS_EMOJI = {"pending": "⏳", "confirmed": "✅", "doubtful": "❓"}
MAX_CHAIN_DEPTH = 4


def _fetch_all(conn: sqlite3.Connection, topic_id: int | None):
    topics = conn.execute(
        "SELECT * FROM topics WHERE id = ? ORDER BY id" if topic_id
        else "SELECT * FROM topics ORDER BY id",
        (topic_id,) if topic_id else (),
    ).fetchall()

    claim_sql = """
        SELECT c.*, t.name AS topic_name, s.title AS source_title, s.kind AS source_kind,
               s.url AS source_url, s.excerpt AS source_excerpt, s.publisher AS source_publisher
        FROM claims c
        LEFT JOIN topics t  ON t.id = c.topic_id
        LEFT JOIN sources s ON s.id = c.source_id
        {where} ORDER BY c.id
    """
    claims = conn.execute(
        claim_sql.format(where="WHERE c.topic_id = ?" if topic_id else ""),
        (topic_id,) if topic_id else (),
    ).fetchall()

    relations = conn.execute("SELECT * FROM relations ORDER BY id").fetchall()
    return topics, claims, relations


def build_markdown(conn: sqlite3.Connection, topic_id: int | None = None) -> str:
    topics, claims, relations = _fetch_all(conn, topic_id)
    claims = [dict(c) for c in claims]
    relations = [dict(r) for r in relations]
    claim_by_id = {c["id"]: c for c in claims}

    lines: list[str] = []
    lines.append("# 采访事实核查稿")
    lines.append("")
    scope = "全部主题"
    if topic_id:
        hit = [t for t in topics if t["id"] == topic_id]
        if hit:
            scope = f"主题：{hit[0]['name']}"
    lines.append(f"> 范围：{scope}　|　导出时间：{datetime.now():%Y-%m-%d %H:%M}")
    lines.append("")

    # 按主题分组（无主题断言归入“未归类”）
    groups: list[tuple[str, list[dict]]] = []
    for t in topics:
        grouped = [c for c in claims if c["topic_id"] == t["id"]]
        if grouped:
            groups.append((t["name"], grouped))
    orphan = [c for c in claims if c["topic_id"] is None]
    if orphan:
        groups.append(("（未归类）", orphan))

    for topic_name, topic_claims in groups:
        topic_claim_ids = {c["id"] for c in topic_claims}
        topic_relations = [
            r for r in relations
            if r["from_claim_id"] in topic_claim_ids and r["to_claim_id"] in topic_claim_ids
        ]
        lines.append(f"## 主题：{topic_name}")
        lines.append("")
        lines.extend(_analysis_section(topic_claims, topic_relations))
        lines.append("")

        for claim in topic_claims:
            lines.extend(_claim_section(claim, claim_by_id, relations))
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*本稿由采访事实核查工作台自动生成，证据链基于编辑录入的断言关系。*")
    lines.append("")
    return "\n".join(lines)


def _analysis_section(claims: list[dict], relations: list[dict]) -> list[str]:
    result = analyze(claims, relations)
    c = result["counts"]
    out = [
        f"**核查概览**：断言 {c['claims']} 条（✅ {c['status_confirmed']} / "
        f"⏳ {c['status_pending']} / ❓ {c['status_doubtful']}），关系 {c['relations']} 条；"
        f"循环引用 {len(result['cycles'])} 处，无来源断言 {len(result['ungrounded'])} 条，"
        f"确认间冲突 {len(result['conflicts'])} 处。",
        "",
    ]
    if result["cycles"]:
        out.append("**⚠ 循环引用**")
        out.append("")
        for cyc in result["cycles"]:
            out.append(f"- {cyc['description']}")
        out.append("")
    if result["ungrounded"]:
        out.append("**⚠ 无来源断言**")
        out.append("")
        for u in result["ungrounded"]:
            out.append(f"- [#{u['id']}] {u['text']}（{u['status_label']}）")
        out.append("")
    if result["conflicts"]:
        out.append("**⚠ 确认间冲突**")
        out.append("")
        for conf in result["conflicts"]:
            out.append(f"- {conf['description']}")
        out.append("")
    return out


def _claim_section(claim: dict, claim_by_id: dict, relations: list[dict]) -> list[str]:
    cid = claim["id"]
    out = [f"### {STATUS_EMOJI.get(claim['status'], '')} [#{cid}] {claim['text']}", ""]
    out.append(f"- **状态**：{STATUS_LABELS.get(claim['status'], claim['status'])}")
    if claim.get("source_title"):
        kind = KIND_LABELS.get(claim.get("source_kind") or "document", "文档")
        src = f"{claim['source_title']}（{kind}）"
        if claim.get("source_publisher"):
            src += f"，{claim['source_publisher']}"
        if claim.get("source_url"):
            src += f"，<{claim['source_url']}>"
        out.append(f"- **来源**：{src}")
        if claim.get("source_excerpt"):
            out.append(f"  > 摘录：{claim['source_excerpt']}")
    else:
        out.append("- **来源**：⚠ 未关联来源")
    if claim.get("notes"):
        out.append(f"- **备注**：{claim['notes']}")

    out.append("- **证据链**：")
    chain = _evidence_chain(cid, claim_by_id, relations)
    if chain:
        out.extend(chain)
    else:
        out.append("  - （暂无关联证据）")
    return out


def _evidence_chain(cid: int, claim_by_id: dict, relations: list[dict]) -> list[str]:
    """证据链：递归展开「被谁支持 / 派生自谁」，并列出反驳关系。"""
    lines: list[str] = []

    def backers(node_id: int, depth: int, visited: set[int]) -> None:
        if depth > MAX_CHAIN_DEPTH:
            return
        for r in relations:
            # 被支持：X supports node
            if r["type"] == "supports" and r["to_claim_id"] == node_id \
                    and r["from_claim_id"] not in visited:
                _emit(r, r["from_claim_id"], depth, visited)
            # 派生上游：node derives Y
            if r["type"] == "derives" and r["from_claim_id"] == node_id \
                    and r["to_claim_id"] not in visited:
                _emit(r, r["to_claim_id"], depth, visited)

    def _emit(rel: dict, other_id: int, depth: int, visited: set[int]) -> None:
        other = claim_by_id.get(other_id)
        if other is None:
            return
        indent = "  " * (depth + 1)
        emoji = STATUS_EMOJI.get(other["status"], "")
        src = f"，来源：{other['source_title']}" if other.get("source_title") else "，⚠ 无来源"
        lines.append(
            f"{indent}- [{REL_LABELS[rel['type']]}] #{other_id} {emoji} "
            f"{other['text']}（{STATUS_LABELS.get(other['status'], other['status'])}{src}）"
        )
        if rel.get("note"):
            lines.append(f"{indent}  - 关系备注：{rel['note']}")
        backers(other_id, depth + 1, visited | {other_id})

    backers(cid, 0, {cid})

    # 反驳关系（双向，不递归）
    for r in relations:
        other_id, arrow = None, ""
        if r["type"] == "refutes" and r["to_claim_id"] == cid:
            other_id, arrow = r["from_claim_id"], "被反驳"
        elif r["type"] == "refutes" and r["from_claim_id"] == cid:
            other_id, arrow = r["to_claim_id"], "反驳"
        if other_id is None:
            continue
        other = claim_by_id.get(other_id)
        if other is None:
            continue
        emoji = STATUS_EMOJI.get(other["status"], "")
        lines.append(
            f"  - [{arrow}] #{other_id} {emoji} {other['text']}"
            f"（{STATUS_LABELS.get(other['status'], other['status'])}）"
        )
        if r.get("note"):
            lines.append(f"    - 关系备注：{r['note']}")
    return lines
