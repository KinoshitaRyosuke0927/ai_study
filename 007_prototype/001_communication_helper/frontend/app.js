// コミュニケーション練習 PoC - フロントエンド
// 音声は WebRTC でブラウザ ⇔ Azure OpenAI Realtime API を直接やり取りし、
// イベント（文字起こし・発話状態）はデータチャネルで受け取る。
// ユーザの発話が確定するたびにバックエンドで受け手の感情を推定し、グラフに反映する。
// 推定には発話内容に加え、声の特徴（間・話速・声量・声の高さ・抑揚）も渡す。
// 推定した感情は振る舞いの指示として AI の会話に差し込み、会話終了後に振り返りレポートを生成する。
// 話者交代は自動応答を使わず、発話ごとのターン判定（応答 / 相づち / 待機）と沈黙タイマーで制御する。

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
  userSpeaking: false,
  responseActive: false, // AI の応答（音声）を生成中か
  responseRequestedAt: 0,
  responsePurposes: new Map(), // response_id → 応答の目的（respond / backchannel / proactive / opening / turn_judge）
  judgeSeq: 0, // ターン判定の連番（古い判定結果を無視するため）
  lastActivityAt: 0, // 最後に誰かが話した・応答を要求した時刻（沈黙の計測用）
  proactiveDone: false, // 今回の沈黙ですでに AI から話しかけたか
  stage: "導入", // 会話の進行段階（感情推定で判定: 導入 / 本題 / まとめ / 終了）
  nextAction: "", // 感情推定で判定した「後輩が次にすべきこと」（沈黙時の話しかけに添える）
  closingDone: false, // 締めの段階（まとめ / 終了）で締めの一言をすでに言わせたか
  itemSeq: 0, // 差し込むシステムメッセージの ID 用の連番
  directiveItemId: null, // 会話に残している最新の態度の指示の ID（次の指示を入れるときに削除）
  promptItemId: null, // 応答待ちの 1 回きりの指示の ID（応答が終わったら削除）
  pendingInterrupt: false, // 次に確定するユーザ発話が割り込みかどうか
  lastInterruptItemId: null, // 直前に割り込みと判定したユーザ発話の item_id（取り消し用）
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
  lastReport: null, // ダウンロード用のレポート { report, ctx }
  logPinned: true, // 会話ログを最下部（最新）に追従させるか（ユーザが上にスクロールすると false）
};

/**
 * 画面の選択肢をバックエンドから取得して表示する。
 */
