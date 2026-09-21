"""端到端 HTTP 冒烟测试（需先启动服务：uvicorn app.main:app --port 8000）。

用法：python tests/test_api_e2e.py
仅依赖标准库；使用独立主题前缀，测试结束自动清理创建的数据。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000")
PREFIX = "E2E-" + uuid.uuid4().hex[:8]
created = {"assertions": [], "sources": [], "transcripts": []}


def req(method, path, body=None, expect=200):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(r) as resp:
            assert resp.status == expect, f"{method} {path}: {resp.status} != {expect}"
            text = resp.read().decode()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        assert e.code == expect, f"{method} {path}: {e.code} != {expect}\n{e.read().decode()}"


def cleanup():
    for aid in created["assertions"]:
        try:
            req("DELETE", f"/api/assertions/{aid}", expect=204)
        except AssertionError:
            pass
    for sid in created["sources"]:
        try:
            req("DELETE", f"/api/sources/{sid}", expect=204)
        except AssertionError:
            pass
    for tid in created["transcripts"]:
        try:
            req("DELETE", f"/api/transcripts/{tid}", expect=204)
        except AssertionError:
            pass


def main():
    # 健康检查（给刚启动的服务一点时间）
    for _ in range(10):
        try:
            assert req("GET", "/api/health")["status"] == "ok"
            break
        except (OSError, AssertionError):
            time.sleep(0.5)
    else:
        raise SystemExit("服务未就绪")

    t1, t2 = PREFIX + "-T1", PREFIX + "-T2"
    x = req("POST", "/api/assertions", {"claim": "X 排放超标", "topic": t1}, 201)
    y = req("POST", "/api/assertions", {"claim": "Y 由 X 派生", "topic": t1}, 201)
    z = req("POST", "/api/assertions", {"claim": "Z 与 X 互斥", "topic": t1}, 201)
    created["assertions"] += [x["id"], y["id"], z["id"]]

    src = req("POST", "/api/sources", {"title": PREFIX + " 监测报告", "content": "超标"}, 201)
    tr = req("POST", "/api/transcripts", {"speaker": "举报人", "snippet": "偷排"}, 201)
    created["sources"].append(src["id"])
    created["transcripts"].append(tr["id"])

    # 证据挂载与校验
    req("POST", f"/api/assertions/{x['id']}/evidence",
        {"kind": "source", "ref_id": src["id"], "quote": "超标"}, 201)
    req("POST", f"/api/assertions/{x['id']}/evidence",
        {"kind": "transcript", "ref_id": tr["id"]}, 201)
    req("POST", f"/api/assertions/{x['id']}/evidence",
        {"kind": "source", "ref_id": src["id"]}, 409)
    req("POST", f"/api/assertions/{x['id']}/evidence",
        {"kind": "source", "ref_id": 999999}, 400)

    # 关系与校验
    req("POST", "/api/assertions/relations",
        {"src_id": y["id"], "dst_id": x["id"], "rel_type": "derived_from"}, 201)
    req("POST", "/api/assertions/relations",
        {"src_id": x["id"], "dst_id": x["id"], "rel_type": "supports"}, 400)
    req("POST", "/api/assertions/relations",
        {"src_id": y["id"], "dst_id": x["id"], "rel_type": "derived_from"}, 409)
    req("POST", "/api/assertions/relations",
        {"src_id": y["id"], "dst_id": 999999, "rel_type": "supports"}, 404)
    req("POST", "/api/assertions/relations",
        {"src_id": z["id"], "dst_id": x["id"], "rel_type": "refutes"}, 201)

    # 派生证据闭包：y 无直接证据但经 derived_from 继承 x 的两条证据
    det = req("GET", f"/api/assertions/{y['id']}")
    assert len(det["evidence_closure"]["evidences"]) == 2
    assert [n["id"] for n in det["evidence_closure"]["chains"][0]] == [y["id"], x["id"]]

    # 循环：x supports y + y derived_from x
    req("POST", "/api/assertions/relations",
        {"src_id": x["id"], "dst_id": y["id"], "rel_type": "supports"}, 201)
    an = req("GET", f"/api/analysis?topic={t1}")
    assert [x["id"], y["id"]] in [c["node_ids"] for c in an["cycles"]]

    # 互斥冲突
    pairs = [tuple(sorted((c["endpoints"][0]["id"], c["endpoints"][1]["id"])))
             for c in an["conflicts"]]
    assert tuple(sorted((x["id"], z["id"]))) in pairs
    # 状态定级：此时两端均非 confirmed => low
    xz = next(c for c in an["conflicts"]
              if {c["endpoints"][0]["id"], c["endpoints"][1]["id"]} == {x["id"], z["id"]})
    assert xz["severity"] == "low"
    assert xz["path"]["edges"] and xz["explanation"]

    # 无来源：y 经派生链有据；w 无据
    w = req("POST", "/api/assertions", {"claim": "无据说法", "topic": t1}, 201)
    created["assertions"].append(w["id"])
    an = req("GET", f"/api/analysis?topic={t1}")
    uns = {u["assertion"]["id"] for u in an["unsourced"]}
    assert w["id"] in uns and y["id"] not in uns

    # 状态流转 + 严重度升级
    req("PATCH", f"/api/assertions/{x['id']}", {"status": "confirmed"}, 200)
    req("PATCH", f"/api/assertions/{z['id']}", {"status": "confirmed"}, 200)
    an = req("GET", f"/api/analysis?topic={t1}")
    xz = next(c for c in an["conflicts"]
              if {c["endpoints"][0]["id"], c["endpoints"][1]["id"]} == {x["id"], z["id"]})
    assert xz["severity"] == "high"

    # 非法状态
    try:
        req("PATCH", f"/api/assertions/{x['id']}", {"status": "bogus"})
        raise SystemExit("非法状态应被拒绝")
    except AssertionError:
        pass

    # 列表过滤 / 主题隔离 / 图 / 导出
    flt = req("GET", f"/api/assertions?topic={t1}&status=confirmed")
    assert {a["id"] for a in flt} == {x["id"], z["id"]}
    other = req("POST", "/api/assertions", {"claim": "另一主题", "topic": t2}, 201)
    created["assertions"].append(other["id"])
    an2 = req("GET", f"/api/analysis?topic={t2}")
    assert an2["summary"]["conflicts"] == 0 and an2["summary"]["cycles"] == 0
    g = req("GET", f"/api/graph?topic={t1}")
    assert {n["id"] for n in g["nodes"]} >= {x["id"], y["id"], z["id"]}
    md = urllib.request.urlopen(BASE + f"/api/export/markdown?topic={urllib.parse.quote(t1)}").read().decode()
    for marker in (t1, "互斥结论", "循环引用", "无来源断言", "证据链", PREFIX + " 监测报告", "举报人"):
        assert marker in md, f"导出缺少：{marker}"

    # 级联删除
    rel_before = len(req("GET", f"/api/assertions/{x['id']}")["incoming_relations"])
    req("DELETE", f"/api/assertions/{z['id']}", expect=204)
    assert len(req("GET", f"/api/assertions/{x['id']}")["incoming_relations"]) == rel_before - 1

    # 前端
    assert "采访事实核查工作台" in urllib.request.urlopen(BASE + "/").read().decode()

    cleanup()
    print("ALL API E2E TESTS PASSED  (topic prefix:", PREFIX + ")")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        cleanup()
        raise
