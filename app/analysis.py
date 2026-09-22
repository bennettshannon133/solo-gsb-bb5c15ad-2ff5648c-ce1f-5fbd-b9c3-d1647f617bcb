"""有向证据图分析：循环引用检测、无来源断言识别、互斥结论冲突路径。

图语义约定：
- supports（支持）:A 支持 B —— A 是 B 的佐证，确认状态沿 A -> B 正向传播；
- refutes （反驳）:A 反驳 B —— A 与 B 互斥，双方均被证实时构成冲突；
- derives （派生自）:A 派生自 B —— B 是 A 的上游依据，确认状态沿 B -> A 反向传播，
  溯源（grounding）沿 A -> B 方向向上寻找来源。
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .models import REL_LABELS, STATUS_LABELS

MAX_CYCLES = 50
MAX_CYCLE_LEN = 10


# ---------------------------------------------------------------- 工具

def _claim_brief(claim: dict) -> dict:
    return {
        "id": claim["id"],
        "text": claim["text"],
        "status": claim["status"],
        "status_label": STATUS_LABELS.get(claim["status"], claim["status"]),
    }


def _edge_brief(rel: dict) -> dict:
    return {
        "relation_id": rel["id"],
        "from": rel["from_claim_id"],
        "to": rel["to_claim_id"],
        "type": rel["type"],
        "label": REL_LABELS[rel["type"]],
    }


# ---------------------------------------------------------------- 循环引用

def find_cycles(claims: list[dict], relations: list[dict]) -> list[dict]:
    """在全部关系边构成的有向图上查找基本回路（按节点集合去重）。"""
    ids = {c["id"] for c in claims}
    adj: dict[int, list[dict]] = defaultdict(list)
    for r in relations:
        if r["from_claim_id"] in ids and r["to_claim_id"] in ids:
            adj[r["from_claim_id"]].append(r)

    claim_by_id = {c["id"]: c for c in claims}
    seen: set[tuple] = set()
    cycles: list[dict] = []

    for start in sorted(ids):
        # 迭代式 DFS：从 start 出发寻找回到 start 的路径
        stack: list[tuple[int, list[int], list[dict]]] = [(start, [start], [])]
        while stack:
            node, path, edges = stack.pop()
            for rel in adj.get(node, []):
                nxt = rel["to_claim_id"]
                if nxt == start:
                    key = _canonical(path)
                    if key not in seen:
                        seen.add(key)
                        cycle_edges = edges + [rel]
                        cycles.append({
                            "claims": [_claim_brief(claim_by_id[i]) for i in path],
                            "edges": [_edge_brief(e) for e in cycle_edges],
                            "description": _describe_cycle(path, cycle_edges),
                        })
                        if len(cycles) >= MAX_CYCLES:
                            return cycles
                elif nxt not in path and len(path) < MAX_CYCLE_LEN:
                    stack.append((nxt, path + [nxt], edges + [rel]))
    return cycles


def _canonical(nodes: list[int]) -> tuple:
    """将回路旋转到最小节点开头，用于去重。"""
    i = nodes.index(min(nodes))
    return tuple(nodes[i:] + nodes[:i])


def _describe_cycle(nodes: list[int], edges: list[dict]) -> str:
    parts = [f"#{nodes[0]}"]
    for e in edges:
        parts.append(f"--{REL_LABELS[e['type']]}--> #{e['to_claim_id']}")
    return "循环引用：" + " ".join(parts)


# ---------------------------------------------------------------- 无来源断言

def find_ungrounded(claims: list[dict], relations: list[dict]) -> dict[str, Any]:
    """识别无来源断言。

    - no_direct_source：未直接关联来源文档/逐字稿的断言（提示级）；
    - ungrounded：既无直接来源，沿「派生自」链向上也无法抵达任何有来源断言（问题级）。
    """
    derives_up: dict[int, list[int]] = defaultdict(list)
    for r in relations:
        if r["type"] == "derives":
            derives_up[r["from_claim_id"]].append(r["to_claim_id"])

    claim_by_id = {c["id"]: c for c in claims}
    cache: dict[int, bool] = {}

    def grounded(cid: int, visiting: set[int]) -> bool:
        if cid in cache:
            return cache[cid]
        claim = claim_by_id.get(cid)
        if claim is None:
            return False
        if claim["source_id"]:
            cache[cid] = True
            return True
        if cid in visiting:  # 派生环内且无来源
            return False
        visiting.add(cid)
        for parent in derives_up.get(cid, []):
            if grounded(parent, visiting):
                visiting.discard(cid)
                cache[cid] = True
                return True
        visiting.discard(cid)
        cache[cid] = False
        return False

    no_direct, ungrounded = [], []
    for c in claims:
        brief = _claim_brief(c)
        brief["topic_id"] = c["topic_id"]
        if not c["source_id"]:
            no_direct.append(brief)
        if not grounded(c["id"], set()):
            ungrounded.append(brief)
    return {"no_direct_source": no_direct, "ungrounded": ungrounded}


# ---------------------------------------------------------------- 互斥结论冲突

def _endorsement_paths(claims: list[dict], relations: list[dict]) -> dict[int, list[dict]]:
    """计算每条断言的「证实路径」：从已确认断言出发，沿支持边正向、派生边反向传播。

    返回 {claim_id: [{"root": 已确认断言id, "path": [关系...]}, ...]}，
    已确认断言自身带有空路径。
    """
    claim_ids = {c["id"] for c in claims}
    positive: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    for r in relations:
        if r["type"] == "supports":
            positive[r["from_claim_id"]].append((r["to_claim_id"], r))
        elif r["type"] == "derives":
            positive[r["to_claim_id"]].append((r["from_claim_id"], r))

    endorsed: dict[int, list[dict]] = defaultdict(list)
    for c in claims:
        if c["status"] != "confirmed":
            continue
        root = c["id"]
        visited = {root}
        queue: deque[tuple[int, list[dict]]] = deque([(root, [])])
        while queue:
            node, path = queue.popleft()
            endorsed[node].append({"root": root, "path": path})
            for nxt, rel in positive.get(node, []):
                if nxt in claim_ids and nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [rel]))
    return endorsed


def _describe_endorsement(entry: dict) -> str:
    """把证实路径翻译成可读中文，如：#3(已确认) 经「#3 支持 #4」得到证实。"""
    root, path = entry["root"], entry["path"]
    if not path:
        return f"#{root} 本身已确认"
    steps = []
    for r in path:
        if r["type"] == "supports":
            steps.append(f"#{r['from_claim_id']} 支持 #{r['to_claim_id']}")
        else:  # derives 反向传播：B 证实 A（A 派生自 B）
            steps.append(f"#{r['to_claim_id']} 派生自 #{r['from_claim_id']}")
    return f"#{root}(已确认) 经「{'；'.join(steps)}」得到证实"


