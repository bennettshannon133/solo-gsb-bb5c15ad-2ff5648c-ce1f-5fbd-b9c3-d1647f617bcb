"""图算法规格测试（纯标准库，直接运行：python tests/test_graph.py）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import graph as G  # noqa: E402


def A(i, topic="T", status="confirmed"):
    return {"id": i, "claim": f"断言{i}", "topic": topic, "status": status}


def R(rid, s, d, t):
    return {"id": rid, "src_id": s, "dst_id": d, "rel_type": t, "rationale": ""}


def test_cycle_enumeration_dedup():
    asg = [A(i) for i in range(1, 5)]
    rels = [
        R(1, 1, 2, "supports"), R(2, 2, 3, "supports"), R(3, 3, 4, "supports"),
        R(4, 4, 1, "derived_from"), R(5, 1, 3, "supports"), R(6, 3, 1, "supports"),
    ]
    rings = sorted(tuple(c["node_ids"]) for c in G.find_cycles(asg, rels))
    assert rings == [(1, 2, 3), (1, 2, 3, 4), (1, 3), (1, 3, 4)], rings


def test_refutes_not_a_cycle():
    assert G.find_cycles([A(1), A(2)], [R(1, 1, 2, "supports"), R(2, 2, 1, "refutes")]) == []


def test_signed_polarity():
    asg = [A(1), A(2), A(3)]
    rels = [R(1, 1, 2, "refutes"), R(2, 2, 3, "refutes"), R(3, 1, 3, "supports")]
    pairs = sorted(
        tuple(sorted((c["endpoints"][0]["id"], c["endpoints"][1]["id"])))
        for c in G.find_conflicts(asg, rels)
    )
    assert pairs == [(1, 2), (2, 3)], pairs  # 偶数次 refutes 的 1↔3 净支持，不报冲突


def test_support_and_refute_between_same_pair():
    cf = G.find_conflicts([A(1), A(2)], [R(1, 1, 2, "supports"), R(2, 1, 2, "refutes")])
    assert len(cf) == 1 and cf[0]["path"]["edges"][0]["rel_type"] == "refutes"


def test_evidence_closure_and_unsourced():
    rels = [R(1, 1, 2, "derived_from")]
    direct = {2: [{"id": 1, "assertion_id": 2, "kind": "source", "ref_id": 1,
                   "quote": "", "created_at": ""}]}
    assert G.find_unsourced([A(1), A(2)], rels, direct) == []
    cl = G.evidence_closure(1, rels, direct)
    assert len(cl["evidences"]) == 1 and cl["chains"] == [[1, 2]]
    assert {u["assertion"]["id"] for u in G.find_unsourced([A(1), A(2)], rels, {})} == {1, 2}


def test_diamond_derived_closure():
    rels = [R(1, 1, 2, "derived_from"), R(2, 1, 3, "derived_from")]
    direct = {
        2: [{"id": 1, "assertion_id": 2, "kind": "source", "ref_id": 1, "quote": "", "created_at": ""}],
        3: [{"id": 2, "assertion_id": 3, "kind": "transcript", "ref_id": 1, "quote": "", "created_at": ""}],
    }
    cl = G.evidence_closure(1, rels, direct)
    assert len(cl["evidences"]) == 2 and sorted(cl["chains"]) == [[1, 2], [1, 3]]


def test_cross_topic_no_conflict():
    assert G.find_conflicts([A(1, "T1"), A(2, "T2")], [R(1, 1, 2, "refutes")]) == []


def test_cycle_shape():
    cy = G.find_cycles([A(1), A(2)], [R(1, 1, 2, "supports"), R(2, 2, 1, "supports")])
    assert cy[0]["node_ids"] == [1, 2]
    assert len(cy[0]["nodes"]) == 3 and len(cy[0]["edges"]) == 2


def test_severity_levels():
    def sev(s1, s2):
        return G.find_conflicts(
            [{"id": 1, "claim": "a", "topic": "T", "status": s1},
             {"id": 2, "claim": "b", "topic": "T", "status": s2}],
            [R(1, 1, 2, "refutes")],
        )[0]["severity"]
    assert sev("confirmed", "confirmed") == "high"
    assert sev("confirmed", "pending") == "medium"
    assert sev("pending", "doubtful") == "low"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    if failures:
        sys.exit(1)
    print("\nALL GRAPH TESTS PASSED")
