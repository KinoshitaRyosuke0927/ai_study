// コミュニケーション練習 PoC - フロントエンド
// 音声は WebRTC でブラウザ ⇔ Azure OpenAI Realtime API を直接やり取りし、
// イベント（文字起こし・発話状態）はデータチャネルで受け取る。
// ユーザの発話が確定するたびにバックエンドで受け手の感情を推定し、グラフに反映する。
// 推定には発話内容に加え、声の特徴（間・話速・声量・声の高さ・抑揚）も渡す。
// 推定した感情は振る舞いの指示として AI の会話に差し込み、会話終了後に振り返りレポートを生成する。

const $ = (id) => document.getElementById(id);

// 感情の軸ごとの線の色（style.css の --series-1〜4 と同じ固定順）
const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

const state = {
  options: null,
  pc: null, // RTCPeerConnection
  dc: null, // データチャネル
  micStream: null,
  analyzer: null, // VoiceAnalyzer（声量・声の高さの計測）
  sessionId: 0, // 古いセッションの評価結果を無視するための連番
  aiSpeaking: false,
  pendingInterrupt: false, // 次に確定するユーザ発話が割り込みかどうか
  interruptCount: 0,
  startedAt: 0,
  timerId: null,
  turns: new Map(), // item_id → { role, text, final, interrupted, bubble }
  speech: new Map(), // item_id → ユーザ発話区間の計測値 { start, end, audioStartMs, audioEndMs, latency, acoustic }
  aiStoppedAt: null, // AI が話し終えた時刻（間の計測用）
  baseline: { volume: [], pitch: [] }, // これまでの発話の声量・声の高さ（比較の基準）
  lastAiItemId: null,
  emotion: null, // 現在の感情値 { relief, tension, motivation, trust }
  evalChain: Promise.resolve(), // 感情推定を発話順に直列実行するためのキュー
  evalPending: 0,
  chart: null,
};

/**
 * 画面の選択肢をバックエンドから取得して表示する。
 */
async function loadOptions() {
  // 選択肢を取得
  const res = await fetch("/api/options");
  state.options = await res.json();
  const { personas, genders, scenarios, voices, vads, session_max_minutes } = state.options;

  // セレクトボックスへ反映
  fillSelect($("persona"), personas.map((p) => [p.id, p.name]));
  fillSelect($("gender"), genders.map((g) => [g.id, g.label]));
  fillScenarioSelect($("scenario"), scenarios);
  fillSelect($("voice"), voices.map((v) => [v.id, v.label]));
  fillSelect($("vad"), vads.map((v) => [v, v]));
  $("timer-max").textContent = formatTime(session_max_minutes * 60);

  // 選択に応じた説明・声の初期値・感情の初期値の表示
  $("persona").onchange = updateDescriptions;
  $("scenario").onchange = () => { updateDescriptions(); resetEmotion(); };
  $("gender").onchange = updateVoice;
  updateDescriptions();
  updateVoice();
  initChart();
  resetEmotion();
}

/**
 * セレクトボックスに選択肢を設定する。
 * @param {HTMLSelectElement} el 対象要素
 * @param {Array<[string, string]>} items [値, 表示名] の配列
 */
function fillSelect(el, items) {
  el.innerHTML = "";
  for (const [value, label] of items) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    el.appendChild(opt);
  }
}

/**
 * シナリオをカテゴリ（業務 / 雑談）ごとにグループ化して設定する。
 * @param {HTMLSelectElement} el 対象要素
 * @param {Array<object>} scenarios シナリオ一覧
 */
function fillScenarioSelect(el, scenarios) {
  el.innerHTML = "";
  const groups = new Map();
  for (const s of scenarios) {
    // カテゴリごとの optgroup を初回のみ作成
    if (!groups.has(s.category)) {
      const group = document.createElement("optgroup");
      group.label = s.category;
      groups.set(s.category, group);
      el.appendChild(group);
    }
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.title;
    groups.get(s.category).appendChild(opt);
  }
}

