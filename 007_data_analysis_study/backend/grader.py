# -*- coding: utf-8 -*-
"""学習者のコード実行と自動採点（プロトタイプ用）

- OS の python3 をサブプロセスで実行し、標準出力を期待値と照合する
- データファイル（CSV等）は static/data/ から一時作業ディレクトリへコピーして渡す
- pandas / matplotlib はシステム Python に導入済みの前提

セキュリティ上の注意:
この実装はプロトタイプ専用。学習者が送ったコードをそのまま実行するため、
インターネット公開時は Docker / nsjail / gVisor 等で隔離してください（README参照）。
"""

import os
import shutil
import subprocess
import tempfile
import time
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # プロジェクト直下
DATA_DIR = os.path.join(BASE_DIR, "static", "data")
MEDIA_DIR = os.path.join(BASE_DIR, "static", "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

PYTHON_ENV = os.environ.get("DS_PYTHON", "")


def _resolve_python():
    """pandas / matplotlib が使える Python を探す（DS_PYTHON があれば優先）"""
    if PYTHON_ENV:
        return PYTHON_ENV
    candidates = ["/usr/bin/python3", "/usr/local/bin/python3", "python3"]
    for c in candidates:
        try:
            r = subprocess.run(
                [c, "-c", "import pandas, matplotlib"],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return "python3"


PYTHON = _resolve_python()
TIMEOUT_SEC = float(os.environ.get("DS_TIMEOUT_SEC", "10"))

# 可視化ドリル用：コード末尾に自動追記して図が出来ているか確認する
VIZ_APPEND = """
try:
    import matplotlib.pyplot as _plt
    if _plt.get_fignums():
        _plt.savefig("chart.png", bbox_inches="tight")
except Exception:
    pass
"""


def build_full_code(starter: str, student_code: str) -> str:
    """ドリルの雛形の ____ を学習者のコードで置き換える"""
    return starter.replace("____", student_code)


def run_code(code: str, data_files=None, save_chart: bool = False,
             drill_id: str = "drill") -> dict:
    """一時ディレクトリでコードを実行し、実行結果と（あれば）チャートを返す"""
    started = time.time()
    chart_filename = None
    with tempfile.TemporaryDirectory() as td:
        # データファイルを渡す
        if data_files:
            for name in data_files:
                src = os.path.join(DATA_DIR, name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(td, name))
        path = os.path.join(td, "main.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            proc = subprocess.run(
                [PYTHON, "-B", path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SEC,
                cwd=td,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg"},
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - started) * 1000)
            return {
                "ok": False, "returncode": None, "stdout": "", "chart_url": None,
                "elapsed_ms": elapsed,
                "stderr": f"実行が{TIMEOUT_SEC:.0f}秒を超えました。for の範囲やデータ量を確認してください。",
            }
        elapsed = int((time.time() - started) * 1000)
        if save_chart and os.path.exists(os.path.join(td, "chart.png")):
            chart_filename = f"{drill_id}-{uuid.uuid4().hex[:8]}.png"
            shutil.copy2(
                os.path.join(td, "chart.png"),
                os.path.join(MEDIA_DIR, chart_filename),
            )
        return {
            "ok": True,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed_ms": elapsed,
            "chart_url": f"/media/{chart_filename}" if chart_filename else None,
        }


def _normalize(text: str) -> list:
    """途中の空行を除き、行末空白を落として比較しやすい形にする"""
    return [ln.rstrip() for ln in (text or "").splitlines() if ln.strip() != ""]


def _base_return(result: dict):
    return {
        "ok": result["ok"], "returncode": result.get("returncode"),
        "stdout": result["stdout"], "stderr": result["stderr"],
        "elapsed_ms": result["elapsed_ms"], "chart_url": result.get("chart_url"),
    }


def grade_code_gap(starter: str, student_code: str, expected: list,
                   data_files=None) -> dict:
    """穴埋め → 実行 → 標準出力照合で採点"""
    code = build_full_code(starter, student_code)
    result = run_code(code, data_files=data_files)
    got = result["stdout"]
    base = _base_return(result)
    base["expected"] = "\n".join(expected)
    base["got"] = got.rstrip("\n")

    if not result["ok"]:
        return {**base, "passed": False, "kind": "error",
                "message": "実行が完了しませんでした（下の実行ログを確認してください）。"}
    if result["returncode"] != 0:
        return {**base, "passed": False, "kind": "error",
                "message": "コードでエラーが発生しました（下の実行ログを確認してください）。"}
    passed = _normalize(got) == _normalize("\n".join(expected))
    return {
        **base, "passed": passed,
        "kind": "match" if passed else "mismatch",
        "message": "正解です！期待した出力と一致しました。"
        if passed else "出力が期待値と一致しません。下の「期待される出力」と見比べてみましょう。",
    }


def grade_code_check(starter: str, student_code: str, data_files=None,
                     drill_id: str = "drill") -> dict:
    """可視化等：エラーなく実行できたら合格（図ができていれば chart_url を返す）"""
    code = build_full_code(starter, student_code) + VIZ_APPEND
    result = run_code(code, data_files=data_files, save_chart=True, drill_id=drill_id)
    base = _base_return(result)
    if not result["ok"]:
        return {**base, "passed": False, "kind": "error",
                "message": "実行が完了しませんでした（下の実行ログを確認してください）。"}
    if result["returncode"] != 0:
        return {**base, "passed": False, "kind": "error",
                "message": "コードでエラーが発生しました。下の実行ログを確認して修正しましょう。"}
    return {**base, "passed": True, "kind": "run_ok",
            "message": "エラーなく実行できました。右に図が表示されていればOKです。"}