async function loadOptions() {
  // 選択肢を取得
  const res = await fetch("/api/options");
  state.options = await res.json();
  const { personas, genders, scenarios, session_max_minutes } = state.options;

  // セレクトボックスへ反映
  fillSelect($("persona"), personas.map((p) => [p.id, p.name]));
  fillSelect($("gender"), genders.map((g) => [g.id, g.label]));
  fillScenarioSelect($("scenario"), scenarios);
  $("timer-max").textContent = formatTime(session_max_minutes * 60);

  // 選択に応じた説明・感情の初期値・表情の表示
  $("persona").onchange = updateDescriptions;
  $("scenario").onchange = () => { updateDescriptions(); resetEmotion(); };
  $("gender").onchange = () => { preloadFaces(); updateExpression(state.emotion, null); };
  updateDescriptions();
  preloadFaces();
  setVideoOnline(false);
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
  const scenario = currentScenario();
  $("persona-name").textContent = persona.name;
  $("persona-desc").textContent = persona.description;
  $("situation-title").textContent = `${scenario.category} / ${scenario.title}`;
  $("situation").textContent = scenario.situation;
  $("emotion-title").textContent = personShortName();
  $("video-name").textContent = personShortName();
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
  $("report-download").disabled = true;
  state.lastReport = null;

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

  // 経過時間タイマー（上限で自動終了）と沈黙の監視
  state.startedAt = Date.now();
  markActivity();
  const maxSec = state.options.session_max_minutes * 60;
  state.timerId = setInterval(() => {
    const sec = Math.floor((Date.now() - state.startedAt) / 1000);
    $("timer").textContent = formatTime(sec);
    if (sec >= maxSec) stopSession("上限時間に達したため終了しました");
    else checkSilence();
  }, 500);

  // AI から話し始めるシナリオでは応答生成を要求
  if (currentScenario().ai_speaks_first) requestResponse("opening");
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
  state.aiSpeaking = state.userSpeaking = state.responseActive = false;
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
      if (state.aiSpeaking) markInterrupted(ev.item_id);
      onSpeechStarted(ev);
      // ユーザが話したので、沈黙時に AI から話しかける権利を戻す
      state.userSpeaking = true;
      state.proactiveDone = false;
      markActivity();
      break;
    case "input_audio_buffer.speech_stopped":
      setIndicator("user-indicator", false);
      onSpeechStopped(ev);
      state.userSpeaking = false;
      markActivity();
      break;
    case "input_audio_buffer.committed":
      // 発話が確定した時点で吹き出しを確保（文字起こしは後から届く）
      upsertTurn(ev.item_id, "user", "（文字起こし中…）", { pending: true });
      state.turns.get(ev.item_id).interrupted = state.pendingInterrupt;
      state.pendingInterrupt = false;
      // AI が話す番かどうかを判定
      requestTurnJudge();
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
      markActivity();
      break;
    case "output_audio_buffer.stopped":
      // 最後まで話し終えた時刻を記録（次のユーザ発話までの間の計測用）
      state.aiStoppedAt = performance.now();
      state.aiSpeaking = false;
      setIndicator("ai-indicator", false);
      markActivity();
      break;
    case "output_audio_buffer.cleared":
      // 割り込みで止まった場合は間を計測しない
      state.aiStoppedAt = null;
      state.aiSpeaking = false;
      setIndicator("ai-indicator", false);
      markActivity();
      break;

    // --- 応答の開始・終了（ターン判定の結果もここで受け取る） ---
    case "response.created":
      state.responsePurposes.set(ev.response.id, ev.response.metadata?.purpose ?? "respond");
      break;
    case "response.done":
      if (ev.response.metadata?.purpose === "turn_judge") {
        handleTurnJudge(ev.response);
      } else {
        state.responseActive = false;
        markActivity();
        // 相づち・話しかけなどの 1 回きりの指示は、使い終わったら削除する
        deleteSystemItem(state.promptItemId);
        state.promptItemId = null;
      }
      break;

    // --- AI 発話の文字起こし（ストリーミング） ---
    case "response.output_audio_transcript.delta": {
      state.lastAiItemId = ev.item_id;
      const isNew = !state.turns.has(ev.item_id);
      appendTurn(ev.item_id, "ai", ev.delta);
      // 相づちは小さく表示
      if (isNew && state.responsePurposes.get(ev.response_id) === "backchannel") {
        state.turns.get(ev.item_id).backchannel = true;
        state.turns.get(ev.item_id).bubble.classList.add("backchannel");
      }
      break;
    }
    case "response.output_audio_transcript.done":
      upsertTurn(ev.item_id, "ai", ev.transcript, { final: true });
      break;

    case "error":
      // AI の話し終わりと同時に話し始めたときの切り詰め失敗は無害なので、画面に出さず割り込みを取り消す
      if (isTruncateAfterEndError(ev.error)) {
        console.debug("割り込みを取り消し:", ev.error.message);
        cancelLastInterrupt();
        break;
      }
      // 指示の削除の失敗（すでに無い等）は会話に影響しないので画面に出さない
      if (ev.error?.event_id?.startsWith("del_")) {
        console.debug("指示の削除に失敗:", ev.error.message);
        break;
      }
      console.error("Realtime error", ev.error);
      addSystemMessage(`エラー: ${ev.error?.message ?? "不明なエラー"}`);
      break;
  }
}

// ===================================================================
// 話者交代の制御
// ===================================================================