/**
 * 選択中のペルソナ・シナリオの説明を表示する。
 */
function updateDescriptions() {
  const persona = currentPersona();
  $("persona-desc").textContent = persona.description;
  $("situation").textContent = currentScenario().situation;
  $("emotion-title").textContent = personShortName();
}

/**
 * 選択中の性別に合わせて声の初期値を切り替える。
 */
function updateVoice() {
  const gender = state.options.genders.find((g) => g.id === $("gender").value);
  $("voice").value = gender.default_voice;
}

const currentPersona = () => state.options.personas.find((p) => p.id === $("persona").value);
const currentScenario = () => state.options.scenarios.find((s) => s.id === $("scenario").value);
// 「新入社員 鈴木さん」→「鈴木さん」
const personShortName = () => currentPersona().name.split(" ").pop();

// ===================================================================
// セッション管理
// ===================================================================

/**
 * 会話セッションを開始する（マイク取得 → WebRTC 接続）。
 */
async function startSession() {
  state.sessionId += 1;
  setControls(true);
  setConnStatus("接続中…", "connecting");
  clearLog();
  resetEmotion();
  $("report-body").innerHTML = "";
  $("report-btn").disabled = true;

  try {
    // マイク取得（エコー除去を有効にしてスピーカー音の回り込みを防ぐ）
    // 自動音量調整は声量の計測を打ち消してしまうため無効にする
    state.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
    });
    state.analyzer = new VoiceAnalyzer(state.micStream);

    // PeerConnection を作成し、AI の音声を audio 要素で再生
    const pc = new RTCPeerConnection();
    state.pc = pc;
    pc.ontrack = (e) => { $("remote-audio").srcObject = e.streams[0]; };
    pc.addTrack(state.micStream.getAudioTracks()[0], state.micStream);
    pc.onconnectionstatechange = () => {
      if (["failed", "disconnected"].includes(pc.connectionState)) stopSession("接続が切断されました");
    };

    // イベント受信用データチャネル
    const dc = pc.createDataChannel("oai-events");
    state.dc = dc;
    dc.onmessage = (e) => handleServerEvent(JSON.parse(e.data));
    dc.onopen = onChannelOpen;

    // SDP オファーをバックエンド経由で Azure に送り、アンサーを設定
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const res = await fetch("/api/realtime/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sdp: offer.sdp,
        ...selectionPayload(),
        voice: $("voice").value,
        vad: $("vad").value,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    await pc.setRemoteDescription({ type: "answer", sdp: await res.text() });
  } catch (err) {
    console.error(err);
    stopSession(`接続に失敗しました: ${err.message}`);
  }
}

/**
 * ペルソナ・性別・シナリオの選択内容を返す（API リクエスト共通部分）。
 * @returns {{persona_id: string, gender_id: string, scenario_id: string}}
 */
function selectionPayload() {
  return {
    persona_id: $("persona").value,
    gender_id: $("gender").value,
    scenario_id: $("scenario").value,
  };
}

/**
 * データチャネル開通時の処理（タイマー開始・AI の第一声）。
 */
function onChannelOpen() {
  setConnStatus("接続中（話しかけてください）", "connected");
  addSystemMessage("会話を開始しました");

  // 経過時間タイマー（上限で自動終了）
  state.startedAt = Date.now();
  const maxSec = state.options.session_max_minutes * 60;
  state.timerId = setInterval(() => {
    const sec = Math.floor((Date.now() - state.startedAt) / 1000);
    $("timer").textContent = formatTime(sec);
    if (sec >= maxSec) stopSession("上限時間に達したため終了しました");
  }, 500);

  // AI から話し始めるシナリオでは応答生成を要求
  if (currentScenario().ai_speaks_first) send({ type: "response.create" });
}

/**
 * セッションを終了し、リソースを解放する。
 * @param {string} [reason] ログに表示する終了理由
 */
