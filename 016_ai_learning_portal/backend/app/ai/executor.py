"""AI が作ったコードを、受講画面と同じ Pyodide でサーバ側で実行するモジュール。

実行は Node.js のスクリプト(backend/runner/run.mjs)に任せる。1回の呼び出しで Pyodide を起動し、
データファイルを置いて、複数のコード(タスク)を順に実行して結果を返す。
呼び出し側は CodeRunner の型だけに依存するため、テストでは set_runner で偽の実行環境に差し替えられる。
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.ai.figure_style import MATPLOTLIBRC
from app.config.settings import get_settings

# 実行スクリプトの場所(backend/runner)
RUNNER_DIR = Path(__file__).resolve().parents[2] / "runner"


class RunnerError(Exception):
    """実行環境が使えない、または実行全体が失敗した(タイムアウトなど)。"""


@dataclass
class Task:
    """実行するコード1つ分。同じ ctx のタスクは変数を共有する(受講画面の単元と同じ)。"""

    id: str
    code: str
    ctx: str
    test: str = ""


@dataclass
class TaskResult:
    """コード1つ分の実行結果。"""

    id: str
    output: str = ""  # 標準出力 + 最後の式の値
    error: str | None = None  # 例外のメッセージ
    images: list[str] = field(default_factory=list)  # matplotlib の図(PNG, base64)
    test_passed: bool | None = None  # テストコードの結果(テストなしは None)
    test_message: str | None = None


class CodeRunner(Protocol):
    """コードの実行環境の型。"""

    def run(self, tasks: list[Task], files: dict[str, bytes]) -> dict[str, TaskResult]:
        """
        データファイルを置いて、タスクを順に実行する

        Args
        -----------------
        - tasks: list[Task],                実行するコード
        - files: dict[str, bytes],          作業ディレクトリに置くデータファイル(ファイル名 → 内容)

        Returns
        -----------------
        - results: dict[str, TaskResult],   タスクの ID → 実行結果

        """
        ...


class NodeRunner:
    """Node.js + Pyodide(backend/runner/run.mjs)でコードを実行する。"""

    def __init__(self, node: str, timeout: int) -> None:
        """
        実行環境を生成する

        Args
        -----------------
        - node: str,                        node コマンド
        - timeout: int,                     1回の実行の上限(秒)

        """
        self._node = node
        self._timeout = timeout

    def run(self, tasks: list[Task], files: dict[str, bytes]) -> dict[str, TaskResult]:
        # 入力の JSON を組み立てる(データファイルは base64 で渡す)
        payload = {
            "matplotlibrc": MATPLOTLIBRC,
            "files": [{"name": name, "data": base64.b64encode(data).decode()} for name, data in files.items()],
            "tasks": [{"id": t.id, "ctx": t.ctx, "code": t.code, "test": t.test} for t in tasks],
        }
        # 実行スクリプトを起動し、標準入力で渡して標準出力の JSON を受け取る
        try:
            proc = subprocess.run(
                [self._node, str(RUNNER_DIR / "run.mjs")],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                timeout=self._timeout,
                cwd=RUNNER_DIR,
            )
        except subprocess.TimeoutExpired as e:
            raise RunnerError(f"コードの実行が {self._timeout} 秒を超えたため停止しました(無限ループの可能性があります)") from e
        except OSError as e:
            raise RunnerError(f"コードの実行環境を起動できません: {e}") from e
        if proc.returncode != 0:
            raise RunnerError(f"コードの実行に失敗しました: {proc.stderr.decode('utf-8', 'replace')[-1000:]}")
        # 結果を TaskResult にして返却
        data = json.loads(proc.stdout.decode("utf-8"))
        results: dict[str, TaskResult] = {}
        for r in data["results"]:
            results[r["id"]] = TaskResult(
                id=r["id"],
                output=r.get("output") or "",
                error=r.get("error"),
                images=list(r.get("images") or []),
                test_passed=r.get("test_passed"),
                test_message=r.get("test_message"),
            )
        return results


# テストで差し替えるための実行環境(None なら設定から作る)
_runner: CodeRunner | None = None


def set_runner(runner: CodeRunner | None) -> None:
    """
    実行環境を差し替える(テスト用)

    Args
    -----------------
    - runner: CodeRunner | None,        差し替える実行環境(None で既定に戻す)

    """
    global _runner
    _runner = runner


def get_runner() -> CodeRunner | None:
    """
    実行環境を返す(使えない場合は None。その場合、AI が作ったコードの検証は行わない)

    Returns
    -----------------
    - runner: CodeRunner | None,        実行環境

    """
    # 差し替えられていればそれを使う
    if _runner is not None:
        return _runner
    # 設定で無効、node が無い、または npm install していない場合は使えない
    settings = get_settings()
    if not settings.ai_runner_enabled or shutil.which(settings.ai_runner_node) is None:
        return None
    if not (RUNNER_DIR / "node_modules" / "pyodide").exists():
        return None
    return NodeRunner(settings.ai_runner_node, settings.ai_runner_timeout_seconds)


# データファイルの要約を作るコード(作業ディレクトリの CSV を読み、列・型・欠損・先頭の行を表示する)
_SUMMARY_CODE = '''
import pandas as pd
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
for name in __FILES__:
    print(f"### {name}")
    try:
        df = pd.read_csv(name)
    except Exception as e:
        print(f"(CSV として読めませんでした: {e})")
        continue
    print(f"行数 {len(df)}、列数 {len(df.columns)}")
    info = pd.DataFrame({"型": df.dtypes.astype(str), "欠損": df.isna().sum(), "種類数": df.nunique()})
    print(info.to_string())
    print("先頭の 3 行:")
    print(df.head(3).to_string())
    print()
'''


def summarize_datasets(files: dict[str, bytes]) -> str:
    """
    データファイルの要約(列・型・欠損・先頭の行)を作る(AI に渡して、データに合ったコードを書かせる)

    Args
    -----------------
    - files: dict[str, bytes],          データファイル(ファイル名 → 内容)

    Returns
    -----------------
    - summary: str,                     要約の文章(実行環境が使えなければファイル名だけ)

    """
    # 実行環境が無ければファイル名だけを返す
    runner = get_runner()
    if runner is None or not files:
        return "\n".join(f"### {name}" for name in files)
    # 要約のコードを実行して、出力を返却
    code = _SUMMARY_CODE.replace("__FILES__", repr(sorted(files)))
    result = runner.run([Task(id="summary", code=code, ctx="summary")], files)["summary"]
    return (result.output or result.error or "").strip()[:6000]
