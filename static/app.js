/* 采访事实核查工作台 —— 纯原生 JS 单页前端 */
"use strict";

const state = { view: "dashboard", topic: "", status: "" };

/* ---------------- 基础工具 ---------------- */

const $ = (sel, root = document) => root.querySelector(sel);
const main = $("#main");

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (res.status === 204) return null;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = data && (data.detail || data.message) || `请求失败 (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

let toastTimer = null;
function toast(msg, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = msg;
  $("#toastRoot").appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function run(fn) {
  Promise.resolve().then(fn).catch((e) => toast(e.message, true));
}

const STATUS_LABEL = { pending: "待核查", confirmed: "已确认", doubtful: "存疑" };
const REL_LABEL = { supports: "支持", refutes: "反驳", derived_from: "派生自" };
const SEV_LABEL = { high: "高危", medium: "需关注", low: "待观察" };

const statusBadge = (s) =>
  `<span class="badge ${s}">${STATUS_LABEL[s] || s}</span>`;
const relBadge = (r) =>
  `<span class="badge rel-${r}">${REL_LABEL[r] || r}</span>`;

function qs(topic = state.topic, extra = "") {
  const p = new URLSearchParams();
  if (topic) p.set("topic", topic);
  const base = p.toString();
  if (extra) return (base ? `?${base}&${extra}` : `?${extra}`);
  return base ? `?${base}` : "";
}

/* ---------------- 模态框 ---------------- */

function openModal(title, bodyHtml, footerHtml = "") {
  const root = $("#modalRoot");
  root.innerHTML = `
    <div class="modal-mask">
      <div class="modal" role="dialog">
        <div class="modal-head"><h2>${title}</h2><button class="modal-x" data-close>✕</button></div>
        <div class="modal-body">${bodyHtml}</div>
        ${footerHtml ? `<div class="modal-foot">${footerHtml}</div>` : ""}
      </div>
    </div>`;
  const mask = $(".modal-mask", root);
  mask.addEventListener("click", (e) => {
    if (e.target === mask || e.target.hasAttribute("data-close")) closeModal();
  });
  return $(".modal", root);
}
function closeModal() { $("#modalRoot").innerHTML = ""; }

function formValues(modal) {
  const out = {};
  modal.querySelectorAll("[name]").forEach((el) => { out[el.name] = el.value; });
  return out;
}

/* ---------------- 主题下拉 ---------------- */

async function refreshTopics(keepValue = true) {
  const topics = await api("/api/assertions/topics");
  const sel = $("#globalTopic");
  const cur = keepValue ? sel.value : "";
  sel.innerHTML =
    `<option value="">全部主题</option>` +
    topics.map((t) => `<option value="${esc(t.topic)}">${esc(t.topic)}（${t.count}）</option>`).join("");
  sel.value = topics.some((t) => t.topic === cur) ? cur : "";
  state.topic = sel.value;
}

$("#globalTopic").addEventListener("change", (e) => {
  state.topic = e.target.value;
  render();
});

/* ---------------- 路由 ---------------- */

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.view = btn.dataset.view;
    render();
  });
});

function render() {
  run(async () => {
    await refreshTopics();
    $("#exportLink").href = "/api/export/markdown" + qs();
    ({
      dashboard: renderDashboard,
      assertions: renderAssertions,
      sources: renderSources,
      transcripts: renderTranscripts,
      graph: renderGraph,
      export: renderExport,
    })[state.view]();
  });
}

/* ---------------- 路径渲染 ---------------- */

function pathChain(path) {
  const nodes = path.nodes, edges = path.edges;
  let html = `<span class="badge pending" style="background:#1e293b;color:#e2e8f0">#${nodes[0].id}</span>`;
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i];
    html += ` <span class="badge rel-${e.rel_type}">—${REL_LABEL[e.rel_type]}→</span> ` +
      `<span class="badge pending" style="background:#1e293b;color:#e2e8f0">#${nodes[i + 1].id}</span>`;
  }
  return `<div class="path-chain">${html}</div>`;
}

function nodeClaims(path) {
  return path.nodes.map((n, i) =>
    `<div style="margin:2px 0">${i + 1}. <b>#${n.id}</b> ${statusBadge(n.status)} ${esc(n.claim)}</div>`
  ).join("");
}

/* ---------------- 视图：总览 ---------------- */