function stopSession(reason = "会話を終了しました") {
  // 二重終了の防止
  if (!state.pc && !state.micStream) return;

  // 接続・マイク・タイマーの解放
  clearInterval(state.timerId);
  state.dc?.close();
  state.pc?.close();
  state.micStream?.getTracks().forEach((t) => t.stop());
  state.analyzer?.close();
  state.pc = state.dc = state.micStream = state.analyzer = null;

  // 表示の後始末（評価中の結果は終了後も反映する）
  setIndicator("user-indicator", false);
  setIndicator("ai-indicator", false);
  state.aiSpeaking = false;
  setConnStatus("未接続", "");
  setControls(false);
  addSystemMessage(reason);

  // 評価済みの発話があれば振り返りレポートを作成
  if ([...state.turns.values()].some((t) => t.role === "user" && t.final)) createReport(state.sessionId);
}

/**
 * データチャネルでイベントを送信する。
 * @param {object} event Realtime API のクライアントイベント
 */
function send(event) {
  if (state.dc?.readyState === "open") state.dc.send(JSON.stringify(event));
}

// ===================================================================
// Realtime API のイベント処理
// ===================================================================

/**
 * Realtime API から届いたサーバイベントを処理する。
 * @param {object} ev サーバイベント
 */
function handleServerEvent(ev) {
  switch (ev.type) {
    // --- ユーザの発話状態 ---
    case "input_audio_buffer.speech_started":
      setIndicator("user-indicator", true);
      // AI の発話中に話し始めた = 割り込み
      if (state.aiSpeaking) markInterrupted();
      onSpeechStarted(ev);
      break;
    case "input_audio_buffer.speech_stopped":
      setIndicator("user-indicator", false);
      onSpeechStopped(ev);
      break;
    case "input_audio_buffer.committed":
      // 発話が確定した時点で吹き出しを確保（文字起こしは後から届く）
      upsertTurn(ev.item_id, "user", "（文字起こし中…）", { pending: true });
      state.turns.get(ev.item_id).interrupted = state.pendingInterrupt;
      state.pendingInterrupt = false;
      break;

    // --- ユーザ発話の文字起こし（gpt-transcribe は途中経過も届く） ---
    case "conversation.item.input_audio_transcription.delta": {
      const turn = state.turns.get(ev.item_id);
      // 最初の差分で「文字起こし中…」を置き換え、以降は追記
      if (!turn || turn.pending) upsertTurn(ev.item_id, "user", ev.delta);
      else appendTurn(ev.item_id, "user", ev.delta);
      break;
    }
    case "conversation.item.input_audio_transcription.completed": {
      const text = ev.transcript.trim();
      upsertTurn(ev.item_id, "user", text || "（聞き取れませんでした）", { final: true });
      // 文字起こしが確定したら、声の特徴をまとめて感情推定をキューに積む
      if (text) {
        state.turns.get(ev.item_id).voice = buildVoiceFeatures(ev.item_id, text);
        enqueueEvaluation(ev.item_id);
      }
      break;
    }
    case "conversation.item.input_audio_transcription.failed":
      upsertTurn(ev.item_id, "user", "（文字起こしに失敗しました）", { final: true });
      break;

    // --- AI の発話状態（WebRTC 時の再生バッファ） ---
    case "output_audio_buffer.started":
      state.aiSpeaking = true;
      setIndicator("ai-indicator", true);
      break;
    case "output_audio_buffer.stopped":
      // 最後まで話し終えた時刻を記録（次のユーザ発話までの間の計測用）
      state.aiStoppedAt = performance.now();
      state.aiSpeaking = false;
      setIndicator("ai-indicator", false);
      break;
    case "output_audio_buffer.cleared":
      // 割り込みで止まった場合は間を計測しない
      state.aiStoppedAt = null;
      state.aiSpeaking = false;
      setIndicator("ai-indicator", false);
      break;

    // --- AI 発話の文字起こし（ストリーミング） ---
    case "response.output_audio_transcript.delta":
      state.lastAiItemId = ev.item_id;
      appendTurn(ev.item_id, "ai", ev.delta);
      break;
    case "response.output_audio_transcript.done":
      upsertTurn(ev.item_id, "ai", ev.transcript, { final: true });
      break;

    case "error":
      console.error("Realtime error", ev.error);
      addSystemMessage(`エラー: ${ev.error?.message ?? "不明なエラー"}`);
      break;
  }
}

