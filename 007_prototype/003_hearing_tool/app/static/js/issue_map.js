/* ヒアリング管理ツールの画面：課題カードのつながりマップ
 *
 * 課題をテーマごとの囲みに入れて並べ、課題どうしのつながり（issue_links.csv）、
 * 解決策の候補（solutions.csv）、データ（data_sources.csv）との関係を線で表示する。
 * カードはドラッグで動かせ、位置は map_positions.csv に保存する（ZIP で受け渡す）。
 * ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ つながりマップ

/** カードの幅と、自動で並べるときの間隔（px） */
const MAP_CARD_W = 220;
const MAP_SMALL_W = 190;
const MAP_STEP_Y = 96;
const MAP_COL_GAP = 90;
const MAP_COLUMNS = 4;

/** テーマの囲みの余白と、見出しの高さ（px） */
const MAP_BOX_PAD = 14;
const MAP_BOX_HEAD = 26;

/** 拡大・縮小の段階 */
const MAP_ZOOMS = [0.5, 0.75, 1, 1.25];

/** 対象者ごとの色（カードの左の線に使う） */
const MAP_PERSON_COLORS = ["#2f6fdb", "#c2410c", "#15803d", "#7c3aed", "#be185d", "#0e7490"];

/** テーマが空の課題の囲みの名前 */
const NO_THEME = "（テーマなし）";

/** マップの表示の状態（画面を描き直しても保つ） */
const issueMap = { showSolutions: true, showSources: true, showDropped: false, selected: "", connectFrom: "" };

/**
 * 保存した値を読み込む（保存できない環境では既定値を返す）。
 * @param {string} key 保存の名前
 * @param {string} fallback 既定値
 * @returns {string} 値
 */
function loadPref(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

/**
 * 値を保存する（保存できなくても表示は続ける）。
 * @param {string} key 保存の名前
 * @param {string} value 値
 * @returns {void}
 */
function savePref(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 何もしない */ }
}

/**
 * 対象者の色を返す。
 * @param {string} personId 対象者のID
 * @returns {string} 色
 */
function personColor(personId) {
  const index = state.tables.persons.findIndex((p) => p.person_id === personId);
  return index < 0 ? "#9aa5b1" : MAP_PERSON_COLORS[index % MAP_PERSON_COLORS.length];
}

/**
 * マップに出すカードと線を集める。
 * @returns {{nodes: object[], edges: object[]}} カード（key、type、row、theme）と線（from、to、type、row）
 */
function collectMapGraph() {
  // 課題：一覧と同じ絞り込み（対象者、状態）に合わせる。見送りは、選んだときだけ出す
  const issues = state.tables.issues.filter((x) => (
    (!filters.issuePerson || x.person_id === filters.issuePerson) &&
    (filters.issueStatus ? x.status === filters.issueStatus : (issueMap.showDropped || x.status !== "見送り"))));
  const visible = new Set(issues.map((x) => x.issue_id));
  const nodes = issues.map((x) => ({ key: `issue:${x.issue_id}`, type: "issue", row: x, theme: x.theme || NO_THEME }));
  const edges = [];

  // 課題どうしのつながり：両方の課題が出ているものだけ
  for (const link of state.tables.issue_links || []) {
    if (visible.has(link.from_issue_id) && visible.has(link.to_issue_id)) {
      edges.push({ from: `issue:${link.from_issue_id}`, to: `issue:${link.to_issue_id}`, type: "link", row: link });
    }
  }

  // 解決策の候補：出ている課題にひも付くもの（対象者で絞っていなければ、ひも付きのないものも出す）
  if (issueMap.showSolutions) {
    for (const s of state.tables.solutions) {
      const linked = ids(s.issue_ids).filter((id) => visible.has(id));
      if (!linked.length && (filters.issuePerson || ids(s.issue_ids).length)) continue;
      nodes.push({ key: `solution:${s.solution_id}`, type: "solution", row: s });
      linked.forEach((id) => edges.push({ from: `solution:${s.solution_id}`, to: `issue:${id}`, type: "solution" }));
    }
  }

  // データ：出ている課題にひも付くもの（対象者で絞っているときは、その対象者のデータだけ）
  if (issueMap.showSources) {
    for (const d of state.tables.data_sources) {
      if (filters.issuePerson && d.person_id !== filters.issuePerson) continue;
      const linked = ids(d.issue_ids).filter((id) => visible.has(id));
      if (!linked.length && ids(d.issue_ids).length) continue;
      nodes.push({ key: `source:${d.source_id}`, type: "source", row: d });
      linked.forEach((id) => edges.push({ from: `source:${d.source_id}`, to: `issue:${id}`, type: "source" }));
    }
  }
  return { nodes, edges };
}

