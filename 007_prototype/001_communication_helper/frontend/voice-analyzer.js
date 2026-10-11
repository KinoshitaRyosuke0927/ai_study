// マイク音声から声量・声の高さを計測するクラス（Web Audio API）
// 40ms ごとに音量（dBFS）と基本周波数（F0）を記録し、発話区間ごとに集計する。
// 音声データ自体はサーバに送らず、集計した数値だけを感情推定に使う。

const FRAME_INTERVAL_MS = 40;
const VOICED_DB_THRESHOLD = -50; // これより大きい音量のフレームを「声あり」とみなす
const PITCH_MIN_HZ = 70;
const PITCH_MAX_HZ = 400;
const PITCH_CLARITY_THRESHOLD = 0.6; // 自己相関のピークがこれ未満なら F0 なし（無声音・雑音）
const FRAME_RETENTION_MS = 60_000; // 保持するフレームの期間

class VoiceAnalyzer {
  /**
   * @param {MediaStream} stream マイクの MediaStream
   */
  constructor(stream) {
    // マイク → AnalyserNode（スピーカーには繋がない）
    this.ctx = new AudioContext();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.ctx.createMediaStreamSource(stream).connect(this.analyser);
    this.buf = new Float32Array(this.analyser.fftSize);
    this.frames = []; // { t, db, f0 }

    // 一定間隔でフレームを記録
    this.timerId = setInterval(() => this.sample(), FRAME_INTERVAL_MS);
  }

  /**
   * 現在のフレームの音量と F0 を記録する。
   */
  sample() {
    // 音量（RMS → dBFS）
    this.analyser.getFloatTimeDomainData(this.buf);
    let sum = 0;
    for (const v of this.buf) sum += v * v;
    const db = 10 * Math.log10(sum / this.buf.length + 1e-12);

    // 声がありそうなフレームだけ F0 を推定（計算量削減）
    const f0 = db > VOICED_DB_THRESHOLD ? detectPitch(this.buf, this.ctx.sampleRate) : null;

    // 記録と古いフレームの破棄
    const t = performance.now();
    this.frames.push({ t, db, f0 });
    while (this.frames.length && this.frames[0].t < t - FRAME_RETENTION_MS) this.frames.shift();
  }

  /**
   * 指定区間の声の特徴を集計する。
   * @param {number} from 区間の開始（performance.now() 基準）
   * @param {number} to 区間の終了（performance.now() 基準）
   * @returns {{voicedSec: number, volumeDb: number|null, pitchHz: number|null, pitchVariationSt: number|null}}
   */
  summarize(from, to) {
    // 区間内の「声あり」フレームを抽出
    const voiced = this.frames.filter((f) => f.t >= from && f.t <= to && f.db > VOICED_DB_THRESHOLD);
    const voicedSec = (voiced.length * FRAME_INTERVAL_MS) / 1000;
    if (!voiced.length) return { voicedSec, volumeDb: null, pitchHz: null, pitchVariationSt: null };

    // 平均音量（エネルギー平均を dB に戻す）
    const meanPower = voiced.reduce((acc, f) => acc + 10 ** (f.db / 10), 0) / voiced.length;
    const volumeDb = 10 * Math.log10(meanPower);

    // 声の高さの中央値と、抑揚（半音単位の標準偏差）
    const f0s = voiced.map((f) => f.f0).filter((v) => v);
    if (f0s.length < 5) return { voicedSec, volumeDb, pitchHz: null, pitchVariationSt: null };
    const pitchHz = median(f0s);
    const st = f0s.map((v) => 12 * Math.log2(v / pitchHz));
    const mean = st.reduce((a, b) => a + b, 0) / st.length;
    const pitchVariationSt = Math.sqrt(st.reduce((a, b) => a + (b - mean) ** 2, 0) / st.length);

    return { voicedSec, volumeDb, pitchHz, pitchVariationSt };
  }

  close() {
    clearInterval(this.timerId);
    this.ctx.close();
  }
}

/**
 * 正規化自己相関で基本周波数（F0）を推定する。
 * @param {Float32Array} buf 時間領域の波形
 * @param {number} sampleRate サンプリング周波数
 * @returns {number|null} F0（Hz）。推定できない場合は null
 */
function detectPitch(buf, sampleRate) {
  // 計算量削減のため 2 サンプルに 1 つに間引く
  const x = new Float32Array(buf.length >> 1);
  for (let i = 0; i < x.length; i++) x[i] = buf[i * 2];
  const sr = sampleRate / 2;
  const minLag = Math.floor(sr / PITCH_MAX_HZ);
  const maxLag = Math.min(Math.floor(sr / PITCH_MIN_HZ), x.length - 1);

  // 各ラグの正規化自己相関を計算
  const corrs = new Float32Array(maxLag + 1);
  let maxCorr = 0;
  for (let lag = minLag; lag <= maxLag; lag++) {
    let num = 0, e1 = 0, e2 = 0;
    for (let i = 0; i + lag < x.length; i++) {
      num += x[i] * x[i + lag];
      e1 += x[i] * x[i];
      e2 += x[i + lag] * x[i + lag];
    }
    corrs[lag] = num / Math.sqrt(e1 * e2 + 1e-12);
    maxCorr = Math.max(maxCorr, corrs[lag]);
  }
  if (maxCorr < PITCH_CLARITY_THRESHOLD) return null;

  // 最大値の 90% 以上ある最初の山を採用（周期の整数倍のラグを選ぶオクターブ誤りを防ぐ）
  for (let lag = minLag + 1; lag < maxLag; lag++) {
    if (corrs[lag] >= maxCorr * 0.9 && corrs[lag] >= corrs[lag - 1] && corrs[lag] >= corrs[lag + 1]) {
      return sr / lag;
    }
  }
  return null;
}

/**
 * 日本語テキストのモーラ数を概算する（話速の計算用）。
 * かな = 1（小さいゃゅょ等は 0）、長音・促音 = 1、漢字 = 1.7、数字 = 1.5、英字 = 0.5 として数える。
 * @param {string} text 文字起こし
 * @returns {number} モーラ数の概算
 */
function estimateMora(text) {
  let mora = 0;
  for (const ch of text) {
    if (/[ぁぃぅぇぉゃゅょゎァィゥェォャュョヮ]/.test(ch)) continue;
    if (/[぀-ゟ゠-ヿ]/.test(ch)) mora += 1;
    else if (/[一-鿿]/.test(ch)) mora += 1.7;
    else if (/[0-9０-９]/.test(ch)) mora += 1.5;
    else if (/[a-zA-Zａ-ｚＡ-Ｚ]/.test(ch)) mora += 0.5;
  }
  return mora;
}

function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