// ===================================================================
// 声の特徴の計測
// ===================================================================

// speech_started は発話開始の検出後に届くため、少し前から区間に含める
const SPEECH_PREROLL_MS = 500;
// speech_started の受信は実際の発話開始より遅れるため、間の計測値から差し引く
const SPEECH_DETECT_LAG_SEC = 0.3;

/**
 * ユーザ発話の開始を記録する（区間の開始時刻・相手が話し終えてからの間）。
 * @param {object} ev input_audio_buffer.speech_started イベント
 */
function onSpeechStarted(ev) {
  const now = performance.now();

  // 相手（AI）が話し終えてからの間。割り込み時・相手が話していない場合は計測しない
  let latency = null;
  if (!state.aiSpeaking && state.aiStoppedAt !== null) {
    latency = Math.max(0, (now - state.aiStoppedAt) / 1000 - SPEECH_DETECT_LAG_SEC);
  }
  state.aiStoppedAt = null;

  state.speech.set(ev.item_id, {
    start: now - SPEECH_PREROLL_MS,
    end: null,
    audioStartMs: ev.audio_start_ms,
    audioEndMs: null,
    latency,
    acoustic: null,
  });
}

/**
 * ユーザ発話の終了を記録し、区間内の声量・声の高さを集計する。
 * @param {object} ev input_audio_buffer.speech_stopped イベント
 */
function onSpeechStopped(ev) {
  const sp = state.speech.get(ev.item_id);
  if (!sp) return;
  sp.end = performance.now();
  sp.audioEndMs = ev.audio_end_ms;
  sp.acoustic = state.analyzer?.summarize(sp.start, sp.end) ?? null;
}

/**
 * 1 発話分の声の特徴量を組み立てる（これまでの発話との比較を含む）。
 * @param {string} itemId ユーザ発話の item_id
 * @param {string} text 文字起こし
 * @returns {object|null} バックエンドの VoiceFeatures 形式。計測できていなければ null
 */
function buildVoiceFeatures(itemId, text) {
  const sp = state.speech.get(itemId);
  if (!sp) return null;
  const ac = sp.acoustic ?? {};

  // 発話区間の長さ（サーバの VAD 時刻を優先）と話速
  const duration = sp.audioEndMs != null && sp.audioStartMs != null
    ? (sp.audioEndMs - sp.audioStartMs) / 1000
    : ac.voicedSec ?? null;
  const speechRate = duration > 0 ? estimateMora(text) / duration : null;

  // これまでの発話（中央値）との差
  const { volume, pitch } = state.baseline;
  const volumeDiff = ac.volumeDb != null && volume.length ? ac.volumeDb - median(volume) : null;
  const pitchDiff = ac.pitchHz != null && pitch.length ? 12 * Math.log2(ac.pitchHz / median(pitch)) : null;

  // 今回の値を次回以降の基準に加える
  if (ac.volumeDb != null) volume.push(ac.volumeDb);
  if (ac.pitchHz != null) pitch.push(ac.pitchHz);

  return {
    duration_sec: duration,
    speech_rate: speechRate,
    volume_db: ac.volumeDb ?? null,
    volume_vs_baseline_db: volumeDiff,
    pitch_hz: ac.pitchHz ?? null,
    pitch_vs_baseline_st: pitchDiff,
    pitch_variation_st: ac.pitchVariationSt ?? null,
    response_latency_sec: sp.latency,
  };
}

/**
 * 割り込みを記録し、直前の AI 発話に印を付ける。
 */