def find_conflicts(claims: list[dict], relations: list[dict]) -> dict[str, list]:
    """检测同一主题下的互斥结论。

    - conflicts：反驳边两端均被证实（已确认或由已确认断言传播证实），给出可解释路径；
    - potential_conflicts：存在反驳边但尚未双方均被证实，提示关注。
    """
    claim_by_id = {c["id"]: c for c in claims}
    endorsed = _endorsement_paths(claims, relations)

    conflicts, potentials = [], []
    for r in relations:
        if r["type"] != "refutes":
            continue
        a_id, b_id = r["from_claim_id"], r["to_claim_id"]
        a, b = claim_by_id.get(a_id), claim_by_id.get(b_id)
        if a is None or b is None:
            continue
        a_paths, b_paths = endorsed.get(a_id), endorsed.get(b_id)
        base = {
            "relation_id": r["id"],
            "note": r["note"],
            "refuter": _claim_brief(a),
            "refuted": _claim_brief(b),
        }
        if a_paths and b_paths:
            ea, eb = a_paths[0], b_paths[0]
            desc_a, desc_b = _describe_endorsement(ea), _describe_endorsement(eb)
            conflicts.append({
                **base,
                "refuter_path": [_edge_brief(x) for x in ea["path"]],
                "refuted_path": [_edge_brief(x) for x in eb["path"]],
                "description": (
                    f"{desc_a}，{desc_b}，"
                    f"但 #{a_id} 反驳 #{b_id}，两者不能同时成立——存在冲突。"
                ),
            })
        else:
            potentials.append({
                **base,
                "reason": (
                    f"反驳方 #{a_id}（{STATUS_LABELS[a['status']]}）与 "
                    f"被反驳方 #{b_id}（{STATUS_LABELS[b['status']]}）尚未均被证实"
                ),
            })
    return {"conflicts": conflicts, "potential_conflicts": potentials}


# ---------------------------------------------------------------- 汇总入口

def analyze(claims: list[dict], relations: list[dict]) -> dict:
    """对（可按主题过滤后的）断言与关系执行全部分析。"""
    claim_rows = [dict(c) for c in claims]
    rel_rows = [dict(r) for r in relations]

    grounding = find_ungrounded(claim_rows, rel_rows)
    conflict_result = find_conflicts(claim_rows, rel_rows)
    cycles = find_cycles(claim_rows, rel_rows)

    status_counts = {"pending": 0, "confirmed": 0, "doubtful": 0}
    for c in claim_rows:
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    return {
        "counts": {
            "claims": len(claim_rows),
            "relations": len(rel_rows),
            **{f"status_{k}": v for k, v in status_counts.items()},
        },
        "cycles": cycles,
        "ungrounded": grounding["ungrounded"],
        "no_direct_source": grounding["no_direct_source"],
        "conflicts": conflict_result["conflicts"],
        "potential_conflicts": conflict_result["potential_conflicts"],
    }
