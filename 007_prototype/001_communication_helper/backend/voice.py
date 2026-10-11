"""ブラウザで計測した声の特徴量を、評価用 LLM と画面向けのラベルに変換するモジュール。

数値の閾値判定はルールベースで行い、LLM には「ラベル + 数値」を参考情報として渡す。
（LLM に生の数値だけを渡すより判断が安定するため）
"""

from pydantic import BaseModel

# 短すぎる発話は区間前後の余白の影響が大きく、話速・抑揚の推定が不安定なため判定しない（秒）
MIN_DURATION_FOR_PROSODY = 2.0


class VoiceFeatures(BaseModel):
    """1 発話分の声の特徴量（ブラウザで計測）。値が取れなかった項目は None。"""

    duration_sec: float | None = None  # 発話区間の長さ
    speech_rate: float | None = None  # 話速（モーラ/秒の概算）
    volume_db: float | None = None  # 有声部分の平均音量（dBFS）
    volume_vs_baseline_db: float | None = None  # これまでの発話の平均音量との差
    pitch_hz: float | None = None  # 声の高さの中央値
    pitch_vs_baseline_st: float | None = None  # これまでの発話の声の高さとの差（半音）
    pitch_variation_st: float | None = None  # 抑揚の大きさ（声の高さの標準偏差、半音）
    response_latency_sec: float | None = None  # 相手が話し終えてから話し始めるまでの間


class VoiceLabel(BaseModel):
    """画面・LLM 向けの判定結果 1 項目。"""

    name: str  # 項目名（話速 / 声量 など）
    label: str  # 判定（速い / 普段どおり など）
    value: str  # 数値の表示用文字列
    notable: bool  # 印象に影響しうる特徴か（画面で強調表示する）


def _label_rate(rate: float) -> tuple[str, bool]:
    """話速（モーラ/秒）を判定する。日本語の会話の標準はおよそ 6〜8 モーラ/秒。"""
    if rate >= 10:
        return "かなり速い", True
    if rate >= 8.5:
        return "速い", True
    if rate < 4.5:
        return "かなりゆっくり", True
    if rate < 5.5:
        return "ゆっくり", False
    return "普通", False


def _label_volume(diff_db: float) -> tuple[str, bool]:
    """これまでの発話と比べた声量の差を判定する。"""
    if diff_db >= 6:
        return "かなり大きい", True
    if diff_db >= 3:
        return "大きめ", True
    if diff_db <= -6:
        return "かなり小さい", True
    if diff_db <= -3:
        return "小さめ", False
    return "普段どおり", False


def _label_pitch(diff_st: float) -> tuple[str, bool]:
    """これまでの発話と比べた声の高さの差を判定する。"""
    if diff_st >= 2.5:
        return "高め（感情的）", True
    if diff_st <= -2.5:
        return "低め", True
    return "普段どおり", False


def _label_variation(std_st: float) -> tuple[str, bool]:
    """抑揚の大きさを判定する。"""
    if std_st < 1.5:
        return "平坦（抑揚が少ない）", True
    if std_st > 4.5:
        return "大きい", False
    return "普通", False


def _label_latency(sec: float) -> tuple[str, bool]:
    """相手が話し終えてから話し始めるまでの間を判定する。"""
    if sec >= 6:
        return "かなり長い沈黙", True
    if sec >= 3:
        return "長め", True
    if sec < 0.5:
        return "即答", False
    return "普通", False


def build_voice_labels(f: VoiceFeatures, interrupted: bool) -> list[VoiceLabel]:
    """声の特徴量を判定ラベルに変換する。

    Args:
        f: ブラウザで計測した特徴量。
        interrupted: 相手の発話に割り込んで話し始めたか。

    Returns:
        list[VoiceLabel]: 判定できた項目のラベル一覧。
    """
    labels: list[VoiceLabel] = []
    long_enough = (f.duration_sec or 0) >= MIN_DURATION_FOR_PROSODY

    # 間（割り込みの場合は間ではなく割り込みとして扱う）
    if interrupted:
        labels.append(VoiceLabel(name="間", label="相手の発話に割り込み", value="-", notable=True))
    elif f.response_latency_sec is not None:
        label, notable = _label_latency(f.response_latency_sec)
        labels.append(VoiceLabel(name="間", label=label, value=f"{f.response_latency_sec:.1f}秒", notable=notable))

    # 話速
    if f.speech_rate is not None and long_enough:
        label, notable = _label_rate(f.speech_rate)
        labels.append(VoiceLabel(name="話速", label=label, value=f"{f.speech_rate:.1f}モーラ/秒", notable=notable))

    # 声量（初回発話は比較対象がないため数値のみ）
    if f.volume_vs_baseline_db is not None:
        label, notable = _label_volume(f.volume_vs_baseline_db)
        labels.append(VoiceLabel(name="声量", label=label, value=f"{f.volume_vs_baseline_db:+.1f}dB", notable=notable))

    # 声の高さ
    if f.pitch_vs_baseline_st is not None:
        label, notable = _label_pitch(f.pitch_vs_baseline_st)
        labels.append(VoiceLabel(name="声の高さ", label=label, value=f"{f.pitch_vs_baseline_st:+.1f}半音", notable=notable))

    # 抑揚
    if f.pitch_variation_st is not None and long_enough:
        label, notable = _label_variation(f.pitch_variation_st)
        labels.append(VoiceLabel(name="抑揚", label=label, value=f"{f.pitch_variation_st:.1f}半音", notable=notable))

    return labels


def format_for_prompt(labels: list[VoiceLabel]) -> str:
    """判定ラベルを評価用プロンプトに埋め込む文字列にする。

    Args:
        labels: build_voice_labels の結果。

    Returns:
        str: 「- 項目: 判定（数値）」形式の箇条書き。項目がなければ「（計測なし）」。
    """
    if not labels:
        return "（計測なし）"
    return "\n".join(f"- {lb.name}: {lb.label}（{lb.value}）" for lb in labels)