function markInterrupted() {
  state.interruptCount += 1;
  state.pendingInterrupt = true;
  $("interrupt-count").textContent = state.interruptCount;
  const bubble = state.turns.get(state.lastAiItemId)?.bubble;
  if (bubble && !bubble.querySelector(".tag")) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "⚠ 発話の途中で遮られました";
    bubble.appendChild(tag);
  }
}

// ===================================================================
// 会話ログ
// ===================================================================

/**
 * 発話を作成または本文を置き換える（吹き出しも同期）。
 * @param {string} itemId 会話アイテム ID
 * @param {"user"|"ai"} role 話者
 * @param {string} text 本文
 * @param {{pending?: boolean, final?: boolean}} [opts] 文字起こし待ち / 確定
 */
function upsertTurn(itemId, role, text, { pending = false, final = false } = {}) {
  // 既存の発話がなければ吹き出しごと作成（Map の挿入順 = 会話順）
  let turn = state.turns.get(itemId);
  if (!turn) {
    const bubble = document.createElement("div");
    bubble.className = `msg ${role}`;
    bubble.appendChild(document.createElement("span"));
    $("log").appendChild(bubble);
    turn = { role, text: "", final: false, pending: false, interrupted: false, bubble };
    state.turns.set(itemId, turn);
  }

  // 本文と状態を更新
  turn.text = text;
  turn.pending = pending;
  turn.final = turn.final || final;
  turn.bubble.firstChild.textContent = text;
  turn.bubble.classList.toggle("pending", pending);
  scrollLog();
}

/**
 * 発話の本文に文字を追記する（ストリーミング表示用）。
 * @param {string} itemId 会話アイテム ID
 * @param {"user"|"ai"} role 話者
 * @param {string} delta 追記する文字列
 */
function appendTurn(itemId, role, delta) {
  const turn = state.turns.get(itemId);
  if (!turn) return upsertTurn(itemId, role, delta);
  turn.text += delta;
  turn.bubble.firstChild.textContent = turn.text;
  scrollLog();
}

/**
 * システムメッセージを会話ログに追加する。
 * @param {string} text 表示する文言
 */
function addSystemMessage(text) {
  const el = document.createElement("div");
  el.className = "msg system";
  el.textContent = text;
  $("log").appendChild(el);
  scrollLog();
}

function clearLog() {
  $("log").innerHTML = "";
  state.turns.clear();
  state.speech.clear();
  state.aiStoppedAt = null;
  state.baseline = { volume: [], pitch: [] };
  state.lastAiItemId = null;
  state.pendingInterrupt = false;
  state.interruptCount = 0;
  $("interrupt-count").textContent = "0";
  $("timer").textContent = "00:00";
}

function scrollLog() {
  const log = $("log");
  log.scrollTop = log.scrollHeight;
}

// ===================================================================
// 感情推定
// ===================================================================

/**
 * 感情推定をキューに積む（前の推定結果を引き継ぐため発話順に直列実行）。
 * @param {string} itemId 評価対象のユーザ発話の item_id
 */
function enqueueEvaluation(itemId) {
  const sessionId = state.sessionId;
  state.evalPending += 1;
  updateEvalStatus();
  state.evalChain = state.evalChain
    .then(() => evaluateTurn(itemId, sessionId))
    .catch((err) => console.error("感情推定エラー", err))
    .finally(() => { state.evalPending -= 1; updateEvalStatus(); });
}

/**
 * 1 発話分の感情推定を行い、画面に反映する。
 * @param {string} itemId 評価対象のユーザ発話の item_id
 * @param {number} sessionId 依頼時点のセッション番号
 */
