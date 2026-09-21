"""有向证据图分析：循环引用、互斥结论冲突路径、无来源断言、证据闭包。

图模型
------
节点 = 断言。关系边 supports / refutes / derived_from 均为有向边。
- 循环引用：supports + derived_from 构成的简单有向环（refutes 环属于对立而非循环论证）。
- 冲突路径：同一主题下两个断言之间，沿有向边存在“反驳符号为奇数”的路径，
  即路径上 refutes 边数为奇数（supports / derived_from 传递同一结论极性）。
  两端点若均为 confirmed，则为高危冲突。
- 无来源断言：没有直接挂载来源/逐字稿证据的断言；derived_from 可沿派生链
  向上追溯到证据，此时给出“派生链上仍无来源”的判定而非直接判无来源。
"""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable

REL_LABEL = {"supports": "支持", "refutes": "反驳", "derived_from": "派生自"}

MAX_PATH_EDGES = 4   # 冲突/证据路径最大边数，避免指数膨胀
MAX_CYCLES = 100


def _short_claim(text: str, n: int = 22) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _node(a: dict) -> dict:
    return {
        "id": a["id"],
        "label": f"#{a['id']} {_short_claim(a['claim'])}",
        "claim": a["claim"],
        "topic": a["topic"],
        "status": a["status"],
    }


def _edge(r: dict) -> dict:
    return {
        "id": r["id"],
        "source": r["src_id"],
        "target": r["dst_id"],
        "rel_type": r["rel_type"],
        "label": REL_LABEL[r["rel_type"]],
        "rationale": r.get("rationale", ""),
    }


# ---------------------------------------------------------------- 图数据

def build_graph(assertions: list[dict], relations: list[dict]) -> dict:
    """返回给前端力导向图的节点/边结构。"""
    return {
        "nodes": [_node(a) for a in assertions],
        "edges": [_edge(r) for r in relations],
    }


def _adjacency(relations: Iterable[dict], types: set[str]) -> dict[int, list[dict]]:
    adj: dict[int, list[dict]] = {}
    for r in relations:
        if r["rel_type"] in types:
            adj.setdefault(r["src_id"], []).append(r)
    return adj


# ---------------------------------------------------------------- 循环引用

def find_cycles(assertions: list[dict], relations: list[dict]) -> list[dict]:
    """枚举依赖边（supports / derived_from）上的简单有向环。

    去重技巧：只允许以环中最小 id 节点为起点枚举，每个有向环恰好被发现一次。
    """
    adj = _adjacency(relations, {"supports", "derived_from"})
    by_id = {a["id"]: a for a in assertions}
    found: list[dict] = []

    def walk(start: int, node: int, path_nodes: list[int], path_edges: list[dict]) -> None:
        if len(found) >= MAX_CYCLES or len(path_edges) > MAX_PATH_EDGES + 1:
            return
        for e in adj.get(node, []):
            nxt = e["dst_id"]
            if nxt not in by_id or nxt < start:
                continue
            if nxt == start:
                closed_nodes = path_nodes + [start]
                found.append({
                    "kind": "cycle",
                    "node_ids": path_nodes,
                    "nodes": [_node(by_id[n]) for n in closed_nodes],
                    "edges": [_edge(x) for x in path_edges + [e]],
                    "explanation": _explain_cycle(closed_nodes, path_edges + [e], by_id),
                })
                continue
            if nxt in path_nodes:
                continue
            walk(start, nxt, path_nodes + [nxt], path_edges + [e])

    for a in sorted(assertions, key=lambda x: x["id"]):
        walk(a["id"], a["id"], [a["id"]], [])
        if len(found) >= MAX_CYCLES:
            break
    return found


def _explain_cycle(nodes: list[int], edges: list[dict], by_id: dict) -> str:
    parts = []
    for i, e in enumerate(edges):
        src, dst = nodes[i], nodes[(i + 1) % len(nodes)]
        parts.append(
            f"#{src}（{_short_claim(by_id[src]['claim'], 14)}）"
            f"—{REL_LABEL[e['rel_type']]}→"
            f"#{dst}（{_short_claim(by_id[dst]['claim'], 14)}）"
        )
    return "循环论证链：" + "；".join(parts) + "，最终回到起点，无法为链上任一断言提供独立依据。"


# ---------------------------------------------------------------- 冲突路径

def find_signed_paths(
    src: int,
    dst: int,
    adj: dict[int, list[dict]],
    by_id: dict[int, dict],
) -> list[dict]:
    """src → dst 的有向路径，返回其中 refutes 边数为奇数（净反驳）的路径。"""
    results: list[dict] = []

    def walk(node: int, sign: int, p_nodes: list[int], p_edges: list[dict], seen: set[int]) -> None:
        if len(results) >= 20 or len(p_edges) > MAX_PATH_EDGES:
            return
        for e in adj.get(node, []):
            nxt = e["dst_id"]
            if nxt not in by_id or nxt in seen:
                continue
            new_sign = -sign if e["rel_type"] == "refutes" else sign
            if nxt == dst:
                if new_sign < 0:
                    results.append({
                        "node_ids": p_nodes + [dst],
                        "edges": [_edge(x) for x in p_edges + [e]],
                        "refute_count": sum(1 for x in p_edges + [e] if x["rel_type"] == "refutes"),
                    })
                continue
            walk(nxt, new_sign, p_nodes + [nxt], p_edges + [e], seen | {nxt})

    walk(src, 1, [src], [], {src})
    return results