/**
 * 最後に会話の動きがあった時刻を更新する（沈黙の計測をリセット）。
 */
function markActivity() {
  state.lastActivityAt = performance.now();
}

/**
 * AI に音声で応答させる。
 * @param {string} purpose 応答の目的（respond / backchannel / proactive / opening）
 * @param {string} [prompt] 応答の直前に差し込むシステムメッセージ（相づち・話しかけの指示）
 */
function requestResponse(purpose, prompt) {
  // 1 回きりの指示は、応答が終わったら削除できるよう ID を付けて差し込む
  if (prompt) state.promptItemId = addSystemItem("tmp", prompt);
  send({ type: "response.create", response: { metadata: { purpose } } });
  state.responseActive = true;
  state.responseRequestedAt = performance.now();
  markActivity();
}

// 応答を要求したのに音声が始まらないまま、この時間が過ぎたら要求失敗とみなす
const RESPONSE_TIMEOUT_MS = 10_000;

/**
 * システムメッセージを ID 付きで会話に差し込む（後から削除できるようにする）。
 * @param {string} kind ID の接頭辞（dir: 態度の指示 / tmp: 1 回きりの指示）
 * @param {string} text 指示文
 * @returns {string} 差し込んだアイテムの ID
 */
function addSystemItem(kind, text) {
  state.itemSeq += 1;
  const id = `${kind}_${state.sessionId}_${state.itemSeq}`;
  send({
    type: "conversation.item.create",
    item: { id, type: "message", role: "system", content: [{ type: "input_text", text }] },
  });
  return id;
}

/**
 * 差し込んだシステムメッセージを会話から削除する（古い指示が文脈に残って混乱するのを防ぐ）。
 * @param {string|null} id 削除するアイテムの ID
 */
function deleteSystemItem(id) {
  if (id) send({ type: "conversation.item.delete", item_id: id, event_id: `del_${id}` });
}

/**
 * 最新のユーザ発話の後に AI が話す番かどうかを判定させる。
 * 会話に残らない裏側の応答（out-of-band）で、判定用の関数を必ず呼ばせて結果を受け取る。
 */
function requestTurnJudge() {
  state.judgeSeq += 1;
  const tt = state.options.turn_taking;
  send({
    type: "response.create",
    response: {
      conversation: "none",
      output_modalities: ["text"],
      instructions: tt.judge_instructions,
      tools: [tt.judge_tool],
      tool_choice: "required",
      metadata: { purpose: "turn_judge", seq: String(state.judgeSeq) },
    },
  });
}

/**
 * ターン判定の応答から判定結果を取り出す。
 * @param {object} response response.done イベントの response
 * @returns {"RESPOND"|"BACKCHANNEL"|"WAIT"} 判定結果。読み取れない場合は RESPOND（後輩として返事をしようとした場合が多いため）
 */
function parseTurnDecision(response) {
  const item = response.output?.[0];
  try {
    const decision = JSON.parse(item?.arguments ?? "{}").decision;
    if (["RESPOND", "BACKCHANNEL", "WAIT"].includes(decision)) return decision;
  } catch {
    // 引数が JSON でない場合は下のフォールバックへ
  }
  return "RESPOND";
}

/**
 * ターン判定の結果に応じて、応答・相づち・待機を行う。
 * @param {object} response response.done イベントの response
 */
function handleTurnJudge(response) {
  // 新しい発話の判定が後から依頼されていれば、この結果は使わない
  if (Number(response.metadata.seq) !== state.judgeSeq) return;
  // ユーザが話し続けている・AI がすでに話している場合は何もしない
  if (state.userSpeaking || state.aiSpeaking || state.responseActive) {
    console.debug("ターン判定を見送り:", { user: state.userSpeaking, ai: state.aiSpeaking, active: state.responseActive });
    return;
  }

  // 判定結果に応じて応答・相づち・待機
  const decision = parseTurnDecision(response);
  console.debug("ターン判定:", decision);
  if (decision === "RESPOND") {
    requestResponse("respond");
  } else if (decision === "BACKCHANNEL") {
    requestResponse("backchannel", state.options.turn_taking.backchannel_prompt);
  }
  // WAIT の場合は何も言わずに待つ（沈黙が続けば checkSilence で話しかける）
}

