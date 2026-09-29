# ============================================================
# AI学習ポータル DB セットアップ(Windows PowerShell)
#   1. データベースと接続ユーザを作成
#   2. テーブル定義とデータ(02_schema_and_data.sql)を登録
# 実行例(このフォルダで):
#   powershell -ExecutionPolicy Bypass -File .\setup_db.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup_db.ps1 -MysqlHost localhost -RootUser root
# ============================================================
param(
    [string]$MysqlHost = "localhost",
    [int]$Port = 3306,
    [string]$RootUser = "root"
)

$ErrorActionPreference = "Stop"

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
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
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
    $dump = (Join-Path $here "02_schema_and_data.sql").Replace("\", "/")
    & $mysql @common ai_learning_portal -e "source $dump"
    if ($LASTEXITCODE -ne 0) { throw "データの登録に失敗しました。" }
    Write-Host "テーブル定義とデータを登録しました。"
}
finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "次に backend/.env を作成し、MYSQL_PASSWORD に今入力した接続ユーザのパスワードを設定してください。"