async function renderDashboard() {
  const a = await api("/api/analysis" + qs());
  const s = a.summary;
  main.innerHTML = `
    <div class="stat-grid">
      <div class="stat"><div class="num">${s.assertions}</div><div class="lbl">事实断言</div></div>
      <div class="stat"><div class="num" style="color:var(--ok)">${s.by_status.confirmed}</div><div class="lbl">已确认</div></div>
      <div class="stat"><div class="num" style="color:var(--warn)">${s.by_status.pending}</div><div class="lbl">待核查</div></div>
      <div class="stat"><div class="num" style="color:var(--doubt)">${s.by_status.doubtful}</div><div class="lbl">存疑</div></div>
      <div class="stat ${s.conflicts ? "alert" : ""}"><div class="num">${s.conflicts}</div><div class="lbl">互斥结论</div></div>
      <div class="stat ${s.cycles ? "warn" : ""}"><div class="num">${s.cycles}</div><div class="lbl">循环引用</div></div>
      <div class="stat ${s.unsourced ? "warn" : ""}"><div class="num">${s.unsourced}</div><div class="lbl">无来源断言</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h2>⚔ 同主题互斥结论与可解释冲突路径</h2></div>
      ${a.conflicts.length ? a.conflicts.map(conflictCard).join("") :
        '<div class="empty">✅ 未发现互斥结论</div>'}
    </div>

    <div class="card">
      <div class="card-title"><h2>🔁 循环引用</h2></div>
      ${a.cycles.length ? a.cycles.map(cycleCard).join("") :
        '<div class="empty">✅ 证据图中没有循环论证</div>'}
    </div>

    <div class="card">
      <div class="card-title"><h2>📭 无来源断言</h2></div>
      ${a.unsourced.length ? a.unsourced.map(unsourcedCard).join("") :
        '<div class="empty">✅ 所有断言均可追溯到证据</div>'}
    </div>`;
}

function conflictCard(c) {
  const [x, y] = c.endpoints;
  return `<div style="margin-bottom:18px">
    <h3><span class="badge sev-${c.severity}">${SEV_LABEL[c.severity]}</span>
      主题「${esc(c.topic)}」：<a href="#" data-a="${x.id}" class="open-a">#${x.id}</a> ⚔ <a href="#" data-a="${y.id}" class="open-a">#${y.id}</a>
      ${c.alt_path_count ? `<span class="muted" style="font-weight:400">（另有 ${c.alt_path_count} 条路径）</span>` : ""}
    </h3>
    <div style="margin:4px 0">${esc(x.claim)} ${statusBadge(x.status)}</div>
    <div style="margin:4px 0">${esc(y.claim)} ${statusBadge(y.status)}</div>
    ${pathChain(c.path)}
    <div class="muted" style="font-size:12.5px">路径上的断言：</div>
    ${nodeClaims(c.path)}
    <div class="explain" style="margin-top:8px">${esc(c.explanation)}</div>
  </div>`;
}

