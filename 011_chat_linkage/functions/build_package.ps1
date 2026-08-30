# Azure Functions デプロイ用のステージングディレクトリを作成し、zip化するスクリプト。
#
# 011_chat_linkage/app 配下の共有ソースはPyInstaller配布(exe化)と共通で使っているため、
# functions/ 配下に実体コピーを常設せず、デプロイ時にのみ .build/ へコピーして
# パッケージングする(二重管理を避けるため)。
#
# 使い方: functions ディレクトリ内で `./build_package.ps1` を実行すると
#         functions/.build/ にステージングされ、functions/dist/functions.zip が生成される
#         (既定で依存パッケージを .python_packages 配下に事前同梱=vendoring する)。
#         生成したzipは、Azure Storageの任意のBlobコンテナへアップロードしたうえで、
#         そのBlobを指すSAS URLをFunction Appの WEBSITE_RUN_FROM_PACKAGE アプリ設定に
#         明示的に設定し、Function Appを再起動してデプロイする。
#         手順の詳細・背景は functions/DEPLOYMENT.md を参照。
#
# -SkipVendoring を指定すると、依存パッケージの事前同梱をスキップし、ソースのみの
# 小さいzipを作る(Azure自身のOryxリモートビルドに任せたい場合のみ使用。ただし
# WEBSITE_RUN_FROM_PACKAGEを手動設定するとOryxビルドがスキップされるため、
# このオプションを使う場合は az functionapp deploy にAzure自身へパッケージ管理を
# 任せる必要がある。詳細はDEPLOYMENT.md参照)。

param(
    [switch]$SkipVendoring
)

$ErrorActionPreference = "Stop"

$FunctionsDir = $PSScriptRoot
$RootDir = Split-Path $FunctionsDir -Parent
$BuildDir = Join-Path $FunctionsDir ".build"
$DistDir = Join-Path $FunctionsDir "dist"
$ZipPath = Join-Path $DistDir "functions.zip"

# 1. ステージングディレクトリを作り直す
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir -Confirm:$false
}
New-Item -ItemType Directory -Force $BuildDir | Out-Null

# 2. Functions固有ファイルをコピーする
Copy-Item (Join-Path $FunctionsDir "function_app.py") $BuildDir
Copy-Item (Join-Path $FunctionsDir "host.json") $BuildDir
Copy-Item (Join-Path $FunctionsDir "requirements.txt") $BuildDir
Copy-Item (Join-Path $FunctionsDir ".funcignore") $BuildDir

# 3. 共有ソース(app/)をコピーする(__pycache__は除外)
$AppSrc = Join-Path $RootDir "app"
$AppDst = Join-Path $BuildDir "app"
Copy-Item $AppSrc $AppDst -Recurse
Get-ChildItem $AppDst -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -Confirm:$false

# 画面UI(main.py・static/)はセキュリティ上の理由からAzure上には配置しない(exe配布限定のため)。
# ポーリング側(slash_command_watcher.py以下)はmain.pyを参照しないため、除外しても動作に影響しない。
Remove-Item (Join-Path $AppDst "main.py") -Force
Remove-Item (Join-Path $AppDst "static") -Recurse -Force

# 学習済みモデル(数百MB)をデプロイパッケージに含めるとAzure Functionsのデプロイに失敗するため、
# パッケージには含めない。Blob Storageの models コンテナに配置し、
# app/model/predict.py が初回起動時のみダウンロードしてMODEL_CACHE_DIR配下にキャッシュする。
Remove-Item (Join-Path $AppDst "model\reminder_classifier") -Recurse -Force
Remove-Item (Join-Path $AppDst "model\train_data") -Recurse -Force

# 4. settings_loader.load_settings()が非frozen時に参照するパス(app/の親)に settings.ini・agenda_template.txt を配置する
Copy-Item (Join-Path $RootDir "settings.ini") $BuildDir
Copy-Item (Join-Path $RootDir "agenda_template.txt") $BuildDir