/**
 * カードの位置を決める。保存した位置があればそれを使い、なければ自動で置く。
 *   課題：テーマごとの列に縦に並べる（同じテーマのカードの下に足す）
 *   解決策の候補とデータ：課題の下の帯に、ひも付く課題の横の位置の順で並べる
 * @param {object[]} nodes カードの一覧（x、y を書き込む）
 * @param {object[]} edges 線の一覧
 * @returns {void}
 */
function layoutMapNodes(nodes, edges) {
  // 保存した位置を入れる
  const saved = Object.fromEntries((state.tables.map_positions || []).map((p) => [p.node, p]));
  for (const n of nodes) {
    const p = saved[n.key];
    if (p && p.x !== "" && p.y !== "" && !isNaN(Number(p.x)) && !isNaN(Number(p.y))) {
      n.x = Number(p.x); n.y = Number(p.y); n.saved = true;
    }
  }
  const placedBottom = () => Math.max(0, ...nodes.filter((n) => n.x !== undefined).map((n) => n.y + MAP_STEP_Y));

  // 課題：テーマごとにまとめる
  const themes = [...new Set(nodes.filter((n) => n.type === "issue").map((n) => n.theme))]
    .sort((a, b) => (a === NO_THEME) - (b === NO_THEME) || a.localeCompare(b, "ja"));
  let slot = 0;
  let rowTop = placedBottom() ? placedBottom() + 40 : 40;
  let rowHeight = 0;
  for (const theme of themes) {
    const members = nodes.filter((n) => n.type === "issue" && n.theme === theme);
    const placed = members.filter((n) => n.x !== undefined);
    const rest = members.filter((n) => n.x === undefined);
    if (!rest.length) continue;

    if (placed.length) {
      // すでに置いたカードがあるテーマ：そのカードの下に足す
      const x = Math.min(...placed.map((n) => n.x));
      let y = Math.max(...placed.map((n) => n.y)) + MAP_STEP_Y;
      rest.forEach((n) => { n.x = x; n.y = y; y += MAP_STEP_Y; });
    } else {
      // まだ置いていないテーマ：新しい列に置く（MAP_COLUMNS 列ごとに折り返す）
      if (slot > 0 && slot % MAP_COLUMNS === 0) { rowTop += rowHeight + 60; rowHeight = 0; }
      const x = 40 + (slot % MAP_COLUMNS) * (MAP_CARD_W + MAP_COL_GAP);
      rest.forEach((n, i) => { n.x = x; n.y = rowTop + MAP_BOX_HEAD + i * MAP_STEP_Y; });
      rowHeight = Math.max(rowHeight, MAP_BOX_HEAD + rest.length * MAP_STEP_Y);
      slot++;
    }
  }

  // 解決策の候補、データ：ひも付く課題の横の位置の平均の順に、下の帯へ並べる
  for (const type of ["solution", "source"]) {
    const rest = nodes.filter((n) => n.type === type && n.x === undefined);
    if (!rest.length) continue;
    const byKey = Object.fromEntries(nodes.map((n) => [n.key, n]));
    const avgX = (n) => {
      const xs = edges.filter((e) => e.from === n.key).map((e) => byKey[e.to]?.x).filter((v) => v !== undefined);
      return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 99999;
    };
    rest.sort((a, b) => avgX(a) - avgX(b));
    const top = placedBottom() + 50;
    rest.forEach((n, i) => {
      n.x = 40 + (i % 6) * (MAP_SMALL_W + 30);
      n.y = top + Math.floor(i / 6) * 70;
    });
  }
}

