"""生成带证据链的 Markdown 核查稿。"""
from __future__ import annotations

from datetime import datetime

from . import graph as graphlib

STATUS_LABEL = {"pending": "⏳ 待核查", "confirmed": "✅ 已确认", "doubtful": "❓ 存疑"}
REL_LABEL = graphlib.REL_LABEL
SEV_LABEL = {"high": "🔴 高危", "medium": "🟠 需关注", "low": "🟡 待观察"}


def _md_escape(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _chain_md(chain_ids: list[int], by_id: dict) -> str:
    return " → ".join(f"#{i}（{STATUS_LABEL[by_id[i]['status']].split(' ')[-1]}）" for i in chain_ids)


def _path_md(path: dict) -> str:
    nodes = path["node_ids"]
    edges = path["edges"]
    parts = [f"#{nodes[0]}"]
    for i, e in enumerate(edges):
        parts.append(f" --{REL_LABEL[e['rel_type']]}--> #{nodes[i + 1]}")
    return "".join(parts)


def build_markdown(topic: str | None, conn) -> str:
    assertions = [
        dict(r) for r in conn.execute("SELECT * FROM assertions ORDER BY topic, id")
    ]
    if topic:
        assertions = [a for a in assertions if a["topic"] == topic]
    keep = {a["id"] for a in assertions}
    by_id = {a["id"]: a for a in assertions}

    relations = [
        dict(r)
        for r in conn.execute("SELECT * FROM relations ORDER BY id")
        if r["src_id"] in keep and r["dst_id"] in keep
    ]
    evidences = [
        dict(r)
        for r in conn.execute("SELECT * FROM evidences ORDER BY id")
        if r["assertion_id"] in keep
    ]
    sources = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM sources")}
    transcripts = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM transcripts")}

    analysis = graphlib.run_analysis(assertions, relations, evidences)

    direct: dict[int, list[dict]] = {}
    for ev in evidences:
        direct.setdefault(ev["assertion_id"], []).append(ev)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"事实核查稿：{topic}" if topic else "事实核查稿（全部主题）"
    lines: list[str] = [
        f"# {title}",
        "",
        f"> 生成时间：{now}　断言 {analysis['summary']['assertions']} 条 / "
        f"关系 {analysis['summary']['relations']} 条 / 证据 {analysis['summary']['evidences']} 条",
        ">",
        f"> 状态分布：待核查 {analysis['summary']['by_status']['pending']}，"
        f"已确认 {analysis['summary']['by_status']['confirmed']}，"
        f"存疑 {analysis['summary']['by_status']['doubtful']}",
        "",
        "## 一、核查问题总览",
        "",
        f"- 循环引用：**{analysis['summary']['cycles']}** 处",
        f"- 同主题互斥结论：**{analysis['summary']['conflicts']}** 对",
        f"- 无来源断言：**{analysis['summary']['unsourced']}** 条",
        "",
    ]

    # ---- 互斥冲突 ----
    lines.append("## 二、互斥结论与冲突路径")
    lines.append("")
    if not analysis["conflicts"]:
        lines.append("未发现同主题互斥结论。")
    for c in analysis["conflicts"]:
        e0, e1 = c["endpoints"]
        lines += [
            f"### {SEV_LABEL[c['severity']]} #{e0['id']} ⚔ #{e1['id']}（主题：{c['topic']}）",
            "",
            f"- 断言 A：{e0['claim']}（{STATUS_LABEL[e0['status']]}）",
            f"- 断言 B：{e1['claim']}（{STATUS_LABEL[e1['status']]}）",
            f"- 冲突路径：`{_path_md(c['path'])}`",
        ]
        for i, node in enumerate(c["path"]["nodes"]):
            edge = c["path"]["edges"][i - 1] if i else None
            prefix = f"  {i + 1}. " if i else "  起点："
            line = f"{prefix}#{node['id']}（{STATUS_LABEL[node['status']].split(' ')[-1]}）{node['claim']}"
            if edge and edge["rationale"]:
                line += f"  ← 边注：{edge['rationale']}"
            lines.append(line)
        if c["alt_path_count"]:
            lines.append(f"- 另有 {c['alt_path_count']} 条冲突路径（工作台查看）")
        lines += ["- " + c["explanation"], ""]

    # ---- 循环引用 ----
    lines.append("## 三、循环引用")
    lines.append("")
    if not analysis["cycles"]:
        lines.append("未发现循环引用。")
        lines.append("")
    for cyc in analysis["cycles"]:
        lines.append(f"### 环：{' → '.join('#' + str(n) for n in cyc['node_ids'])} → #{cyc['node_ids'][0]}")
        lines.append("")
        for i, e in enumerate(cyc["edges"]):
            lines.append(
                f"- #{e['source']} --{REL_LABEL[e['rel_type']]}--> #{e['target']}"
                + (f"：{e['rationale']}" if e["rationale"] else "")
            )
        lines += ["- " + cyc["explanation"], ""]

    # ---- 无来源 ----
    lines.append("## 四、无来源断言")
    lines.append("")
    if not analysis["unsourced"]:
        lines.append("所有断言均可追溯到来源文档或逐字稿片段。")
        lines.append("")
    for u in analysis["unsourced"]:
        n = u["assertion"]
        lines.append(f"- [{STATUS_LABEL[n['status']].split(' ')[-1]}] #{n['id']}（{n['topic']}）{n['claim']}")
    if analysis["unsourced"]:
        lines.append("")

    # ---- 断言明细与证据链 ----
    lines.append("## 五、断言明细与证据链")
    lines.append("")
    current_topic = None
    for a in assertions:
        if a["topic"] != current_topic:
            current_topic = a["topic"]
            lines.append(f"### 主题：{current_topic}")
            lines.append("")
        lines.append(f"#### #{a['id']} {a['claim']}")
        lines.append("")
        lines.append(f"- 状态：**{STATUS_LABEL[a['status']]}**")
        if a["note"]:
            lines.append(f"- 编辑备注：{_md_escape(a['note'])}")

        closure = graphlib.evidence_closure(a["id"], relations, direct)
        if closure["evidences"]:
            lines.append("- 证据链：")
            shown = set()
            for ev in closure["evidences"]:
                key = (ev["kind"], ev["ref_id"])
                if key in shown:
                    continue
                shown.add(key)
                if ev["kind"] == "source":
                    s = sources.get(ev["ref_id"])
                    if s:
                        meta = " / ".join(x for x in (s["publisher"], s["doc_date"]) if x)
                        lines.append(f"    - 📄 来源文档 **{s['title']}**" + (f"（{meta}）" if meta else ""))
                        if s["url"]:
                            lines.append(f"      - 链接：{s['url']}")
                else:
                    t = transcripts.get(ev["ref_id"])
                    if t:
                        meta = " / ".join(x for x in (t["speaker"], t["recorded_at"]) if x)
                        lines.append(f"    - 🎙 逐字稿片段（{meta}）")
                if ev["quote"]:
                    lines.append(f"      > {_md_escape(ev['quote'])}")
            if not direct.get(a["id"]) and closure["chains"]:
                chains = "; ".join(_chain_md(c, by_id) for c in closure["chains"][:3])
                lines.append(f"    - 证据经派生链追溯：{chains}")
        else:
            lines.append("- ⚠️ 证据链：**无任何可追溯证据**")

        outgoing = [r for r in relations if r["src_id"] == a["id"]]
        incoming = [r for r in relations if r["dst_id"] == a["id"]]
        for r in outgoing:
            lines.append(
                f"- 关系：#{r['src_id']} --{REL_LABEL[r['rel_type']]}--> #{r['dst_id']}"
                + (f"：{_md_escape(r['rationale'])}" if r["rationale"] else "")
            )
        for r in incoming:
            if r["src_id"] == a["id"]:
                continue
            lines.append(
                f"- 反向关系：#{r['src_id']} --{REL_LABEL[r['rel_type']]}--> 本断言"
                + (f"：{_md_escape(r['rationale'])}" if r["rationale"] else "")
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