async function evaluateTurn(itemId, sessionId) {
  // 別セッションに切り替わっていたら破棄
  if (sessionId !== state.sessionId) return;
  const target = state.turns.get(itemId);

  // 評価対象より前の確定済み発話を履歴にする
  const history = [];
  for (const [id, turn] of state.turns) {
    if (id === itemId) break;
    if (turn.final && !turn.pending) history.push({ role: turn.role, text: turn.text });
  }

  // バックエンドで推定
  const res = await fetch("/api/emotion/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...selectionPayload(),
      history,
      utterance: target.text,
      interrupted: target.interrupted,
      current: state.emotion,
      voice: target.voice ?? null,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const result = await res.json();
  if (sessionId !== state.sessionId) return;

  // 状態・グラフ・会話ログに反映
  state.emotion = result.emotion;
  target.evaluation = result;
  renderMeters(result.emotion, result.delta);
  $("inner-voice").textContent = `「${result.inner_voice}」`;
  $("emotion-reason").textContent = result.reason;
  pushChartPoint(target.text, result);
  annotateTurn(target, result);

  // 感情を AI の態度に反映（次の応答から効く振る舞いの指示を会話に差し込む）
  $("directive").textContent = result.directive;
  send({
    type: "conversation.item.create",
    item: { type: "message", role: "system", content: [{ type: "input_text", text: result.directive }] },
  });
}

/**
 * ユーザ発話の吹き出しに、声の特徴と評価（良かった点・気になった点）を付ける。
 * @param {object} turn 対象の発話
 * @param {object} result 推定結果
 */
function annotateTurn(turn, result) {
  // 声の特徴（印象に影響しうるものは強調）
  const voiceBox = document.createElement("div");
  voiceBox.className = "eval";
  for (const lb of result.voice_labels) {
    const el = chip(`${lb.name}: ${lb.label}`, lb.notable ? "voice notable" : "voice");
    el.title = lb.value;
    voiceBox.appendChild(el);
  }
  if (voiceBox.childElementCount) turn.bubble.appendChild(voiceBox);

  // 良かった点・気になった点
  const box = document.createElement("div");
  box.className = "eval";
  for (const text of result.good_points) box.appendChild(chip(`○ ${text}`, "good"));
  for (const text of result.bad_points) box.appendChild(chip(`△ ${text}`, "bad"));
  if (box.childElementCount) turn.bubble.appendChild(box);
}

/**
 * 小さなラベル要素を作成する。
 * @param {string} text 表示文字列
 * @param {string} cls 追加するクラス
 * @returns {HTMLSpanElement}
 */
function chip(text, cls) {
  const el = document.createElement("span");
  el.className = `chip ${cls}`;
  el.textContent = text;
  return el;
}

function updateEvalStatus() {
  $("eval-status").textContent = state.evalPending > 0 ? "推定中…" : "";
}

// ===================================================================
// 感情の表示（メーター・グラフ）
// ===================================================================

/**
 * 感情をシナリオの初期値に戻し、メーターとグラフをリセットする。
 */
function resetEmotion() {
  state.emotion = { ...currentScenario().initial_emotion };
  renderMeters(state.emotion, null);
  $("inner-voice").textContent = "―";
  $("emotion-reason").textContent = "";
  $("directive").textContent = "（まだありません）";

  // グラフは「開始」時点の値だけにする
  const chart = state.chart;
  chart.data.labels = ["開始"];
  chart.data.datasets.forEach((ds) => { ds.data = [state.emotion[ds.key]]; });
  chart.$meta = [null]; // ツールチップ用（発話・理由）
  chart.update();
}

/**
 * 軸ごとのメーター（現在値と直近の変化量）を描画する。
 * @param {object} emotion 感情値
 * @param {object|null} delta 直近の変化量
 */
function renderMeters(emotion, delta) {
  const box = $("meters");
  box.innerHTML = "";
  state.options.emotion_axes.forEach((axis, i) => {
    const row = document.createElement("div");
    row.className = "meter";
    const d = delta?.[axis.id] ?? 0;
    row.innerHTML = `
      <span class="meter-name"><span class="meter-key"></span></span>
      <span class="meter-track"><span class="meter-fill"></span></span>
      <span class="meter-value"></span>
      <span class="meter-delta"></span>`;
    row.querySelector(".meter-key").style.background = SERIES_COLORS[i];
    row.querySelector(".meter-name").append(axis.label);
    row.querySelector(".meter-fill").style.cssText = `width:${emotion[axis.id]}%;background:${SERIES_COLORS[i]}`;
    row.querySelector(".meter-value").textContent = emotion[axis.id];
    row.querySelector(".meter-delta").textContent = delta ? (d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : "±0") : "";
    box.appendChild(row);
  });
}

/**
 * 感情推移グラフを初期化する。
 */
function initChart() {
  const ctx = $("emotion-chart");
  state.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: state.options.emotion_axes.map((axis, i) => ({
        key: axis.id,
        label: axis.label,
        data: [],
        borderColor: SERIES_COLORS[i],
        backgroundColor: SERIES_COLORS[i],
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBorderColor: "#fff",
        pointBorderWidth: 2,
        tension: 0.3,
      })),
    },
    options: {
      maintainAspectRatio: false,
      animation: { duration: 500 },
      // 縦線上の全系列をまとめてツールチップ表示
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          min: 0,
          max: 100,
          ticks: { stepSize: 25, color: "#8a8984" },
          grid: { color: "#eeeeec" },
        },
        x: { ticks: { color: "#8a8984" }, grid: { display: false } },
      },
      plugins: {
        legend: { position: "top", labels: { boxWidth: 10, boxHeight: 10, color: "#52514e" } },
        tooltip: {
          callbacks: {
            // 発話内容と変化の理由をツールチップに表示
            title: (items) => {
              const meta = state.chart.$meta[items[0].dataIndex];
              return meta ? `${items[0].label}: 「${truncate(meta.utterance, 30)}」` : "会話開始時";
            },
            afterBody: (items) => {
              const meta = state.chart.$meta[items[0].dataIndex];
              return meta ? ["", ...wrapText(meta.reason, 24)] : [];
            },
          },
        },
      },
    },
  });
}