/**
 * カードの HTML を作る。
 * @param {object} n カード
 * @returns {string} HTML
 */
function mapCardHtml(n) {
  const r = n.row;
  if (n.type === "issue") {
    const person = (find("persons", r.person_id) || {}).name || "";
    return `<div class="im-card issue" data-node="${h(n.key)}" style="left:${n.x}px;top:${n.y}px;width:${MAP_CARD_W}px;border-left-color:${personColor(r.person_id)}">
      <div class="im-card-title">${h(r.title)}</div>
      <div class="im-card-meta"><span>${h(person)}</span>${badge(r.status)}</div></div>`;
  }
  if (n.type === "solution") {
    return `<div class="im-card solution" data-node="${h(n.key)}" style="left:${n.x}px;top:${n.y}px;width:${MAP_SMALL_W}px">
      <div class="im-card-kind">解決策の候補${r.uses_genai === "1" ? "（生成AI）" : ""}</div>
      <div class="im-card-title">${h(r.method)}</div></div>`;
  }
  return `<div class="im-card source" data-node="${h(n.key)}" style="left:${n.x}px;top:${n.y}px;width:${MAP_SMALL_W}px">
    <div class="im-card-kind">データ（${h(r.confirmation)}）</div>
    <div class="im-card-title">${h(r.name)}</div></div>`;
}

/**
 * 四角形の中心から外へ向かう線が、四角形の縁と交わる点を返す（矢印を縁で止めるため）。
 * @param {object} rect 四角形（x、y、w、h）
 * @param {number} tx 線の向かう先の x
 * @param {number} ty 線の向かう先の y
 * @returns {{x: number, y: number}} 縁の上の点
 */
function rectEdgePoint(rect, tx, ty) {
  const cx = rect.x + rect.w / 2;
  const cy = rect.y + rect.h / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const scale = Math.min(Math.abs((rect.w / 2) / (dx || 1e-9)), Math.abs((rect.h / 2) / (dy || 1e-9)));
  return { x: cx + dx * Math.min(scale, 1), y: cy + dy * Math.min(scale, 1) };
}

/**
 * つながりマップを表示する。
 * @param {HTMLElement} box 表示先
 * @returns {void}
 */