function cycleCard(cy) {
  return `<div style="margin-bottom:16px">
    <h3>环：${cy.node_ids.map((id) => `<a href="#" data-a="${id}" class="open-a">#${id}</a>`).join(" → ")} → #${cy.node_ids[0]}</h3>
    ${pathChain(cy)}
    <div class="explain">${esc(cy.explanation)}</div>
  </div>`;
}

function unsourcedCard(u) {
  const n = u.assertion;
  return `<div style="margin-bottom:8px">
    <a href="#" data-a="${n.id}" class="open-a">#${n.id}</a> ${statusBadge(n.status)}
    <span class="muted">[${esc(n.topic)}]</span> ${esc(n.claim)}
  </div>`;
}

document.addEventListener("click", (e) => {
  const link = e.target.closest(".open-a");
  if (link) {
    e.preventDefault();
    run(() => openAssertion(Number(link.dataset.a)));
  }
});

/* ---------------- 视图：断言列表 ---------------- */

async function renderAssertions() {
  const [list, an] = await Promise.all([
    api(`/api/assertions${qs(state.topic, state.status ? `status=${state.status}` : "")}`),
    api("/api/analysis" + qs()),
  ]);
  const unsourcedIds = new Set(an.unsourced.map((u) => u.assertion.id));
  main.innerHTML = `
    <div class="filters-bar">
      <h2 style="margin:0">📌 事实断言（${list.length}）</h2>
      <select id="statusFilter">
        <option value="">全部状态</option>
        <option value="pending">待核查</option>
        <option value="confirmed">已确认</option>
        <option value="doubtful">存疑</option>
      </select>
      <button class="btn" id="newAssertion">＋ 新建断言</button>
    </div>
    <div class="card" style="padding:0;overflow:hidden">
      <table>
        <thead><tr><th style="width:48px">#</th><th>断言</th><th style="width:140px">主题</th>
        <th style="width:90px">状态</th><th style="width:110px">核查性</th><th style="width:190px"></th></tr></thead>
        <tbody>
        ${list.length ? list.map((a) => `<tr>
          <td>${a.id}</td>
          <td class="clamp">${esc(a.claim)}
            ${a.note ? `<div class="muted" style="font-size:12px">${esc(a.note)}</div>` : ""}
          </td>
          <td>${esc(a.topic)}</td>
          <td>${statusBadge(a.status)}</td>
          <td>${unsourcedIds.has(a.id) ? '<span class="badge sev-medium">无来源</span>' : '<span class="muted">有据可查</span>'}</td>
          <td><div class="row-actions">
            <button class="btn small ghost" data-detail="${a.id}">详情/证据</button>
            <button class="btn small subtle" data-edit="${a.id}">编辑</button>
            <button class="btn small danger" data-del="${a.id}">删除</button>
          </div></td>
        </tr>`).join("") :
        '<tr><td colspan="6"><div class="empty">还没有断言，点击「新建断言」开始</div></td></tr>'}
        </tbody>
      </table>
    </div>`;
  $("#statusFilter").value = state.status;
  $("#statusFilter").addEventListener("change", (e) => { state.status = e.target.value; renderAssertions(); });
  $("#newAssertion").addEventListener("click", assertionForm);
  main.querySelectorAll("[data-detail]").forEach((b) =>
    b.addEventListener("click", () => run(() => openAssertion(Number(b.dataset.detail)))));
  main.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => run(() => assertionForm(Number(b.dataset.edit)))));
  main.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => run(() => deleteAssertion(Number(b.dataset.del)))));
}

async function deleteAssertion(id) {
  if (!confirm(`确认删除断言 #${id}？其证据挂载与关系会一并移除。`)) return;
  await api(`/api/assertions/${id}`, { method: "DELETE" });
  toast(`已删除断言 #${id}`);
  render();
}

async function assertionForm(id) {
  const topics = await api("/api/assertions/topics");
  const a = id ? await api(`/api/assertions/${id}`).then((d) => d.assertion) : null;
  const modal = openModal(
    a ? `编辑断言 #${a.id}` : "新建事实断言",
    `<label class="field"><span>断言内容（一句话事实主张）</span>
       <textarea name="claim" required>${esc(a?.claim || "")}</textarea></label>
     <div class="form-grid">
       <label class="field"><span>主题</span>
         <input name="topic" list="topicList" required value="${esc(a?.topic || state.topic || "")}">
         <datalist id="topicList">${topics.map((t) => `<option value="${esc(t.topic)}">`).join("")}</datalist>
       </label>
       <label class="field"><span>核查状态</span>
         <select name="status">
           ${["pending", "confirmed", "doubtful"].map((s) =>
             `<option value="${s}" ${a?.status === s ? "selected" : ""}>${STATUS_LABEL[s]}</option>`).join("")}
         </select>
       </label>
     </div>
     <label class="field"><span>编辑备注</span><textarea name="note">${esc(a?.note || "")}</textarea></label>`,
    `<button class="btn subtle" data-close>取消</button>
     <button class="btn" id="saveAssertion">${a ? "保存" : "创建"}</button>`
  );
  $("#saveAssertion", modal).addEventListener("click", () => run(async () => {
    const v = formValues(modal);
    if (!v.claim.trim() || !v.topic.trim()) return toast("断言内容和主题不能为空", true);
    const body = { claim: v.claim, topic: v.topic, status: v.status, note: v.note };
    if (a) {
      await api(`/api/assertions/${a.id}`, { method: "PATCH", body: JSON.stringify(body) });
      toast("已保存");
    } else {
      await api("/api/assertions", { method: "POST", body: JSON.stringify(body) });
      toast("已创建断言");
    }
    closeModal();
    render();
  }));
}