def find_conflicts(assertions: list[dict], relations: list[dict]) -> list[dict]:
    """同主题断言对之间的净反驳路径（两个方向各搜一次，取较短者）。"""
    adj = _adjacency(relations, {"supports", "refutes", "derived_from"})
    by_id = {a["id"]: a for a in assertions}
    topics: dict[str, list[dict]] = {}
    for a in assertions:
        topics.setdefault(a["topic"], []).append(a)

    out: list[dict] = []
    for topic, group in topics.items():
        group = sorted(group, key=lambda x: x["id"])
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                p1 = find_signed_paths(a["id"], b["id"], adj, by_id)
                p2 = find_signed_paths(b["id"], a["id"], adj, by_id)
                paths = sorted(p1 + p2, key=lambda p: (len(p["edges"]), p["refute_count"]))
                if not paths:
                    continue
                best = paths[0]
                statuses = {a["status"], b["status"]}
                if statuses == {"confirmed"}:
                    severity = "high"
                elif "confirmed" in statuses:
                    severity = "medium"
                else:
                    severity = "low"
                out.append({
                    "kind": "conflict",
                    "topic": topic,
                    "severity": severity,
                    "endpoints": [_node(a), _node(b)],
                    "path": {
                        "node_ids": best["node_ids"],
                        "nodes": [_node(by_id[n]) for n in best["node_ids"]],
                        "edges": best["edges"],
                    },
                    "alt_path_count": len(paths) - 1,
                    "explanation": _explain_conflict(a, b, best, by_id),
                })
    rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda c: (rank[c["severity"]], c["topic"], c["endpoints"][0]["id"]))
    return out[:100]


def _explain_conflict(a: dict, b: dict, path: dict, by_id: dict) -> str:
    chain = []
    nodes = path["node_ids"]
    for i, e in enumerate(path["edges"]):
        chain.append(f"#{nodes[i]} —{REL_LABEL[e['rel_type']]}→")
    chain.append(f"#{nodes[-1]}")
    sev_text = {"high": "高危：双方均已确认", "medium": "需关注：一方已确认", "low": "待观察：双方均未确认"}
    return (
        f"主题「{a['topic']}」存在互斥结论："
        f"#{a['id']} 与 #{b['id']}。证据图路径 {' '.join(chain)} "
        f"含 {path['refute_count']} 条反驳边，极性为奇数意味着净反驳。{sev_text[_sev(a, b)]}。"
    )


def _sev(a: dict, b: dict) -> str:
    s = {a["status"], b["status"]}
    if s == {"confirmed"}:
        return "high"
    if "confirmed" in s:
        return "medium"
    return "low"


# ---------------------------------------------------------------- 无来源 / 证据闭包

def evidence_closure(
    assertion_id: int,
    relations: list[dict],
    direct: dict[int, list[dict]],
) -> dict:
    """沿 derived_from 边向上 BFS，收集传递可达的全部证据与派生链。"""
    deriv = _adjacency(relations, {"derived_from"})
    visited: set[int] = {assertion_id}
    queue = deque([(assertion_id, [assertion_id])])
    chains: list[list[int]] = []
    evidences: list[dict] = []
    seen_ev: set[tuple[str, int]] = set()

    while queue:
        node, chain = queue.popleft()
        node_ev = direct.get(node, [])
        if node_ev:
            chains.append(chain)
        for ev in node_ev:
            key = (ev["kind"], ev["ref_id"])
            if key not in seen_ev:
                seen_ev.add(key)
                evidences.append(ev)
        for e in deriv.get(node, []):
            nxt = e["dst_id"]
            if nxt not in visited and len(chain) <= MAX_PATH_EDGES:
                visited.add(nxt)
                queue.append((nxt, chain + [nxt]))

    return {"evidences": evidences, "chains": chains}


def find_unsourced(
    assertions: list[dict],
    relations: list[dict],
    direct: dict[int, list[dict]],
) -> list[dict]:
    """无直接证据，且沿派生链向上也追溯不到任何证据的断言。"""
    out = []
    for a in assertions:
        if direct.get(a["id"]):
            continue
        closure = evidence_closure(a["id"], relations, direct)
        if closure["evidences"]:
            continue
        out.append({
            "kind": "unsourced",
            "assertion": _node(a),
            "explanation": (
                f"断言 #{a['id']}（{_short_claim(a['claim'], 14)}）未挂载任何来源文档或逐字稿片段，"
                "派生链上游同样没有证据，无法进入已确认状态。"
            ),
        })
    out.sort(key=lambda x: (x["assertion"]["status"] != "confirmed", x["assertion"]["id"]))
    return out


# ---------------------------------------------------------------- 汇总分析

def run_analysis(assertions: list[dict], relations: list[dict], evidences: list[dict]) -> dict:
    direct: dict[int, list[dict]] = {}
    for ev in evidences:
        direct.setdefault(ev["assertion_id"], []).append(ev)

    cycles = find_cycles(assertions, relations)
    conflicts = find_conflicts(assertions, relations)
    unsourced = find_unsourced(assertions, relations, direct)

    counts = {"assertions": len(assertions), "relations": len(relations), "evidences": len(evidences)}
    by_status = {"pending": 0, "confirmed": 0, "doubtful": 0}
    for a in assertions:
        by_status[a["status"]] += 1

    return {
        "summary": {
            **counts,
            "by_status": by_status,
            "cycles": len(cycles),
            "conflicts": len(conflicts),
            "unsourced": len(unsourced),
        },
        "cycles": cycles,
        "conflicts": conflicts,
        "unsourced": unsourced,
    }
