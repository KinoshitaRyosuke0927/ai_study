# Azure Functions デプロイ用のステージングディレクトリを作成し、zip化するスクリプト。
#
# 使い方: 011_nightrain ディレクトリで `.\build_package.ps1` を実行すると
#         .build/ にステージングされ、dist/functions.zip が生成される
#         (既定で依存パッケージを .python_packages 配下に事前同梱=vendoring する)。
#         生成したzipは、Azure Storageの任意のBlobコンテナへアップロードしたうえで、
#         そのBlobを指すSAS URLをFunction Appの WEBSITE_RUN_FROM_PACKAGE アプリ設定に
#         明示的に設定し、Function Appを再起動してデプロイする。
#         手順の詳細・背景は DEPLOYMENT.md を参照。
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

$RootDir = $PSScriptRoot
$BuildDir = Join-Path $RootDir ".build"
$DistDir = Join-Path $RootDir "dist"
$ZipPath = Join-Path $DistDir "functions.zip"

# 1. ステージングディレクトリを作り直す
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir -Confirm:$false
}
New-Item -ItemType Directory -Force $BuildDir | Out-Null

# 2. Functions固有ファイルをコピーする
Copy-Item (Join-Path $RootDir "function_app.py") $BuildDir
Copy-Item (Join-Path $RootDir "host.json") $BuildDir
Copy-Item (Join-Path $RootDir "requirements.txt") $BuildDir
Copy-Item (Join-Path $RootDir ".funcignore") $BuildDir

# 3. ソース(app/)をコピーする(__pycache__は除外)
$AppSrc = Join-Path $RootDir "app"
$AppDst = Join-Path $BuildDir "app"
Copy-Item $AppSrc $AppDst -Recurse
Get-ChildItem $AppDst -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -Confirm:$false

# 学習済みモデル(app/model/reminder_classifier.joblib、数百KB)はデプロイパッケージにそのまま同梱する。
# 存在しない場合は推論時にエラーになるため、ここで事前にチェックしておく。
# (モデルは 011_agenda_tool で学習し、011_agenda_tool の python -m app.model.export_model でコピーする)
if (-not (Test-Path (Join-Path $AppDst "model\reminder_classifier.joblib"))) {
    throw "学習済みモデル app/model/reminder_classifier.joblib がありません。011_agenda_tool で python -m app.model.export_model を実行してください。"
}

if (-not $SkipVendoring) {
    # 4. 依存パッケージ(requirements.txt)を .python_packages/lib/site-packages に事前インストールする。
    # Azure側のOryxリモートビルドが使えない/信頼できない場合のフォールバック用。
    # Windows上からでも --platform 等を指定することで、Linux(manylinux)向けのwheelを取得できる。
    $SitePackagesDir = Join-Path $BuildDir ".python_packages\lib\site-packages"

    # pipはアップデート通知などの無害なメッセージも標準エラー出力に書くことがあり、
    # $ErrorActionPreference="Stop"の下ではそれだけでスクリプトが異常終了してしまう
    # (PowerShell 5.1のネイティブコマンド呼び出しの既知の挙動)。
    # そのためpip呼び出しの間だけ一時的に緩和し、成否は$LASTEXITCODEで判定する。
    $ErrorActionPreference = "Continue"

    # 依存パッケージ(scikit-learn・numpy・scipy等)はすべてLinux向けのwheelが配布されているため、
    # 1回のpip呼び出しでまとめてインストールする
    # (BERT版で必要だったtorchのCPU版指定・unidic-liteの別途インストールは不要)。
    # scikit-learn 1.8系・numpy 2.x系のLinux向けwheelは manylinux_2_27/2_28 タグでのみ配布されているため、
    # 従来の manylinux2014(=manylinux_2_17)に加えて指定する
    # (Azure FunctionsのPython 3.11実行環境はDebian 12ベース(glibc 2.36)のため、manylinux_2_28のwheelが動作する)。
    python -m pip install `
        --python-version 3.11 `
        --implementation cp `
        --abi cp311 `
        --platform manylinux2014_x86_64 `
        --platform manylinux_2_27_x86_64 `
        --platform manylinux_2_28_x86_64 `
        --only-binary=:all: `
        --target $SitePackagesDir `
        -r (Join-Path $RootDir "requirements.txt")
    $InstallExitCode = $LASTEXITCODE

    $ErrorActionPreference = "Stop"
    if ($InstallExitCode -ne 0) {
        throw "依存パッケージのインストールに失敗しました(exit code $InstallExitCode)"
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
$zipScriptPath = Join-Path $RootDir ".build_zip.py"
Set-Content -Path $zipScriptPath -Value $zipScript -Encoding utf8
python $zipScriptPath $BuildDir $ZipPath
Remove-Item $zipScriptPath -Force

Write-Host "デプロイ用zipを作成しました: $ZipPath"
Write-Host "次の手順(Blobアップロード -> WEBSITE_RUN_FROM_PACKAGE設定 -> 再起動)は DEPLOYMENT.md を参照してください。"