/* ---------------- 断言详情：证据与关系 ---------------- */

async function openAssertion(id) {
  const [d, sources, transcripts, assertions] = await Promise.all([
    api(`/api/assertions/${id}`),
    api("/api/sources"),
    api("/api/transcripts"),
    api("/api/assertions"),
  ]);
  const a = d.assertion;
  const modal = openModal(
    `断言 #${a.id}`,
    `<div>${statusBadge(a.status)} <span class="muted">主题：${esc(a.topic)}</span></div>
     <div style="font-size:15px;margin:8px 0">${esc(a.claim)}</div>
     ${a.note ? `<div class="muted">备注：${esc(a.note)}</div>` : ""}
     <div class="filters-bar" style="margin-top:10px">
       <label>状态流转
         <select id="statusSel">
           ${["pending", "confirmed", "doubtful"].map((s) =>
             `<option value="${s}" ${a.status === s ? "selected" : ""}>${STATUS_LABEL[s]}</option>`).join("")}
         </select>
       </label>
       <button class="btn small subtle" id="editBtn">编辑内容</button>
       <button class="btn small danger" id="delBtn">删除断言</button>
     </div>

     <div class="detail-section">
       <h3>🔗 证据挂载（${d.evidence.length}）</h3>
       ${d.evidence.length ? d.evidence.map(evItem).join("") : '<div class="muted">暂无直接证据</div>'}
       <div class="form-grid" style="margin-top:10px">
         <label class="field"><span>证据类型</span>
           <select id="evKind">
             <option value="source">📄 来源文档</option>
             <option value="transcript">🎙 逐字稿片段</option>
           </select></label>
         <label class="field"><span>选择条目</span><select id="evRef"></select></label>
         <label class="field full"><span>引文/定位（可选）</span><input id="evQuote" placeholder="如：第三段第二行 / 关键原句"></label>
       </div>
       <button class="btn small" id="addEv">＋ 挂载证据</button>
     </div>

     <div class="detail-section">
       <h3>🔁 派生证据链（沿“派生自”向上追溯）</h3>
       ${d.evidence_closure.evidences.length
         ? `<div class="muted">可追溯证据 ${d.evidence_closure.evidences.length} 条` +
           (d.evidence_closure.chains.length
             ? "；链：" + d.evidence_closure.chains
               .map((c) => c.map((n) => `#${n.id}`).join(" → ")).join("；")
             : "（直接挂载）") + "</div>"
         : '<div class="explain" style="border-color:var(--warn)">⚠ 本断言及其派生链上游没有任何来源证据</div>'}
     </div>

     <div class="detail-section">
       <h3>➡ 出边关系（${d.outgoing_relations.length}）</h3>
       ${relTable(d.outgoing_relations, true)}
       <h3 style="margin-top:12px">⬅ 入边关系（${d.incoming_relations.length}）</h3>
       ${relTable(d.incoming_relations, false)}
       <div class="form-grid" style="margin-top:10px">
         <label class="field"><span>关系类型</span>
           <select id="relType">
             <option value="supports">支持</option>
             <option value="refutes">反驳</option>
             <option value="derived_from">派生自</option>
           </select></label>
         <label class="field"><span>目标断言</span><select id="relTarget">
           ${assertions.filter((x) => x.id !== id)
             .map((x) => `<option value="${x.id}">#${x.id} ${esc(x.claim.slice(0, 40))}</option>`).join("")}
         </select></label>
         <label class="field full"><span>关系说明（可选）</span><input id="relRationale"></label>
       </div>
       <button class="btn small" id="addRel">＋ 添加关系</button>
     </div>`,
    `<button class="btn subtle" data-close>关闭</button>`
  );

  function fillRefs() {
    const kind = $("#evKind", modal).value;
    const items = kind === "source" ? sources : transcripts;
    $("#evRef", modal).innerHTML = items.length
      ? items.map((x) => `<option value="${x.id}">${esc(kind === "source" ? x.title : x.speaker + "：" + x.snippet.slice(0, 30))}</option>`).join("")
      : `<option value="">（请先在对应模块创建）</option>`;
  }
  $("#evKind", modal).addEventListener("change", fillRefs);
  fillRefs();

  $("#addEv", modal).addEventListener("click", () => run(async () => {
    const refId = Number($("#evRef", modal).value);
    if (!refId) return toast("请先创建来源或逐字稿", true);
    await api(`/api/assertions/${id}/evidence`, {
      method: "POST",
      body: JSON.stringify({ kind: $("#evKind", modal).value, ref_id: refId, quote: $("#evQuote", modal).value }),
    });
    toast("证据已挂载");
    closeModal();
    run(() => openAssertion(id));
    render();
  }));

  modal.querySelectorAll("[data-rmev]").forEach((b) =>
    b.addEventListener("click", () => run(async () => {
      await api(`/api/assertions/${id}/evidence/${b.dataset.rmev}`, { method: "DELETE" });
      closeModal();
      run(() => openAssertion(id));
      render();
    })));

  $("#addRel", modal).addEventListener("click", () => run(async () => {
    try {
      await api("/api/assertions/relations", {
        method: "POST",
        body: JSON.stringify({
          src_id: id,
          dst_id: Number($("#relTarget", modal).value),
          rel_type: $("#relType", modal).value,
          rationale: $("#relRationale", modal).value,
        }),
      });
      toast("关系已添加");
      closeModal();
      run(() => openAssertion(id));
      render();
    } catch (e) { toast(e.message, true); }
  }));

  modal.querySelectorAll("[data-rmrel]").forEach((b) =>
    b.addEventListener("click", () => run(async () => {
      await api(`/api/assertions/relations/${b.dataset.rmrel}`, { method: "DELETE" });
      closeModal();
      run(() => openAssertion(id));
      render();
    })));

  $("#statusSel", modal).addEventListener("change", (e) => run(async () => {
    await api(`/api/assertions/${id}`, { method: "PATCH", body: JSON.stringify({ status: e.target.value }) });
    toast("状态已更新");
    closeModal();
    render();
  }));
  $("#editBtn", modal).addEventListener("click", () => { closeModal(); run(() => assertionForm(id)); });
  $("#delBtn", modal).addEventListener("click", () => run(async () => {
    closeModal();
    await deleteAssertion(id);
  }));
}

function evItem(ev) {
  const ref = ev.ref;
  if (!ref) return "";
  const head = ev.kind === "source"
    ? `📄 <b>${esc(ref.title)}</b> <span class="muted">${esc([ref.publisher, ref.doc_date].filter(Boolean).join(" / "))}</span>`
    : `🎙 <b>${esc(ref.speaker)}</b> <span class="muted">${esc([ref.interviewed, ref.recorded_at].filter(Boolean).join(" / "))}</span>`;
  const body = ev.kind === "source"
    ? esc((ref.content || "").slice(0, 160))
    : esc((ref.snippet || "").slice(0, 160));
  return `<div class="ev-item">
    <div style="display:flex;justify-content:space-between;gap:8px">
      <span>${head}</span>
      <button class="btn small subtle" data-rmev="${ev.id}">移除</button>
    </div>
    <div class="muted" style="font-size:12.5px;margin-top:3px">${body}</div>
    ${ev.quote ? `<p class="ev-quote">“${esc(ev.quote)}”</p>` : ""}
  </div>`;
}

function relTable(rels, outgoing) {
  if (!rels.length) return '<div class="muted">无</div>';
  return `<table><tbody>${rels.map((r) => `<tr>
    <td>${relBadge(r.rel_type)}</td>
    <td>${outgoing ? "→ #" + r.dst_id : "#" + r.src_id + " → 本断言"}</td>
    <td class="clamp muted" style="font-size:12.5px">${esc(r.rationale || "")}</td>
    <td><button class="btn small subtle" data-rmrel="${r.id}">删除</button></td>
  </tr>`).join("")}</tbody></table>`;
}

/* ---------------- 视图：来源文档 ---------------- */

async function renderSources() {
  const list = await api("/api/sources");
  main.innerHTML = `
    <div class="filters-bar"><h2 style="margin:0">📄 来源文档（${list.length}）</h2>
      <button class="btn" id="newSource">＋ 新建来源</button></div>
    <div class="card" style="padding:0;overflow:hidden"><table>
      <thead><tr><th style="width:48px">#</th><th>标题</th><th style="width:150px">发布方</th>
      <th style="width:110px">日期</th><th style="width:180px"></th></tr></thead>
      <tbody>${list.length ? list.map((s) => `<tr>
        <td>${s.id}</td>
        <td class="clamp"><b>${esc(s.title)}</b>
          ${s.url ? `<div class="muted" style="font-size:12px">${esc(s.url)}</div>` : ""}
          ${s.content ? `<div class="muted" style="font-size:12px">${esc(s.content.slice(0, 100))}…</div>` : ""}
        </td>
        <td>${esc(s.publisher)}</td><td>${esc(s.doc_date)}</td>
        <td><div class="row-actions">
          <button class="btn small ghost" data-edit="${s.id}">编辑</button>
          <button class="btn small danger" data-del="${s.id}">删除</button>
        </div></td></tr>`).join("") :
        '<tr><td colspan="5"><div class="empty">暂无来源文档</div></td></tr>'}
      </tbody></table></div>`;
  $("#newSource").addEventListener("click", () => sourceForm());
  main.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => run(() => sourceForm(Number(b.dataset.edit)))));
  main.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => run(async () => {
      if (!confirm("删除来源将同时移除它在各断言上的证据挂载，确认？")) return;
      await api(`/api/sources/${b.dataset.del}`, { method: "DELETE" });
      toast("已删除");
      render();
    })));
}

async function sourceForm(id) {
  const s = id ? await api(`/api/sources/${id}`) : null;
  const modal = openModal(s ? `编辑来源 #${s.id}` : "新建来源文档", `
    <label class="field"><span>标题</span><input name="title" required value="${esc(s?.title || "")}"></label>
    <div class="form-grid">
      <label class="field"><span>发布方</span><input name="publisher" value="${esc(s?.publisher || "")}"></label>
      <label class="field"><span>文档日期</span><input name="doc_date" type="date" value="${esc(s?.doc_date || "")}"></label>
    </div>
    <label class="field"><span>链接 URL</span><input name="url" value="${esc(s?.url || "")}"></label>
    <label class="field"><span>摘要 / 关键内容</span><textarea name="content">${esc(s?.content || "")}</textarea></label>`,
    `<button class="btn subtle" data-close>取消</button><button class="btn" id="save">${s ? "保存" : "创建"}</button>`);
  $("#save", modal).addEventListener("click", () => run(async () => {
    const v = formValues(modal);
    if (!v.title.trim()) return toast("标题不能为空", true);
    await api(s ? `/api/sources/${s.id}` : "/api/sources", {
      method: s ? "PATCH" : "POST",
      body: JSON.stringify(v),
    });
    closeModal();
    toast(s ? "已保存" : "已创建");
    render();
  }));
}

/* ---------------- 视图：逐字稿 ---------------- */

async function renderTranscripts() {
  const list = await api("/api/transcripts");
  main.innerHTML = `
    <div class="filters-bar"><h2 style="margin:0">🎙 逐字稿片段（${list.length}）</h2>
      <button class="btn" id="newTr">＋ 新建片段</button></div>
    ${list.length ? list.map((t) => `<div class="card">
      <div style="display:flex;justify-content:space-between;gap:10px">
        <div><b>#${t.id} ${esc(t.speaker)}</b>
          <span class="muted">采访人：${esc(t.interviewed || "—")}　时间：${esc(t.recorded_at || "—")}</span></div>
        <div class="row-actions">
          <button class="btn small ghost" data-edit="${t.id}">编辑</button>
          <button class="btn small danger" data-del="${t.id}">删除</button>
        </div>
      </div>
      <p style="margin:8px 0 0">${esc(t.snippet)}</p>
    </div>`).join("") : '<div class="card"><div class="empty">暂无逐字稿片段</div></div>'}`;
  $("#newTr").addEventListener("click", () => transcriptForm());
  main.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => run(() => transcriptForm(Number(b.dataset.edit)))));
  main.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => run(async () => {
      if (!confirm("删除片段将同时移除相关证据挂载，确认？")) return;
      await api(`/api/transcripts/${b.dataset.del}`, { method: "DELETE" });
      toast("已删除");
      render();
    })));
}

async function transcriptForm(id) {
  const t = id ? await api(`/api/transcripts/${id}`) : null;
  const modal = openModal(t ? `编辑片段 #${t.id}` : "新建逐字稿片段", `
    <div class="form-grid">
      <label class="field"><span>说话人</span><input name="speaker" required value="${esc(t?.speaker || "")}"></label>
      <label class="field"><span>采访人</span><input name="interviewed" value="${esc(t?.interviewed || "")}"></label>
      <label class="field full"><span>录制时间</span><input name="recorded_at" type="date" value="${esc(t?.recorded_at || "")}"></label>
    </div>
    <label class="field"><span>逐字稿原文</span><textarea name="snippet" style="min-height:120px" required>${esc(t?.snippet || "")}</textarea></label>`,
    `<button class="btn subtle" data-close>取消</button><button class="btn" id="save">${t ? "保存" : "创建"}</button>`);
  $("#save", modal).addEventListener("click", () => run(async () => {
    const v = formValues(modal);
    if (!v.speaker.trim() || !v.snippet.trim()) return toast("说话人和原文不能为空", true);
    await api(t ? `/api/transcripts/${t.id}` : "/api/transcripts", {
      method: t ? "PATCH" : "POST",
      body: JSON.stringify(v),
    });
    closeModal();
    toast(t ? "已保存" : "已创建");
    render();
  }));
}

/* ---------------- 视图：证据图（简易力导向） ---------------- */

const EDGE_COLOR = { supports: "#059669", refutes: "#dc2626", derived_from: "#2563eb" };
const NODE_COLOR = { pending: "#d97706", confirmed: "#059669", doubtful: "#7c3aed" };

async function renderGraph() {
  main.innerHTML = `
    <div class="filters-bar"><h2 style="margin:0">🕸 有向证据图</h2>
      <button class="btn subtle" id="reheat">重新布局</button>
      <span class="muted">拖动节点可调整位置，点击节点查看详情</span></div>
    <div class="graph-legend">
      <span><i class="legend-dot" style="background:#059669"></i>已确认</span>
      <span><i class="legend-dot" style="background:#d97706"></i>待核查</span>
      <span><i class="legend-dot" style="background:#7c3aed"></i>存疑</span>
      <span>边：<b style="color:#059669">支持</b> / <b style="color:#dc2626">反驳</b> / <b style="color:#2563eb">派生自</b></span>
    </div>
    <div class="graph-wrap"><svg id="graphSvg"></svg></div>`;

  const data = await api("/api/graph" + qs());
  if (!data.nodes.length) {
    $("#graphSvg").outerHTML = '<div class="card"><div class="empty">当前筛选下没有断言</div></div>';
    return;
  }

  const svg = $("#graphSvg");
  const W = svg.clientWidth || 1100, H = 620;
  const nodes = data.nodes.map((n, i) => ({
    ...n,
    x: W / 2 + Math.cos((i / data.nodes.length) * Math.PI * 2) * 220 + (Math.random() - .5) * 30,
    y: H / 2 + Math.sin((i / data.nodes.length) * Math.PI * 2) * 220 + (Math.random() - .5) * 30,
    vx: 0, vy: 0,
  }));
  const pos = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = data.edges.map((e) => ({ ...e, s: pos[e.source], t: pos[e.target] })).filter((e) => e.s && e.t);

  function simulate() {
    for (let tick = 0; tick < 320; tick++) {
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.vx += (W / 2 - a.x) * 0.0025;
        a.vy += (H / 2 - a.y) * 0.0025;
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 0.01) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = .01; }
          const f = 5200 / d2;
          const d = Math.sqrt(d2);
          a.vx += (dx / d) * f; a.vy += (dy / d) * f;
          b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
        }
      }
      const target = 180;
      for (const e of edges) {
        const dx = e.t.x - e.s.x, dy = e.t.y - e.s.y;
        const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
        const f = (d - target) * 0.02;
        e.s.vx += (dx / d) * f; e.s.vy += (dy / d) * f;
        e.t.vx -= (dx / d) * f; e.t.vy -= (dy / d) * f;
      }
      for (const n of nodes) {
        n.vx *= 0.85; n.vy *= 0.85;
        n.x = Math.max(30, Math.min(W - 30, n.x + n.vx));
        n.y = Math.max(30, Math.min(H - 30, n.y + n.vy));
      }
    }
    draw();
  }

  function draw() {
    const defs = Object.keys(EDGE_COLOR).map((k) =>
      `<marker id="arr-${k}" markerWidth="9" markerHeight="9" refX="18" refY="4" orient="auto">
         <path d="M0,0 L9,4 L0,8 Z" fill="${EDGE_COLOR[k]}"/></marker>`).join("");
    const edgeSvg = edges.map((e) => {
      const mx = (e.s.x + e.t.x) / 2, my = (e.s.y + e.t.y) / 2;
      return `<g>
        <line x1="${e.s.x}" y1="${e.s.y}" x2="${e.t.x}" y2="${e.t.y}"
          stroke="${EDGE_COLOR[e.rel_type]}" stroke-width="2" opacity=".75"
          marker-end="url(#arr-${e.rel_type})"></line>
        <text x="${mx}" y="${my}" class="edge-label" text-anchor="middle"
          stroke="#fbfcfe" stroke-width="3" paint-order="stroke" fill="${EDGE_COLOR[e.rel_type]}">
          ${REL_LABEL[e.rel_type]}</text>
      </g>`;
    }).join("");
    const nodeSvg = nodes.map((n) => `
      <g data-node="${n.id}" style="cursor:pointer">
        <circle cx="${n.x}" cy="${n.y}" r="15" fill="${NODE_COLOR[n.status]}"
          stroke="#fff" stroke-width="2"></circle>
        <text x="${n.x}" y="${n.y + 30}" class="node-label" text-anchor="middle">#${n.id} ${esc(n.label.replace(/^#\d+\s/, "").slice(0, 18))}</text>
      </g>`).join("");
    svg.innerHTML = `<defs>${defs}</defs>${edgeSvg}${nodeSvg}`;
  }

  // 事件委托：监听器只绑定一次，重绘 innerHTML 不会泄漏
  let dragNode = null;
  let moved = false;
  let downXY = null;
  let suppressClick = false;
  svg.addEventListener("pointerdown", (ev) => {
    const g = ev.target.closest?.("[data-node]");
    if (!g) return;
    dragNode = pos[Number(g.dataset.node)];
    moved = false;
    downXY = { x: ev.clientX, y: ev.clientY };
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!dragNode) return;
    if (Math.abs(ev.clientX - downXY.x) + Math.abs(ev.clientY - downXY.y) > 4) moved = true;
    const rect = svg.getBoundingClientRect();
    dragNode.x = ev.clientX - rect.left;
    dragNode.y = ev.clientY - rect.top;
    draw();
  });
  const endDrag = () => {
    if (moved) {
      // 抑制拖拽结束时合成的 click，避免误打开详情
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 60);
    }
    dragNode = null;
  };
  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", endDrag);
  svg.addEventListener("click", (ev) => {
    const g = ev.target.closest?.("[data-node]");
    if (!g || suppressClick) return;
    run(() => openAssertion(Number(g.dataset.node)));
  });

  $("#reheat").addEventListener("click", simulate);
  simulate();
}

/* ---------------- 视图：导出 ---------------- */

async function renderExport() {
  const topics = await api("/api/assertions/topics");
  main.innerHTML = `
    <div class="card">
      <h2>📝 导出 Markdown 核查稿</h2>
      <p class="muted">核查稿包含：状态统计、互斥结论与冲突路径、循环引用、无来源断言、每条断言的证据链（含派生追溯）与关系清单。</p>
      <div class="filters-bar">
        <select id="expTopic">
          <option value="">全部主题</option>
          ${topics.map((t) => `<option value="${esc(t.topic)}">${esc(t.topic)}</option>`).join("")}
        </select>
        <button class="btn" id="previewBtn">预览</button>
        <a class="btn ghost" id="downloadBtn" href="/api/export/markdown" target="_blank">⬇ 下载 .md 文件</a>
      </div>
    </div>
    <pre class="preview" id="mdPreview">点击「预览」生成核查稿……</pre>`;
  const sel = $("#expTopic");
  sel.value = state.topic;
  function syncUrl() {
    const t = sel.value;
    $("#downloadBtn").href = "/api/export/markdown" + (t ? "?topic=" + encodeURIComponent(t) : "");
  }
  sel.addEventListener("change", syncUrl);
  syncUrl();
  $("#previewBtn").addEventListener("click", () => run(async () => {
    const t = sel.value;
    const res = await fetch("/api/export/markdown" + (t ? "?topic=" + encodeURIComponent(t) : ""));
    $("#mdPreview").textContent = await res.text();
  }));
}

/* ---------------- 启动 ---------------- */
render();
