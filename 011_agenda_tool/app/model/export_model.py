"""学習済みモデルと推論用コードを、チャット内容自動リマインドサービス(011_nightrain)にコピーする。

アジェンダ作成ツール(011_agenda_tool)とチャット内容自動リマインドサービス(011_nightrain)は、
投稿のフィルタに同じモデルを使う。モデルの学習・検証はこのフォルダ(011_agenda_tool/app/model/)
でのみ行い、学習したモデルをこのスクリプトで 011_nightrain に反映する。

実行方法: 011_agenda_tool ディレクトリで
    python -m app.model.export_model
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
# コピー先: 011_agenda_tool と同じ階層にある 011_nightrain の app/model/
DEST_DIR = MODEL_DIR.parents[2] / "011_nightrain" / "app" / "model"

# コピーするファイル(学習済みモデル本体と、モデルの読み込み・推論に必要なコード)
# preprocess.py はモデル内部から参照されるため、モデルと必ずセットでコピーする
EXPORT_FILES = ["reminder_classifier.joblib", "predict.py", "preprocess.py"]


def export_model() -> None:
    """
    EXPORT_FILES を 011_nightrain/app/model/ にコピーし、コピー結果を表示する

    Args
    -----------------
    - なし

    Returns
    -----------------
    - None

    """
    # コピー先のプロジェクト(011_nightrain/app)が無い場合は、誤った場所に作らないよう中止する
    if not DEST_DIR.parent.exists():
        raise SystemExit(f"コピー先のプロジェクトが見つかりません: {DEST_DIR.parent}")
    DEST_DIR.mkdir(exist_ok=True)

    for name in EXPORT_FILES:
        src = MODEL_DIR / name
        if not src.exists():
            raise SystemExit(f"{name} がありません。先に python -m app.model.train_model を実行してください。")
        dst = DEST_DIR / name

        # 内容が同じ場合はコピーしない(変更の有無がわかるように表示する)
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            print(f"変更なし: {name}")
            continue
        shutil.copy2(src, dst)
        print(f"コピーしました: {name} -> {dst}")

    print("011_nightrain に反映するには、build_package.ps1 で再ビルドして再デプロイしてください。")


if __name__ == "__main__":
    export_model()
