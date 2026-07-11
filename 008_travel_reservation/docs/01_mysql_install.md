# MySQL環境構築手順書

MySQLが未導入の人が対象です。既にMySQLが導入済みの場合はこの手順は不要です。

## 1. インストーラのダウンロード

MySQL Installer for Windows(公式)からダウンロードする。

- ダウンロードページ: https://dev.mysql.com/downloads/installer/
- 動作確認環境がMySQL 8.0のためバージョンは **8.0系** を選択する

パッケージは2種類あるが、通常は **Web版(mysql-installer-web-community-*.msi)** でよい。

- Web版: インストール実行時にネットワーク経由で必要なファイルを取得する(ファイルサイズが小さい)
- Full版: オフライン環境でインストールする場合に使用する

ダウンロード時にOracleアカウントへのサインインを求められるが、ページ下部の「No thanks, just start my download.」からアカウント登録なしでダウンロードできる。

## 2. インストーラの実行

1. ダウンロードした`.msi`を実行する
2. 「Choosing a Setup Type」画面で **Server only** を選択する
   (GUIツールは別途A5:SQL Mk-2を導入するため、最小構成で問題ない)
3. 「Execute」でインストールを実行する

## 3. 初期設定ウィザード(Product Configuration)

1. **Type and Networking**
   - Config Type: `Development Computer`
   - Port: `3306`(既定のまま)
2. **Authentication Method**
   - `Use Strong Password Encryption for Authentication (RECOMMENDED)`を選択
3. **Accounts and Roles**
   - Root Password: rootアカウントの任意の強力なパスワードを設定する。**必ず控えておく**(以降の手順で頻繁に使用する)
4. **Windows Service**
   - Windows Service Name: `MySQL80`(ここでは既定のまま。手順書内のコマンド例はこの名前を前提にしている)
   - 「Start the MySQL Server at System Startup」にチェックを推奨
5. 「Apply Configuration」→「Finish」で完了する

## 4. インストール確認

サービスが登録され、起動していることを確認する。

```powershell
Get-Service MySQL80
```

`Status`が`Running`であればOK。停止している場合は起動する。

```powershell
Start-Service MySQL80
```

## 5. mysqlコマンドの動作確認
インストーラによって自動的に環境変数PATHへ追加される。以下がエラーなく実行できることを確認する。

```powershell
mysql --version
```

コマンドが見つからない場合は、PowerShellを再起動するか、以下を手動でPATHに追加する。

```
C:\Program Files\MySQL\MySQL Server 8.0\bin
```