function renderIssueMap(box) {
  const zoom = Number(loadPref("issue_map_zoom", "1"));
  const oldWrap = box.querySelector(".im-wrap");
  const oldScroll = oldWrap ? [oldWrap.scrollLeft, oldWrap.scrollTop] : null;

  // カードと線を集め、位置を決める
  const { nodes, edges } = collectMapGraph();
  layoutMapNodes(nodes, edges);
  const byKey = Object.fromEntries(nodes.map((n) => [n.key, n]));
  if (issueMap.selected && !byKey[issueMap.selected]) issueMap.selected = "";

  // 対象者の色の凡例
  const persons = state.tables.persons.map((p) => (
    `<span><i class="im-swatch" style="background:${personColor(p.person_id)}"></i>${h(p.name)}</span>`)).join("");

  box.innerHTML = `
    <div class="im-toolbar">
      <label><input type="checkbox" id="im-sol" ${issueMap.showSolutions ? "checked" : ""}> 解決策の候補</label>
      <label><input type="checkbox" id="im-src" ${issueMap.showSources ? "checked" : ""}> データ</label>
      <label><input type="checkbox" id="im-drop" ${issueMap.showDropped ? "checked" : ""} ${filters.issueStatus ? "disabled" : ""}> 見送りも表示</label>
      <span class="rm-scales">${MAP_ZOOMS.map((z) => (
        `<button type="button" class="small ${z === zoom ? "on" : ""}" data-im-zoom="${z}">${Math.round(z * 100)}%</button>`)).join("")}</span>
      <button type="button" class="small" id="im-relayout" title="カードの位置を自動で並べ直します">自動で並べ直す</button>
    </div>
    <div class="im-legend muted">
      ${persons}
      <span><i class="im-line link"></i>課題どうしのつながり（→は原因・影響の向き）</span>
      <span><i class="im-line solution"></i>解決策の候補</span>
      <span><i class="im-line source"></i>データ</span>
      <span>カードを押すと、つながっているものを強調します。ドラッグで動かせます。</span>
    </div>
    ${issueMap.connectFrom ? `<div class="notice im-connect">「${h(labelOf("issues", find("issues", issueMap.connectFrom.split(":")[1])))}」とつなぐ課題のカードを押してください。
      <button type="button" class="small" id="im-connect-cancel">やめる</button></div>` : ""}
    <div class="im-layout">
      <div class="im-wrap"><div class="im-sizer"><div class="im-canvas" style="transform:scale(${zoom})">
        <div class="im-boxes"></div>
        <svg class="im-edges" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker id="im-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#7c3aed"></path></marker>
          </defs>
          <g class="im-edge-layer"></g>
        </svg>
        ${nodes.map(mapCardHtml).join("")}
      </div></div></div>
      <aside class="im-side panel" id="im-side"></aside>
    </div>
    ${nodes.length ? "" : '<p class="muted">表示する課題がありません。絞り込みを変えるか、課題を追加してください。</p>'}`;

  const wrap = box.querySelector(".im-wrap");
  const sizer = box.querySelector(".im-sizer");
  const canvas = box.querySelector(".im-canvas");
  const edgeLayer = box.querySelector(".im-edge-layer");
  const svg = box.querySelector(".im-edges");
  const boxesEl = box.querySelector(".im-boxes");

  /**
   * カードの今の位置と大きさを、画面の要素から読み取る。
   * @param {string} key カードのキー
   * @returns {{x: number, y: number, w: number, h: number}} 四角形
   */
  const rectOf = (key) => {
    const el = canvas.querySelector(`[data-node="${CSS.escape(key)}"]`);
    return { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight };
  };

  /**
   * テーマの囲みの位置を、中の課題のカードから計算する。
   * @returns {object[]} 囲みの一覧（theme、x、y、w、h、keys）
   */
  const themeBoxes = () => {
    const groups = {};
    nodes.filter((n) => n.type === "issue").forEach((n) => { (groups[n.theme] ||= []).push(n.key); });
    return Object.entries(groups).map(([theme, keys]) => {
      const rects = keys.map(rectOf);
      const x = Math.min(...rects.map((r) => r.x)) - MAP_BOX_PAD;
      const y = Math.min(...rects.map((r) => r.y)) - MAP_BOX_PAD - MAP_BOX_HEAD;
      const right = Math.max(...rects.map((r) => r.x + r.w)) + MAP_BOX_PAD;
      const bottom = Math.max(...rects.map((r) => r.y + r.h)) + MAP_BOX_PAD;
      return { theme, x, y, w: right - x, h: bottom - y, keys };
    });
  };

  /**
   * 線とテーマの囲みを描き直し、マップの大きさを合わせる（カードを動かすたびに呼ぶ）。
   * @returns {void}
   */
  const redraw = () => {
    // テーマの囲み（見出しをドラッグすると、中のカードをまとめて動かせる）
    boxesEl.innerHTML = themeBoxes().map((b) => `
      <div class="im-box ${b.theme === NO_THEME ? "none" : ""}" style="left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px">
        <div class="im-box-head" data-theme="${h(b.theme)}" title="ドラッグすると、このテーマのカードをまとめて動かせます">${h(b.theme)}
          <span class="im-box-count">${b.keys.length}</span></div></div>`).join("");

    // 線：カードの縁から縁へ引く
    edgeLayer.innerHTML = edges.map((e, i) => {
      const a = rectOf(e.from);
      const b = rectOf(e.to);
      const p1 = rectEdgePoint(a, b.x + b.w / 2, b.y + b.h / 2);
      const p2 = rectEdgePoint(b, a.x + a.w / 2, a.y + a.h / 2);
      const directed = e.type === "link" && (e.row.kind === "原因" || e.row.kind === "影響");
      const label = e.type === "link" ? `<text class="im-edge-label" x="${(p1.x + p2.x) / 2}" y="${(p1.y + p2.y) / 2 - 4}"
        text-anchor="middle">${h(e.row.kind)}</text>` : "";
      return `<g class="im-edge ${e.type}" data-edge="${i}">
        <line class="im-edge-hit" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"></line>
        <line class="im-edge-line" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" ${directed ? 'marker-end="url(#im-arrow)"' : ""}></line>
        ${label}</g>`;
    }).join("");

    // マップの大きさ：いちばん右下のカードまで入るようにし、拡大・縮小の分だけスクロールの範囲を合わせる
    const rects = nodes.map((n) => rectOf(n.key));
    const width = Math.max(800, ...rects.map((r) => r.x + r.w)) + 120;
    const height = Math.max(400, ...rects.map((r) => r.y + r.h)) + 120;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    sizer.style.width = `${width * zoom}px`;
    sizer.style.height = `${height * zoom}px`;
    applyHighlight();
  };

  /**
   * 選んだカードと、それにつながるカードと線を強調し、ほかを薄くする。
   * @returns {void}
   */
  const applyHighlight = () => {
    const sel = issueMap.selected;
    const near = new Set(sel ? [sel] : []);
    edges.forEach((e) => { if (e.from === sel || e.to === sel) { near.add(e.from); near.add(e.to); } });
    canvas.querySelectorAll(".im-card").forEach((el) => {
      el.classList.toggle("selected", el.dataset.node === sel);
      el.classList.toggle("dim", !!sel && !near.has(el.dataset.node));
    });
    edgeLayer.querySelectorAll(".im-edge").forEach((el) => {
      const e = edges[Number(el.dataset.edge)];
      el.classList.toggle("dim", !!sel && e.from !== sel && e.to !== sel);
    });
  };

  /**
   * カードの位置を保存する。
   * @param {string[]} keys 保存するカードのキー
   * @returns {Promise<void>}
   */
  const savePositions = async (keys) => {
    const positions = keys.map((key) => { const r = rectOf(key); return { node: key, x: r.x, y: r.y }; });
    try {
      await api("POST", "/api/map/positions", { positions });
      await reload();
    } catch (e) {
      toast(e.message, true);
    }
  };

  /**
   * データを読み直した後に、スクロールの位置を保ってマップを描き直す。
   * @returns {void}
   */
  const rerender = () => renderIssueMap(box);

  // 最初の描画（カードの大きさが決まってから線を引く）
  redraw();
  if (oldScroll) { wrap.scrollLeft = oldScroll[0]; wrap.scrollTop = oldScroll[1]; }
  renderMapSide(box.querySelector("#im-side"), byKey, edges, rerender);

  // ---------------------------------------------------------------- ドラッグ
  // カードまたはテーマの見出しを押したまま動かすと移動する。ほとんど動かさずに離したら「押した」とみなす
  let drag = null;
  canvas.addEventListener("pointerdown", (event) => {
    const card = event.target.closest(".im-card");
    const head = event.target.closest(".im-box-head");
    if (!card && !head) return;
    const keys = card ? [card.dataset.node] : nodes.filter((n) => n.type === "issue" && n.theme === head.dataset.theme).map((n) => n.key);
    drag = {
      keys, card, startX: event.clientX, startY: event.clientY, moved: false,
      origin: keys.map((key) => { const r = rectOf(key); return [r.x, r.y]; }),
      boxes: themeBoxes(),
    };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = (event.clientX - drag.startX) / zoom;
    const dy = (event.clientY - drag.startY) / zoom;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    drag.keys.forEach((key, i) => {
      const el = canvas.querySelector(`[data-node="${CSS.escape(key)}"]`);
      el.style.left = `${Math.max(0, drag.origin[i][0] + dx)}px`;
      el.style.top = `${Math.max(MAP_BOX_HEAD + MAP_BOX_PAD, drag.origin[i][1] + dy)}px`;
    });
    redraw();
  });
  canvas.addEventListener("pointerup", async () => {
    if (!drag) return;
    const { keys, card, moved, boxes } = drag;
    drag = null;

    // 動かさずに離した：カードを押したときの処理
    if (!moved) { if (card) onCardClick(card.dataset.node); return; }

    // 動かした：位置を保存する。課題を別のテーマの囲みに入れたら、テーマを変えるか確かめる
    await savePositions(keys);
    if (card && card.classList.contains("issue")) {
      const node = byKey[card.dataset.node];
      const r = rectOf(node.key);
      const cx = r.x + r.w / 2;
      const cy = r.y + r.h / 2;
      const target = boxes.find((b) => b.theme !== node.theme && cx > b.x && cx < b.x + b.w && cy > b.y && cy < b.y + b.h);
      if (target && await confirmDialog(`「${node.row.title}」のテーマを「${target.theme}」に変えますか？`)) {
        try {
          await api("PUT", `/api/tables/issues/${node.row.issue_id}`, { values: { theme: target.theme === NO_THEME ? "" : target.theme } });
          await reload();
          toast("テーマを変えました。");
        } catch (e) { toast(e.message, true); }
      }
    }
    rerender();
  });

  // カードを押したとき：つなぐ相手を選んでいるならつながりを作り、そうでなければ選ぶ
  const onCardClick = async (key) => {
    if (issueMap.connectFrom) {
      if (!key.startsWith("issue:")) { toast("つなげるのは課題のカードだけです。", true); return; }
      if (key === issueMap.connectFrom) return;
      const defaults = { from_issue_id: issueMap.connectFrom.split(":")[1], to_issue_id: key.split(":")[1], kind: "関連" };
      issueMap.connectFrom = "";
      await editRow("issue_links", null, defaults);
      rerender();
      return;
    }
    issueMap.selected = issueMap.selected === key ? "" : key;
    applyHighlight();
    renderMapSide(box.querySelector("#im-side"), byKey, edges, rerender);
  };

  // 何もないところを押したら、選択をやめる
  // （カードのドラッグ中はポインタを捕まえるので、click ではなく pointerdown で判定する）
  wrap.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".im-card, .im-edge, .im-box-head")) return;
    if (issueMap.selected) {
      issueMap.selected = "";
      applyHighlight();
      renderMapSide(box.querySelector("#im-side"), byKey, edges, rerender);
    }
  });

  // 課題どうしの線を押したら、そのつながりを編集する
  edgeLayer.addEventListener("click", async (event) => {
    const el = event.target.closest(".im-edge.link");
    if (!el) return;
    if (await editLink(edges[Number(el.dataset.edge)].row)) rerender();
  });

  // ---------------------------------------------------------------- 上のボタン
  box.querySelector("#im-sol").onchange = (e) => { issueMap.showSolutions = e.target.checked; rerender(); };
  box.querySelector("#im-src").onchange = (e) => { issueMap.showSources = e.target.checked; rerender(); };
  box.querySelector("#im-drop").onchange = (e) => { issueMap.showDropped = e.target.checked; rerender(); };
  box.querySelectorAll("[data-im-zoom]").forEach((b) => {
    b.onclick = () => { savePref("issue_map_zoom", b.dataset.imZoom); rerender(); };
  });
  box.querySelector("#im-connect-cancel")?.addEventListener("click", () => { issueMap.connectFrom = ""; rerender(); });
  box.querySelector("#im-relayout").onclick = async () => {
    // 表示中のカードの保存した位置を消し、自動の配置に戻す（相手と共有している位置も変わる）
    const ok = await confirmDialog("表示中のカードの位置を、自動の配置に並べ直します。ZIP で共有している位置も、次に渡したときに変わります。");
    if (!ok) return;
    const keep = (state.tables.map_positions || []).filter((p) => !byKey[p.node]);
    state.tables.map_positions = keep;
    nodes.forEach((n) => { delete n.x; delete n.y; });
    layoutMapNodes(nodes, edges);
    try {
      await api("POST", "/api/map/positions", { positions: nodes.map((n) => ({ node: n.key, x: n.x, y: n.y })) });
      await reload();
      toast("並べ直しました。");
    } catch (e) { toast(e.message, true); }
    rerender();
  };
}