/**
 * 誰も話さない状態が一定時間続いたら、AI から話しかける（1 回の沈黙につき 1 回まで）。
 */
function checkSilence() {
  // 応答の要求がエラー等で失敗したまま残っていたら解除する
  if (state.responseActive && !state.aiSpeaking && performance.now() - state.responseRequestedAt > RESPONSE_TIMEOUT_MS) {
    state.responseActive = false;
  }
  if (state.userSpeaking || state.aiSpeaking || state.responseActive || state.proactiveDone) return;
  const silenceMs = state.options.turn_taking.silence_sec * 1000;
  if (performance.now() - state.lastActivityAt < silenceMs) return;
  state.proactiveDone = true;

  // 会話が締めの段階（まとめ / 終了）なら、一度だけ締めの一言を言わせ、以降は話しかけない
  const tt = state.options.turn_taking;
  if (tt.closing_stages.includes(state.stage)) {
    if (state.closingDone) return;
    state.closingDone = true;
    requestResponse("closing", tt.closing_prompt);
    return;
  }
  // まだ誰も話していなければ、会話の始まりにふさわしい一言（挨拶など）にする
  if (state.turns.size === 0) {
    requestResponse("proactive", tt.idle_opening_prompt);
    return;
  }
  // それ以外は、感情推定で判定した「次にすべきこと」を添えて話しかけさせる
  const hint = state.nextAction ? `\n（参考: 今あなたが次にすべきこと: ${state.nextAction}）` : "";
  requestResponse("proactive", tt.proactive_prompt + hint);
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
 * 割り込みを記録する（感情推定・レポート用。ユーザが萎縮しないよう会話ログには印を付けない）。
 * @param {string} itemId 割り込んで話し始めたユーザ発話の item_id
 */
function markInterrupted(itemId) {
  state.interruptCount += 1;
  state.pendingInterrupt = true;
  state.lastInterruptItemId = itemId;
  $("interrupt-count").textContent = state.interruptCount;
}

/**
 * 直前の割り込みを取り消す。
 * AI が話し終えた直後に話し始めた場合、再生終了の通知が遅れて割り込みと誤判定されることがある。
 * その場合は Azure 側の音声の切り詰めが失敗するので、そのエラーを受けて取り消す。
 */
function cancelLastInterrupt() {
  const itemId = state.lastInterruptItemId;
  if (!itemId) return;
  state.lastInterruptItemId = null;

  // 回数を戻す
  state.interruptCount = Math.max(0, state.interruptCount - 1);
  $("interrupt-count").textContent = state.interruptCount;

  // 発話がまだ確定前なら確定時の印を、確定済みなら発話の印を外す（感情推定は文字起こし確定後に行うため間に合う）
  if (state.turns.has(itemId)) state.turns.get(itemId).interrupted = false;
  else state.pendingInterrupt = false;

  // 実際は AI が話し終えた直後に話し始めているので、間は 0 秒（即答）として扱う
  const sp = state.speech.get(itemId);
  if (sp && sp.latency === null) sp.latency = 0;
}

/**
 * 「AI の話し終わりと同時に話し始めた」ことによる、Azure 側の音声切り詰めの失敗エラーかを判定する。
 * 例: "Audio content of 5400ms is already shorter than 5740ms"
 * @param {object} error error イベントの error
 * @returns {boolean}
 */
function isTruncateAfterEndError(error) {
  return /already shorter than/i.test(error?.message ?? "");
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
  state.logPinned = true;
  state.turns.clear();
  state.speech.clear();
  state.responsePurposes.clear();
  state.judgeSeq = 0;
  state.proactiveDone = false;
  state.stage = "導入";
  state.nextAction = "";
  state.closingDone = false;
  state.itemSeq = 0;
  state.directiveItemId = state.promptItemId = null;
  state.userSpeaking = state.aiSpeaking = state.responseActive = false;
  state.aiStoppedAt = null;
  state.baseline = { volume: [], pitch: [] };
  state.lastAiItemId = null;
  state.pendingInterrupt = false;
  state.lastInterruptItemId = null;
  state.interruptCount = 0;
  $("interrupt-count").textContent = "0";
  $("timer").textContent = "00:00";
}

// 最下部からこの距離（px）以内なら「最新を表示中」とみなす
const LOG_BOTTOM_THRESHOLD = 40;

/**
 * 会話ログが最新（最下部）を表示中なら、最下部までスクロールする。
 * ユーザが上にスクロールして過去のログを見ているときは位置を変えない。
 */
function scrollLog() {
  if (!state.logPinned) return;
  const log = $("log");
  log.scrollTop = log.scrollHeight;
}

/**
 * 会話ログのスクロール追従を設定する。
 * - ユーザのスクロール操作で「最下部に追従するか」を切り替える
 * - 文字起こしの追記や評価ラベルの追加など、ログの中身が変わるたびに追従中なら最下部へ移動する
 */
function initLogAutoScroll() {
  const log = $("log");
  log.addEventListener("scroll", () => {
    state.logPinned = log.scrollHeight - log.scrollTop - log.clientHeight <= LOG_BOTTOM_THRESHOLD;
  });
  new MutationObserver(scrollLog).observe(log, { childList: true, subtree: true, characterData: true });
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
  updateExpression(result.emotion, result.delta);
  pushChartPoint(target.text, result);
  annotateTurn(target, result);

  // 会話の進行段階を記録（締めの段階以外に戻ったら、締めの一言をまた言えるようにする）
  state.stage = result.stage;
  state.nextAction = result.next_action;
  if (!state.options.turn_taking.closing_stages.includes(result.stage)) state.closingDone = false;

  // 感情と進行状況を AI の態度に反映（次の応答から効く振る舞いの指示を差し込み、前回の指示は削除して最新の 1 件だけ残す）
  deleteSystemItem(state.directiveItemId);
  state.directiveItemId = addSystemItem("dir", result.directive);
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
  updateExpression(state.emotion, null);

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
      <span class="meter-value"></span>
      <span class="meter-delta"></span>`;
    row.querySelector(".meter-key").style.background = SERIES_COLORS[i];
    row.querySelector(".meter-name").append(axis.label);
    row.querySelector(".meter-value").textContent = emotion[axis.id];
    row.querySelector(".meter-delta").textContent = delta ? (d > 0 ? `▲${d}` : d < 0 ? `▼${-d}` : "±0") : "";
    box.appendChild(row);
  });
}

// ===================================================================
// 相手の表情（カメラ映像風の表示）
// ===================================================================

// 表情画像の種類（image/{man|woman}_{表情}.png）
const EXPRESSIONS = ["smile", "laugh", "think", "surprise", "angry"];
// 性別 ID → 画像ファイル名の接頭辞
const FACE_PREFIX = { male: "man", female: "woman" };

/**
 * 感情値から表情を選ぶ。強い感情ほど優先する（怒り > 動揺 > 困惑・萎縮 > 大喜び > 穏やか）。
 * @param {object} emotion 感情値 { relief, tension, motivation, trust }
 * @param {object|null} delta 直前の発話による変化量
 * @returns {string} 表情（EXPRESSIONS のいずれか）
 */
function expressionFor(emotion, delta) {
  const { relief, tension, motivation, trust } = emotion;
  // 不満・反発: 安心感も信頼感も大きく損なわれている
  if (relief <= 25 && trust <= 25) return "angry";
  // 動揺・焦り: 1 回の発言で緊張が急に高まった、または強く萎縮している
  if ((delta?.tension ?? 0) >= 15 || tension >= 80) return "surprise";
  // 困惑・緊張・落ち込み
  if (tension >= 60 || motivation <= 35 || relief <= 35) return "think";
  // 安心して前向き
  if (relief >= 70 && motivation >= 65 && tension <= 35) return "laugh";
  return "smile";
}

/**
 * 表情画像を切り替える（変わったときだけ軽いアニメーションを付ける）。
 * @param {object} emotion 感情値
 * @param {object|null} delta 直前の発話による変化量
 */
function updateExpression(emotion, delta) {
  const img = $("face");
  const src = faceUrl(expressionFor(emotion, delta));
  if (img.getAttribute("src") === src) return;
  img.src = src;
  img.classList.remove("changed");
  void img.offsetWidth; // アニメーションを再生し直すためにリフローさせる
  img.classList.add("changed");
}

/**
 * 選択中の性別の表情画像の URL を返す。
 * @param {string} expression 表情
 * @returns {string}
 */
function faceUrl(expression) {
  return `/images/${FACE_PREFIX[$("gender").value]}_${expression}.png`;
}

/**
 * 表情の切り替え時にちらつかないよう、選択中の性別の画像を先読みする。
 */
function preloadFaces() {
  for (const expression of EXPRESSIONS) new Image().src = faceUrl(expression);
}

/**
 * 相手（AI）の音声のオン/オフを切り替える。
 * 再生だけを止めるので、会話（文字起こし・感情推定・話者交代）はそのまま続く。
 */
function toggleAiAudio() {
  const audio = $("remote-audio");
  audio.muted = !audio.muted;
  const tile = $("video-tile");
  tile.classList.toggle("muted", audio.muted);
  tile.setAttribute("aria-pressed", String(audio.muted));
  $("video-audio").textContent = audio.muted ? "🔇 音声オフ" : "🔊 音声オン";
}

/**
 * 接続中かどうかでカメラ映像の見た目を切り替える（未接続時は薄く表示）。
 * @param {boolean} online 接続中かどうか
 */
function setVideoOnline(online) {
  $("video-tile").classList.toggle("offline", !online);
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
  state.lastReport = null;
  $("report-download").disabled = true;
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

    // ダウンロード用に、レポートと会話の情報を保持
    state.lastReport = { report, ctx: buildReportContext(initial) };
    $("report-download").disabled = false;
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
  body.appendChild(el("p", "report-meta", "※緊張は低いほど良い状態です。"));

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

/**
 * ダウンロード用に、会話の条件と評価付きの会話ログをまとめる。
 * @param {object} initial 開始時の感情値
 * @returns {object} レポートの Markdown 化に必要な情報
 */
function buildReportContext(initial) {
  const gender = state.options.genders.find((g) => g.id === $("gender").value);
  return {
    startedAt: new Date(state.startedAt),
    personName: currentPersona().name,
    shortName: personShortName(),
    genderLabel: gender.label,
    scenario: currentScenario(),
    duration: $("timer").textContent,
    interruptCount: state.interruptCount,
    initial,
    final: { ...state.emotion },
    turns: [...state.turns.values()].filter((t) => t.final && !t.pending),
  };
}

/**
 * レポートと会話ログを Markdown 形式の文字列にする。
 * @param {{report: object, ctx: object}} data state.lastReport
 * @returns {string} Markdown
 */
function buildReportMarkdown({ report, ctx }) {
  const axes = state.options.emotion_axes;
  const lines = [];
  const signed = (d) => (d > 0 ? `+${d}` : String(d));

  // 見出しと会話の条件
  lines.push("# 振り返りレポート", "");
  lines.push(`- 日時: ${formatDateTime(ctx.startedAt)}`);
  lines.push(`- 会話相手: ${ctx.personName}（${ctx.genderLabel}）`);
  lines.push(`- シチュエーション: ${ctx.scenario.category} / ${ctx.scenario.title}`);
  lines.push(`- 状況: ${ctx.scenario.situation}`);
  lines.push(`- 会話時間: ${ctx.duration}　割り込み: ${ctx.interruptCount} 回`, "");

  // 総評
  lines.push("## 総評", "", report.summary, "");

  // 気持ちの変化
  lines.push(`## ${ctx.shortName}の気持ちの変化`, "");
  lines.push("| | 開始 | 終了 | 変化 |", "|---|---:|---:|---:|");
  for (const axis of axes) {
    const d = ctx.final[axis.id] - ctx.initial[axis.id];
    lines.push(`| ${axis.label} | ${ctx.initial[axis.id]} | ${ctx.final[axis.id]} | ${signed(d)} |`);
  }
  lines.push("", "※緊張は低いほど良い状態です。", "");

  // 相手から見た印象
  lines.push(`## ${ctx.shortName}から見たあなた`, "", `> 「${report.impression}」`, "");

  // 良かったところ
  lines.push("## 良かったところ", "");
  for (const item of report.good_points) lines.push(`- **「${item.quote}」**`, `  - ${item.comment}`);
  lines.push("");

  // もっと良くできるところ
  if (report.improvements.length) {
    lines.push("## もっと良くできるところ", "");
    report.improvements.forEach((item, i) => {
      lines.push(`### ${i + 1}. 「${item.quote}」`, "", `- 伝わり方: ${item.problem}`, `- 言い換え例: 「${item.better}」`, "");
    });
  }

  // 次回意識すること
  lines.push("## 次回意識すること", "", report.next_focus, "");

  // 会話ログ（あなたの発言には評価を添える）
  lines.push("## 会話ログ", "");
  for (const turn of ctx.turns) {
    if (turn.role === "ai") {
      lines.push(`**${ctx.shortName}**${turn.backchannel ? "（相づち）" : ""}: ${turn.text}`, "");
      continue;
    }
    lines.push(`**あなた**: ${turn.text}`, "");
    const ev = turn.evaluation;
    if (!ev) continue;
    lines.push(`- 気持ちの変化: ${axes.map((a) => `${a.label} ${signed(ev.delta[a.id])}`).join(" / ")}`);
    if (ev.voice_labels.length) lines.push(`- 声: ${ev.voice_labels.map((lb) => `${lb.name} ${lb.label}`).join(" / ")}`);
    if (ev.good_points.length) lines.push(`- 良かった点: ${ev.good_points.join(" / ")}`);
    if (ev.bad_points.length) lines.push(`- 改善点: ${ev.bad_points.join(" / ")}`);
    lines.push("");
  }
  return lines.join("\n");
}

/**
 * レポートを Markdown ファイルとしてダウンロードする。
 */
function downloadReport() {
  if (!state.lastReport) return;
  const { ctx } = state.lastReport;

  // ファイル名: report_YYYYMMDD_HHMM_シナリオ名.md
  const d = ctx.startedAt;
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`;
  const filename = `report_${stamp}_${ctx.scenario.title}.md`;

  // Blob を作ってリンク経由で保存
  const blob = new Blob([buildReportMarkdown(state.lastReport)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function formatDateTime(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
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
  // 相手が話している間は、カメラ映像の枠を光らせる
  if (id === "ai-indicator") $("video-tile").classList.toggle("speaking", active);
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
  for (const id of ["persona", "gender", "scenario"]) $(id).disabled = running;
  setVideoOnline(running);
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
// モーダルの外側（背景）をクリックしたら閉じる
$("report-dialog").addEventListener("click", (e) => {
  const rect = e.currentTarget.getBoundingClientRect();
  const inside = e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
  if (!inside) e.currentTarget.close();
});
$("report-download").onclick = downloadReport;
// カメラ映像風のエリアをクリック（または Enter / Space）で相手の音声をオン/オフ
$("video-tile").onclick = toggleAiAudio;
$("video-tile").onkeydown = (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    toggleAiAudio();
  }
};
initLogAutoScroll();
loadOptions();
