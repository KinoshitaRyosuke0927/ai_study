-- ============================================================
-- 008_travel_reservation DB スキーマ定義
-- 対象: MySQL 8.0
-- 文字コード: utf8mb4（日本語データを扱うため）
--
-- ENGINE=InnoDB: 外部キー制約とトランザクションが使えるストレージエンジン
-- CHARSET=utf8mb4: 日本語や絵文字を正しく扱える文字コード(無印utf8は不完全)
-- COLLATE=utf8mb4_0900_ai_ci: 文字の比較・並び替えルール
--   (ai=アクセント差を区別しない、ci=大文字小文字を区別しない)
-- ============================================================

CREATE DATABASE IF NOT EXISTS travel_reservation
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE travel_reservation;

-- ------------------------------------------------------------
-- m_user: ユーザマスタ
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS m_user (
    user_id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    -- 短く上限が明確な文字列はVARCHAR(n)を使用
    user_name    VARCHAR(255) NOT NULL,
    mail_address VARCHAR(255) NOT NULL,
    -- bcryptハッシュを格納(現行実装は"$2b$12$..."形式・60文字)
    password     VARCHAR(255) NOT NULL,
    owner_flag   TINYINT(1) NOT NULL DEFAULT 0,
    UNIQUE KEY uk_m_user_mail_address (mail_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- m_hotel: ホテルマスタ
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS m_hotel (
    hotel_id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    hotel_name    VARCHAR(255) NOT NULL,
    owner_user_id INT UNSIGNED NOT NULL,
    address       VARCHAR(255) NOT NULL,
    -- 長さが不定で検索条件にもならない文章はTEXTを使用
    introduction  TEXT,
    KEY idx_m_hotel_owner_user_id (owner_user_id),
    -- CONSTRAINT: DB側でデータの整合性を強制するルール
    -- (存在しないuser_idをオーナーとして登録できないようにする)
    CONSTRAINT fk_m_hotel_owner_user
        FOREIGN KEY (owner_user_id) REFERENCES m_user (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- m_accommodation_plan: 宿泊プランマスタ
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS m_accommodation_plan (
    plan_id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    hotel_id      INT UNSIGNED NOT NULL,
    -- common/constants.py の AREA_CODE に対応するコード値("0301"=東京 等)
    area          VARCHAR(10) NOT NULL,
    plan_name     VARCHAR(255) NOT NULL,
    price         INT UNSIGNED NOT NULL,
    -- 1日あたりの最大予約可能室数
    capacity      INT UNSIGNED NOT NULL,
    room_size     INT UNSIGNED NOT NULL,
    has_breakfast TINYINT(1) NOT NULL DEFAULT 0,
    has_lunch     TINYINT(1) NOT NULL DEFAULT 0,
    has_dinner    TINYINT(1) NOT NULL DEFAULT 0,
    introduction  TEXT,
    KEY idx_m_accommodation_plan_hotel_id (hotel_id),
    -- CONSTRAINT: DB側でデータの整合性を強制するルール
    -- (存在しないhotel_idのプランを登録できないようにする)
    CONSTRAINT fk_m_accommodation_plan_hotel
        FOREIGN KEY (hotel_id) REFERENCES m_hotel (hotel_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- t_reservation: 予約トランザクション
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS t_reservation (
    reservation_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id        INT UNSIGNED NOT NULL,
    plan_id        INT UNSIGNED NOT NULL,
    date_of_stay   DATE NOT NULL,
    -- common/constants.py の RESERVATION_STATUS に対応するコード値
    -- ("1"=予約中, "2"=チェックイン済, "3"=キャンセル)
    status         CHAR(1) NOT NULL,
    KEY idx_t_reservation_user_id (user_id),
    KEY idx_t_reservation_plan_id_date (plan_id, date_of_stay),
    -- CONSTRAINT: DB側でデータの整合性を強制するルール
    -- (存在しないuser_idのユーザが予約できないようにする)
    CONSTRAINT fk_t_reservation_user
        FOREIGN KEY (user_id) REFERENCES m_user (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    -- (存在しないplan_idのプランが予約できないようにする)
    CONSTRAINT fk_t_reservation_plan
        FOREIGN KEY (plan_id) REFERENCES m_accommodation_plan (plan_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    -- CHECK制約: RESERVATION_STATUSで定義されたコード値以外を許可しない
    CONSTRAINT chk_t_reservation_status
        CHECK (status IN ('1', '2', '3'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