/**
 * グラフに 1 発話分の点を追加する。
 * @param {string} utterance ユーザの発話
 * @param {object} result 推定結果
 */
function pushChartPoint(utterance, result) {
  const chart = state.chart;
  chart.data.labels.push(`発話${chart.data.labels.length}`);
  chart.data.datasets.forEach((ds) => ds.data.push(result.emotion[ds.key]));
  chart.$meta.push({ utterance, reason: result.reason });
  chart.update();
}

// ===================================================================
// 振り返りレポート
// ===================================================================

/**
 * 会話終了後に振り返りレポートを生成して表示する。
 * @param {number} sessionId 対象のセッション番号
 */
async function createReport(sessionId) {
  // 生成中の表示
  const body = $("report-body");
  body.innerHTML = '<p class="report-loading">レポートを作成しています…</p>';
  openReport();

  try {
    // 実行中の感情推定がすべて終わるのを待つ
    await state.evalChain;
    if (sessionId !== state.sessionId) return;

    // 評価付きの会話ログを組み立てる（文字起こし待ちのまま終わった発話は除く）
    const turns = [...state.turns.values()]
      .filter((t) => t.final && !t.pending)
      .map((t) => ({
        role: t.role,
        text: t.text,
        evaluation: t.evaluation
          ? {
              delta: t.evaluation.delta,
              reason: t.evaluation.reason,
              good_points: t.evaluation.good_points,
              bad_points: t.evaluation.bad_points,
              voice_labels: t.evaluation.voice_labels.map((lb) => `${lb.name}: ${lb.label}`),
            }
          : null,
      }));
    const initial = currentScenario().initial_emotion;

    // バックエンドで生成
    const res = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...selectionPayload(),
        turns,
        initial_emotion: initial,
        final_emotion: state.emotion,
        interrupt_count: state.interruptCount,
      }),
    });
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
    const report = await res.json();
    if (sessionId !== state.sessionId) return;

    renderReport(report, initial, state.emotion);
    $("report-btn").disabled = false;
  } catch (err) {
    console.error(err);
    body.innerHTML = "";
    body.appendChild(el("p", "report-loading", `レポートを作成できませんでした: ${err.message}`));
  }
}