/**
 * 課題どうしのつながりを編集するダイアログを開く（削除もできる）。
 * @param {object} link issue_links の行
 * @returns {Promise<boolean>} 保存または削除したら true
 */
async function editLink(link) {
  // 入力欄を作り、ダイアログを開く
  const fields = FORMS.issue_links;
  const html = fields.map((f) => fieldHtml(f, link[f.key] ?? "", {})).join("") +
    `<p class="hint muted">最終更新：${h(link.updated_by)}（${h(link.updated_at)}）</p>`;
  const result = await openDialog(`${TABLE_NAME.issue_links}を編集`, html, [
    { label: "やめる", value: "cancel" }, { label: "削除", value: "delete", danger: true }, { label: "保存", value: "save", primary: true },
  ]);

  // 削除、または保存する
  if (result === "delete") {
    const ok = await confirmDialog("このつながりを削除します。");
    if (!ok) return false;
    try { await api("DELETE", `/api/tables/issue_links/${link.link_id}`); await reload(); toast("削除しました。"); return true; }
    catch (e) { toast(e.message, true); return false; }
  }
  if (result !== "save") return false;
  try {
    const values = collectValues(document.getElementById("dialog-body"), fields);
    await api("PUT", `/api/tables/issue_links/${link.link_id}`, { values });
    await reload();
    toast("保存しました。");
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  }
}

