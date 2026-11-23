# -*- mode: python ; coding: utf-8 -*-
# スケジュール確認ツールを exe にするための PyInstaller の設定。
# 使い方(004_schedule_tool フォルダで実行):
#     pyinstaller schedule_tool.spec --noconfirm
# 出力: dist\schedule_tool\schedule_tool.exe(_internal フォルダとセットで配布する)

from PyInstaller.utils.hooks import collect_submodules

# 同梱するファイル: 画面のファイル
datas = [("app/static", "app/static")]

# uvicorn は内部で動的に読み込むモジュールがあるため、すべてを含める
# scikit-learn も内部で動的に読み込むモジュールがあるため含める(業務状況の学習・推定で使う)
hiddenimports = collect_submodules("uvicorn") + ["app.main", "sklearn._cyutility"]

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 使わない大きなパッケージは含めない
    excludes=["tkinter", "matplotlib", "pandas", "torch", "openai"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="schedule_tool",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="schedule_tool",
)