/**
 * レポートの内容を描画する。
 * @param {object} report バックエンドが生成したレポート
 * @param {object} initial 開始時の感情値
 * @param {object} final 終了時の感情値
 */
function renderReport(report, initial, final) {
  const body = $("report-body");
  body.innerHTML = "";
  const name = personShortName();

  // 見出し情報（シナリオ・会話時間）
  body.appendChild(el("p", "report-meta",
    `${currentScenario().category} / ${currentScenario().title}　会話時間 ${$("timer").textContent}　割り込み ${state.interruptCount} 回`));

  // 総評
  body.appendChild(el("h3", "", "総評"));
  body.appendChild(el("p", "", report.summary));

  // 感情の変化（開始 → 終了）
  body.appendChild(el("h3", "", `${name}の気持ちの変化`));
  const table = document.createElement("table");
  table.className = "report-emotions";
  table.innerHTML = "<thead><tr><th></th><th>開始</th><th>終了</th><th>変化</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const axis of state.options.emotion_axes) {
    const d = final[axis.id] - initial[axis.id];
    const tr = document.createElement("tr");
    for (const text of [axis.label, initial[axis.id], final[axis.id], d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : "±0"]) {
      tr.appendChild(el("td", "", String(text)));
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  body.appendChild(table);
  body.appendChild(el("p", "report-meta", "※緊張は低いほど良い状態です。発言ごとの推移は右側のグラフで確認できます。"));

  // 相手から見た印象
  body.appendChild(el("h3", "", `${name}から見たあなた`));
  body.appendChild(el("p", "report-impression", `「${report.impression}」`));

  // 良かった発言
  body.appendChild(el("h3", "", "良かったところ"));
  for (const item of report.good_points) {
    const box = el("div", "report-item", "");
    box.appendChild(el("div", "quote", `「${item.quote}」`));
    box.appendChild(el("div", "", item.comment));
    body.appendChild(box);
  }

  // 改善したい発言（言い換え例つき）
  if (report.improvements.length) {
    body.appendChild(el("h3", "", "もっと良くできるところ"));
    for (const item of report.improvements) {
      const box = el("div", "report-item", "");
      box.appendChild(el("div", "quote", `「${item.quote}」`));
      box.appendChild(el("div", "", item.problem));
      box.appendChild(el("div", "better", item.better));
      body.appendChild(box);
    }
  }

  // 次回のポイント
  body.appendChild(el("h3", "", "次回意識すること"));
  body.appendChild(el("p", "report-focus", report.next_focus));
}

function openReport() {
  const dialog = $("report-dialog");
  if (!dialog.open) dialog.showModal();
}

/**
 * テキストを持つ要素を作成する（innerHTML を使わず XSS を防ぐ）。
 * @param {string} tag タグ名
 * @param {string} cls クラス名
 * @param {string} text テキスト
 * @returns {HTMLElement}
 */
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  e.textContent = text;
  return e;
}

// ===================================================================
// 汎用
// ===================================================================

function truncate(text, n) {
  return text.length > n ? `${text.slice(0, n)}…` : text;
}

function wrapText(text, n) {
  const lines = [];
  for (let i = 0; i < text.length; i += n) lines.push(text.slice(i, i + n));
  return lines;
}

function setIndicator(id, active) {
  $(id).classList.toggle("active", active);
}

function setConnStatus(text, cls) {
  const el = $("conn-status");
  el.textContent = text;
  el.className = `badge ${cls}`;
}

/**
 * 接続中/未接続に応じてボタンと選択欄の有効状態を切り替える。
 * @param {boolean} running 接続中かどうか
 */
function setControls(running) {
  $("start-btn").disabled = running;
  $("stop-btn").disabled = !running;
  for (const id of ["persona", "gender", "scenario", "voice", "vad"]) $(id).disabled = running;
}

function formatTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

// 初期化
$("start-btn").onclick = startSession;
$("stop-btn").onclick = () => stopSession();
$("report-btn").onclick = openReport;
$("report-close").onclick = () => $("report-dialog").close();
loadOptions();
