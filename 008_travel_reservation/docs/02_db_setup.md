# DB作成・データ投入手順書

前提: MySQL 8.0がインストール済みであること。

このリポジトリの`backend`ディレクトリを基準に手順を記載する。
以降のコマンドはPowerShellで`backend`ディレクトリに移動してから実行すること。

```powershell
cd <リポジトリのクローン先>\travel_reservation\backend
```

## 0. 前提確認

MySQLサービスが起動していることを確認する。

```powershell
Get-Service MySQL80
```

`Status`が`Running`でない場合は起動する。

```powershell
Start-Service MySQL80
```

## 1. rootでMySQLに接続

インストール時に設定したrootパスワードを使用する。
**PowerShellの現在のディレクトリが`backend`であること**を確認してから接続する(後続の`SOURCE`コマンドが相対パスになるため)。

```powershell
mysql -u root -p
```

以降、`mysql>`プロンプト内での操作になる。

## 2. アプリケーション用ユーザー作成

アプリからはrootを使わず、専用ユーザーで最小権限にて接続する。

```sql
CREATE USER IF NOT EXISTS 'ais_admin'@'localhost' IDENTIFIED BY '<各自で設定する強力なパスワード>';
GRANT SELECT, INSERT, UPDATE, DELETE ON travel_reservation.* TO 'ais_admin'@'localhost';
FLUSH PRIVILEGES;
```

- パスワードは平文でリポジトリにコミットしないこと(各自のメモや`.env`等で管理する)。

## 3. テーブル作成(DDL適用)

`database/ddl/schema.sql`を`SOURCE`コマンドで読み込む。`travel_reservation`データベースの作成もこのSQL内で行われる。

```sql
SOURCE database/ddl/schema.sql;
```

作成されるテーブル(4つ、外部キー制約付き)。

- `m_user`
- `m_hotel`
- `m_accommodation_plan`
- `t_reservation`

## 4. テーブル作成の確認

```sql
USE travel_reservation;
SHOW TABLES;
DESCRIBE m_user;
DESCRIBE m_hotel;
DESCRIBE m_accommodation_plan;
DESCRIBE t_reservation;
```

上記4テーブルが表示されることを確認する。

## 5. 動作確認用の最小データの投入

`database/dml/insert_minimum_data.sql`にDMLを用意している。同じくrootでの`mysql`セッション内で実行する。

```sql
SOURCE database/dml/insert_minimum_data.sql;
```

- 実行すると対象4テーブルを`TRUNCATE`したうえでINSERTする(DBを初期状態に戻すDML)。既存データは全て消える点に注意する。
- `m_user` → `m_hotel` → `m_accommodation_plan` → `t_reservation`の順(外部キー制約を満たす順)で登録する。
- 日本語の文字化けを防ぐため、DML内で`SET NAMES utf8mb4;`を実行している。

## 6. データ投入の確認

```sql
SELECT COUNT(*) FROM m_user;
SELECT COUNT(*) FROM m_hotel;
SELECT COUNT(*) FROM m_accommodation_plan;
SELECT COUNT(*) FROM t_reservation;
```

以下の件数と一致していることを確認する。

| テーブル | 件数 |
|---|---|
| `m_user` | 3 |
| `m_hotel` | 1 |
| `m_accommodation_plan` | 3 |
| `t_reservation` | 32 |

内容を確認したい場合は`SELECT * FROM <テーブル名>;`を実行する。
文字化けして見える場合は表示のみの問題であることが多い(コンソールのコードページの問題)。

```sql
SELECT user_name, CHAR_LENGTH(user_name), LENGTH(user_name) FROM m_user;
```

## 7. アプリ用ユーザーでの接続確認

```powershell
mysql -u ais_admin -p travel_reservation
```

```sql
SHOW TABLES;
```
