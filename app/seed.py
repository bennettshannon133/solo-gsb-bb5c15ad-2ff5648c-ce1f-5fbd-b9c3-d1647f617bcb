"""首次启动时写入演示数据（可用 SEED_SAMPLE=0 关闭）。"""
from __future__ import annotations

import os

from .database import db


def seed_if_empty() -> None:
    if os.getenv("SEED_SAMPLE", "1") not in ("1", "true", "TRUE"):
        return
    with db() as conn:
        if conn.execute("SELECT COUNT(*) AS n FROM assertions").fetchone()["n"]:
            return
        _seed(conn)


def _seed(conn) -> None:
    a = conn.execute(
        "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
        (
            "事故桥梁在坍塌前刚完成了一次结构性大修",
            "桥梁坍塌事故",
            "confirmed",
            "来自施工方内部通报，需与监理记录交叉验证。",
        ),
    ).lastrowid
    b = conn.execute(
        "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
        (
            "例行检修中发现过桥梁主体承重结构存在损伤",
            "桥梁坍塌事故",
            "confirmed",
            "知情人提供了检修记录照片。",
        ),
    ).lastrowid
    c = conn.execute(
        "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
        (
            "坍塌由桥梁老化年久失修直接导致",
            "桥梁坍塌事故",
            "pending",
            "与“刚完成大修”说法存在张力。",
        ),
    ).lastrowid
    d = conn.execute(
        "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
        (
            "施工方在大修中未按设计要求更换关键承重构件",
            "桥梁坍塌事故",
            "doubtful",
            "单一信源，待官方鉴定。",
        ),
    ).lastrowid
    e = conn.execute(
        "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
        (
            "涉事企业拿到了数亿元政府专项补贴",
            "招商补贴争议",
            "confirmed",
            "",
        ),
    ).lastrowid
    f = conn.execute(
        "INSERT INTO assertions (claim, topic, status, note) VALUES (?,?,?,?)",
        (
            "涉事企业符合该专项补贴的全部申领门槛",
            "招商补贴争议",
            "pending",
            "记者尚未取得完整申报材料。",
        ),
    ).lastrowid

    s1 = conn.execute(
        "INSERT INTO sources (title, publisher, doc_date, url, content) VALUES (?,?,?,?,?)",
        (
            "市交通委关于桥梁大修完工的情况通报",
            "市交通委员会",
            "2026-08-12",
            "https://example.gov/tongbao",
            "通报称该桥结构性大修已于7月底完工并通过验收。",
        ),
    ).lastrowid
    s2 = conn.execute(
        "INSERT INTO sources (title, publisher, doc_date, url, content) VALUES (?,?,?,?,?)",
        (
            "桥梁定期检修记录（2026年春季）",
            "市政设施管护中心",
            "2026-04-20",
            "",
            "记录显示主梁存在局部损伤，建议在后续大修中处理。",
        ),
    ).lastrowid
    s3 = conn.execute(
        "INSERT INTO sources (title, publisher, doc_date, url, content) VALUES (?,?,?,?,?)",
        (
            "财政专项资金拨付公示表",
            "市财政局",
            "2025-11-30",
            "https://example.gov/butie",
            "涉事企业获得产业引导专项资金 3.2 亿元。",
        ),
    ).lastrowid

    t1 = conn.execute(
        "INSERT INTO transcripts (speaker, interviewed, recorded_at, snippet) VALUES (?,?,?,?)",
        (
            "张某（原检修班组工人）",
            "记者李某",
            "2026-09-10",
            "我们春天检查的时候就看到主梁有裂缝，拍了照上报，后来修没修就不知道了。",
        ),
    ).lastrowid
    t2 = conn.execute(
        "INSERT INTO transcripts (speaker, interviewed, recorded_at, snippet) VALUES (?,?,?,?)",
        (
            "王某（施工方项目经理）",
            "记者李某",
            "2026-09-12",
            "大修是按期做完的，流程都走完了，具体更换了哪些构件我不方便说。",
        ),
    ).lastrowid

    # 证据挂载
    for assertion_id, kind, ref_id, quote in [
        (a, "source", s1, "结构性大修已于7月底完工并通过验收"),
        (a, "transcript", t2, "大修是按期做完的，流程都走完了"),
        (b, "source", s2, "主梁存在局部损伤，建议在后续大修中处理"),
        (b, "transcript", t1, "春天检查的时候就看到主梁有裂缝"),
        (e, "source", s3, "获得产业引导专项资金 3.2 亿元"),
    ]:
        conn.execute(
            "INSERT INTO evidences (assertion_id, kind, ref_id, quote) VALUES (?,?,?,?)",
            (assertion_id, kind, ref_id, quote),
        )

    # 断言关系
    for src, dst, rel, rationale in [
        # 循环引用：a→d 支持、d→a 支持，构成 2 节点循环论证
        (a, d, "supports", "大修完工却未换构件，与施工质量问题相互印证"),
        (d, a, "supports", "若施工确有问题，则‘刚完成大修’的通报本身也需重新审视"),
        (d, c, "derived_from", "由“未按设计更换构件”推出“老化失修导致坍塌”的说法"),
        (c, a, "refutes", "若坍塌源于老化失修，则与“刚完成结构大修”相矛盾"),
        (b, d, "supports", "检修发现损伤佐证了施工方处置不到位的怀疑"),
        (e, f, "supports", "拿到补贴意味着企业被认定符合门槛（待核）"),
        (f, e, "refutes", "若门槛造假，则补贴发放的合规性结论被推翻"),
    ]:
        conn.execute(
            "INSERT INTO relations (src_id, dst_id, rel_type, rationale) VALUES (?,?,?,?)",
            (src, dst, rel, rationale),
        )
