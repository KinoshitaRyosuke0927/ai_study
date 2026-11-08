# -*- mode: python ; coding: utf-8 -*-
# ヒアリング管理ツールを exe にするための PyInstaller の設定。
# 使い方（003_hearing_tool フォルダで実行）：
#     .venv\Scripts\pyinstaller.exe hearing_tool.spec --noconfirm
# 出力：dist\hearing_tool\hearing_tool.exe（_internal フォルダとセットで配布する）

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 同梱するファイル：画面のファイル、設定の見本、imageio-ffmpeg に含まれる ffmpeg
datas = [
    ("app/static", "app/static"),
    ("config.example.json", "."),
]
datas += collect_data_files("imageio_ffmpeg")

# uvicorn は内部で動的に読み込むモジュールがあるため、すべてを含める
hiddenimports = collect_submodules("uvicorn")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 開発用の取り込みスクリプトや、使わない大きなパッケージは含めない
    excludes=["tools", "tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hearing_tool",
    debug=False,
    strip=False,
    upx=False,
    # 起動の案内と、終了の操作（ウィンドウを閉じる）のため、コンソールを表示する
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="hearing_tool",
)
