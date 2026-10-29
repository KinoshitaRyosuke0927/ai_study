# ============================================================
# AI学習ポータル DB セットアップ(Windows PowerShell)
#   1. データベースと接続ユーザを作成
#   2. スナップショットのテーブル定義とデータ(snapshot_*/schema_and_data.sql)を登録
#      (既存のテーブルは作り直すため、取り込み先の DB にあったデータは消える)
#   3. スナップショットの講座の画像(snapshot_*/images)を画像の保存先にコピー
# 実行例(このフォルダで):
#   powershell -ExecutionPolicy Bypass -File .\setup_db.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup_db.ps1 -MysqlHost localhost -RootUser root
#   powershell -ExecutionPolicy Bypass -File .\setup_db.ps1 -ImageDir D:\portal\images   # IMAGE_LOCAL_DIR を変えている場合
# ============================================================
param(
    [string]$MysqlHost = "localhost",
    [int]$Port = 3306,
    [string]$RootUser = "root",
    [string]$ImageDir = ""
)

$ErrorActionPreference = "Stop"

# 使うスナップショット(新しいスナップショットを作ったら、ここのフォルダ名を変える)
$snapshotName = "snapshot_20261030"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$snapshot = Join-Path $here $snapshotName
if (-not (Test-Path (Join-Path $snapshot "schema_and_data.sql"))) { throw "スナップショットが見つかりません: $snapshot" }
# 画像の保存先(既定は backend/var/images。backend/.env の IMAGE_LOCAL_DIR と合わせる)
if (-not $ImageDir) { $ImageDir = Join-Path $here "..\backend\var\images" }

# 既存のデータが消えることを確認する
Write-Host "スナップショット $snapshotName の内容で DB ai_learning_portal を作り直します。"
Write-Host "DB にある既存のテーブルとデータはすべて削除されます(画像の保存先: $ImageDir)。"
$answer = Read-Host "続けますか? (y/N)"
if ($answer -ne "y") { Write-Host "中止しました。"; exit 1 }

# mysql コマンドを探す(PATH に無ければ既定のインストール先を見る)
$mysql = (Get-Command mysql -ErrorAction SilentlyContinue).Source
if (-not $mysql) {
    $candidate = Get-ChildItem "C:\Program Files\MySQL\MySQL Server *\bin\mysql.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($candidate) { $mysql = $candidate.FullName }
}
if (-not $mysql) { throw "mysql コマンドが見つかりません。MySQL の bin フォルダを PATH に追加してください。" }

# パスワードの入力(画面には表示しない)
function Read-Plain([string]$prompt) {
    $secure = Read-Host $prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
$rootPw = Read-Plain "MySQL 管理者($RootUser)のパスワード"
$appPw = Read-Plain "作成する接続ユーザ ai_learning_portal のパスワード"
if (-not $appPw) { throw "接続ユーザのパスワードを入力してください。" }

# 管理者パスワードは環境変数で渡す(コマンド履歴に残さない)
$env:MYSQL_PWD = $rootPw
$common = @("-h", $MysqlHost, "-P", $Port, "-u", $RootUser, "--default-character-set=utf8mb4")
try {
    # 1. データベースと接続ユーザを作成(01_create_database.sql と同じ内容)
    $escaped = $appPw.Replace("\", "\\").Replace("'", "''")
    $sql = @"
CREATE DATABASE IF NOT EXISTS ai_learning_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'ai_learning_portal'@'localhost' IDENTIFIED BY '$escaped';
ALTER USER 'ai_learning_portal'@'localhost' IDENTIFIED BY '$escaped';
GRANT ALL PRIVILEGES ON ai_learning_portal.* TO 'ai_learning_portal'@'localhost';
FLUSH PRIVILEGES;
"@
    & $mysql @common -e $sql
    if ($LASTEXITCODE -ne 0) { throw "データベースの作成に失敗しました。" }
    Write-Host "データベースと接続ユーザを作成しました。"

    # 2. テーブル定義とデータを登録(文字化けを防ぐため mysql の source で直接読み込む)
    $dump = (Join-Path $snapshot "schema_and_data.sql").Replace("\", "/")
    & $mysql @common ai_learning_portal -e "source $dump"
    if ($LASTEXITCODE -ne 0) { throw "データの登録に失敗しました。" }
    Write-Host "テーブル定義とデータを登録しました。"
}
finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
}

# 3. 講座の画像をコピー(講座 ID ごとのフォルダ。同じ名前のファイルは上書き)
New-Item -ItemType Directory -Force $ImageDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $snapshot "images\*") $ImageDir
Write-Host "講座の画像をコピーしました: $ImageDir"

Write-Host ""
Write-Host "次に backend/.env を作成し、MYSQL_PASSWORD に今入力した接続ユーザのパスワードを設定してください。"