if (-not $SkipVendoring) {
    # 4.5. 依存パッケージ(requirements.txt)を .python_packages/lib/site-packages に事前インストールする。
    # Azure側のOryxリモートビルドが使えない/信頼できない場合のフォールバック用。
    # Windows上からでも --platform 等を指定することで、Linux(manylinux)向けのwheelを取得できる。
    $SitePackagesDir = Join-Path $BuildDir ".python_packages\lib\site-packages"

    # unidic-lite はwheelを配布しておらずsdistのみのため、クロスプラットフォーム指定
    # (--platform/--abi/--python-version)とは同時指定できない(pipの制約)。
    # 純粋なデータパッケージ(コンパイル不要)なので、別途プラットフォーム指定なしで
    # インストールする(Windows上でビルドしてもLinux上でそのまま動作する)。
    #
    # torch は --target への「2回に分けたpip install」だと、既にターゲットへ
    # インストール済みの依存(jinja2/MarkupSafe等)とバージョン解決が競合してしまうため、
    # requirements.txt本体と同じ1回のpip呼び出しでまとめてインストールする。
    # また通常のPyPIにもCUDA同梱版のtorchが同じバージョン番号で存在するため、
    # (a) torchのみバージョンを "==2.6.0+cpu" と明示して曖昧さを無くし、
    # (b) --platform に manylinux2014_x86_64(他パッケージ用)と linux_x86_64(torchのCPU版wheel用、
    #     実ファイル名で確認済み: torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl)の両方を指定する。
    $ReqLines = (Get-Content (Join-Path $FunctionsDir "requirements.txt") | Where-Object { $_ -notmatch "^unidic-lite" }) + "torch==2.6.0+cpu"
    $MainReqPath = Join-Path $FunctionsDir ".build_requirements_main.txt"
    Set-Content -Path $MainReqPath -Value $ReqLines -Encoding ascii

    # pipはアップデート通知などの無害なメッセージも標準エラー出力に書くことがあり、
    # $ErrorActionPreference="Stop"の下ではそれだけでスクリプトが異常終了してしまう
    # (PowerShell 5.1のネイティブコマンド呼び出しの既知の挙動)。
    # そのためpip呼び出しの間だけ一時的に緩和し、成否は$LASTEXITCODEで判定する。
    $ErrorActionPreference = "Continue"

    python -m pip install `
        --python-version 3.11 `
        --implementation cp `
        --abi cp311 `
        --platform manylinux2014_x86_64 `
        --platform linux_x86_64 `
        --only-binary=:all: `
        --index-url https://download.pytorch.org/whl/cpu `
        --extra-index-url https://pypi.org/simple `
        --target $SitePackagesDir `
        -r $MainReqPath
    $MainInstallExitCode = $LASTEXITCODE
    Remove-Item $MainReqPath -Force
    if ($MainInstallExitCode -ne 0) {
        $ErrorActionPreference = "Stop"
        throw "依存パッケージのインストールに失敗しました(exit code $MainInstallExitCode)"
    }

    python -m pip install --target $SitePackagesDir "unidic-lite>=1.0.8"
    $UnidicInstallExitCode = $LASTEXITCODE

    $ErrorActionPreference = "Stop"
    if ($UnidicInstallExitCode -ne 0) {
        throw "unidic-liteのインストールに失敗しました(exit code $UnidicInstallExitCode)"
    }
}

# 5. zip化する
# PowerShellのCompress-Archiveは、Linux上のAzure FunctionsのRun From Package展開時に
# ディレクトリとして正しく認識されないzipエントリを生成することがある(パス区切りの互換性問題)。
# そのため、Pythonのzipfileモジュールで明示的にフォワードスラッシュ区切りのエントリ名で
# zip化する(Windows/Linux間で確実に互換性のある方法)。
if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir -Confirm:$false
}
New-Item -ItemType Directory -Force $DistDir | Out-Null

$zipScript = @'
import os
import sys
import zipfile

build_dir, zip_path = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(build_dir):
        for name in files:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, build_dir).replace(os.sep, "/")
            zf.write(full_path, rel_path)
'@
$zipScriptPath = Join-Path $FunctionsDir ".build_zip.py"
Set-Content -Path $zipScriptPath -Value $zipScript -Encoding utf8
python $zipScriptPath $BuildDir $ZipPath
Remove-Item $zipScriptPath -Force

Write-Host "デプロイ用zipを作成しました: $ZipPath"
Write-Host "次の手順(Blobアップロード -> WEBSITE_RUN_FROM_PACKAGE設定 -> 再起動)は functions/DEPLOYMENT.md を参照してください。"