/**
 * 選んだカードの詳しい内容と、操作のボタンを右の欄に表示する。
 * @param {HTMLElement} side 表示先
 * @param {object} byKey キーからカードを引く表
 * @param {object[]} edges 線の一覧
 * @param {Function} rerender マップを描き直す関数
 * @returns {void}
 */
function renderMapSide(side, byKey, edges, rerender) {
  const node = byKey[issueMap.selected];
  if (!node) {
    side.innerHTML = `<h3>使い方</h3>
      <ul class="im-help">
        <li>カードを押すと、つながっている課題、解決策、データを強調し、ここに詳しい内容を出します。</li>
        <li>カードをドラッグで動かせます。テーマの見出しをドラッグすると、テーマごと動かせます。</li>
        <li>課題を別のテーマの囲みに入れると、テーマを変えるか確かめます。</li>
        <li>課題を選んで「つながりを追加」を押し、相手の課題を押すと、課題どうしをつなげます。</li>
        <li>紫の線（課題どうしのつながり）を押すと、種類やメモを直せます。</li>
      </ul>`;
    return;
  }
  const r = node.row;

  // 解決策の候補とデータ：その項目と、ひも付く課題
  if (node.type !== "issue") {
    const linked = edges.filter((e) => e.from === node.key).map((e) => byKey[e.to].row);
    const table = node.type === "solution" ? "solutions" : "data_sources";
    side.innerHTML = `
      <div class="im-side-kind">${node.type === "solution" ? "解決策の候補" : "データ"}</div>
      <h3>${h(node.type === "solution" ? r.method : r.name)}</h3>
      ${node.type === "solution" ? `<div class="md-view">${renderMarkdown(r.concern ? `**懸念点**\n\n${r.concern}` : "")}</div>`
        : `<p>${badge(r.confirmation)} ${h(r.location)}</p>`}
      <h4>ひも付く課題（${linked.length}）</h4>
      <ul>${linked.map((x) => `<li>${h(labelOf("issues", x))}</li>`).join("") || '<li class="muted">なし</li>'}</ul>
      <div class="actions"><button class="small" id="im-edit">編集</button></div>`;
    side.querySelector("#im-edit").onclick = async () => { if (await editRow(table, r)) rerender(); };
    return;
  }

  // 課題：つながり、解決策、データの一覧と、追加のボタン
  const links = (state.tables.issue_links || []).filter((k) => k.from_issue_id === r.issue_id || k.to_issue_id === r.issue_id);
  const linkText = (k) => {
    const out = k.from_issue_id === r.issue_id;
    const other = find("issues", out ? k.to_issue_id : k.from_issue_id);
    const arrow = k.kind === "原因" ? (out ? "→ の原因" : "← が原因") : k.kind === "影響" ? (out ? "→ に影響" : "← から影響") : `― ${k.kind}`;
    return `${arrow}：${h(labelOf("issues", other))}`;
  };
  const sols = state.tables.solutions.filter((s) => ids(s.issue_ids).includes(r.issue_id));
  const srcs = state.tables.data_sources.filter((d) => ids(d.issue_ids).includes(r.issue_id));
  side.innerHTML = `
    <div class="im-side-kind">課題（${h((find("persons", r.person_id) || {}).name)}）</div>
    <h3>${h(r.title)}</h3>
    <p>${badge(r.status)} <span class="muted">テーマ：${h(r.theme || "なし")}</span></p>
    ${r.quote ? `<blockquote class="im-quote">${h(r.quote)}</blockquote>` : ""}
    <h4>課題どうしのつながり（${links.length}）</h4>
    <ul>${links.map((k) => `<li><a href="javascript:void(0)" data-link="${k.link_id}">${linkText(k)}</a></li>`).join("") || '<li class="muted">なし</li>'}</ul>
    <h4>解決策の候補（${sols.length}）</h4>
    <ul>${sols.map((s) => `<li>${h(s.method)}</li>`).join("") || '<li class="muted">なし</li>'}</ul>
    <h4>データ（${srcs.length}）</h4>
    <ul>${srcs.map((d) => `<li>${h(d.name)}</li>`).join("") || '<li class="muted">なし</li>'}</ul>
    <div class="actions">
      <button class="small" id="im-edit">編集</button>
      <button class="small" id="im-connect">つながりを追加</button>
      <button class="small" id="im-add-sol">解決策の候補を追加</button>
      <button class="small" id="im-add-src">データを追加</button>
    </div>`;

  // ボタンの処理
  side.querySelector("#im-edit").onclick = async () => { if (await editRow("issues", r)) rerender(); };
  side.querySelector("#im-connect").onclick = () => { issueMap.connectFrom = node.key; rerender(); };
  side.querySelector("#im-add-sol").onclick = async () => {
    if (await editRow("solutions", null, { issue_ids: r.issue_id, uses_genai: "0" })) rerender();
  };
  side.querySelector("#im-add-src").onclick = async () => {
    if (await editRow("data_sources", null, { person_id: r.person_id, issue_ids: r.issue_id, confirmation: "本人の認識" })) rerender();
  };
  side.querySelectorAll("[data-link]").forEach((a) => {
    a.onclick = async () => { if (await editLink(find("issue_links", a.dataset.link))) rerender(); };
  });
}
