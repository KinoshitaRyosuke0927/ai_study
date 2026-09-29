-- ============================================================
-- AI学習ポータル テーブル定義 + データ(デモ環境への移行用)
--   対象 DB : ai_learning_portal(先に 01_create_database.sql で作成しておく)
--   内容    : 全テーブルの定義(既存テーブルは作り直す)と、作成時点の全データ
--             ・デモ用のサンプルユーザ 2名
--                 admin     / WrDuo__3d_7p  (管理者)
--                 learner01 / dldtpnm7N2L4  (受講者)
--             ・講座「統計の基礎」(5単元・演習6問・データファイル scores.csv)
--             ・Alembic の版数(取り込み後の alembic upgrade head は何もしない)
--   実行例  : mysql -u root -p --default-character-set=utf8mb4 ai_learning_portal < 02_schema_and_data.sql
-- ============================================================

-- MySQL dump 10.13  Distrib 8.0.34, for Win64 (x86_64)
--
-- Host: localhost    Database: ai_learning_portal
-- ------------------------------------------------------
-- Server version	8.0.34

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('0eb2fcc73f83');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cells`
--

DROP TABLE IF EXISTS `cells`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cells` (
  `id` int NOT NULL AUTO_INCREMENT,
  `unit_id` int NOT NULL,
  `position` int NOT NULL,
  `cell_type` varchar(16) NOT NULL,
  `source` mediumtext NOT NULL,
  `problem_id` int DEFAULT NULL,
  `ai_generated` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `problem_id` (`problem_id`),
  KEY `unit_id` (`unit_id`),
  CONSTRAINT `cells_ibfk_1` FOREIGN KEY (`problem_id`) REFERENCES `problems` (`id`) ON DELETE SET NULL,
  CONSTRAINT `cells_ibfk_2` FOREIGN KEY (`unit_id`) REFERENCES `units` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=32 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cells`
--

LOCK TABLES `cells` WRITE;
/*!40000 ALTER TABLE `cells` DISABLE KEYS */;
INSERT INTO `cells` VALUES (1,1,1,'markdown','## 概念\n\nデータは大きく **量的データ**(数値で大きさを表す)と **質的データ**(カテゴリを表す)に分けられます。\nさらに、値の性質によって次の4つの **尺度水準** に分類されます。\n\n| 尺度 | 例 | できる計算 |\n|---|---|---|\n| 名義尺度 | 血液型、クラス | 度数を数える |\n| 順序尺度 | 満足度(1〜5)、順位 | 大小の比較 |\n| 間隔尺度 | 気温(℃)、西暦 | 差をとる |\n| 比例尺度 | 身長、点数、時間 | 比をとる |\n\n尺度によって使える集計方法が変わるため、分析の最初にデータの種類を確認することが大切です。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(2,1,2,'markdown','## 例題\n40人分のテストの成績データ `scores.csv` を読み込み、先頭の行と各列の型を確認します。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(3,1,3,'code','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\ndf.head()',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(4,1,4,'code','df.dtypes',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(5,1,5,'markdown','`class`(クラス)は名義尺度の質的データ、`math` や `study_hours` は比例尺度の量的データです。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(6,1,6,'markdown','## 演習',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(7,1,7,'exercise','',1,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(8,2,1,'markdown','## 概念\n\n量的データは値がばらばらなので、一定の幅の **階級** に区切って、各階級に入るデータの個数(**度数**)を数えます。\nこれを表にしたものが **度数分布表**、棒グラフにしたものが **ヒストグラム** です。\n\n階級の幅を変えると見え方が変わるため、いくつか試して分布の特徴(山の位置・広がり・偏り)をつかみます。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(9,2,2,'markdown','## 例題\n英語の点数を 20 点刻みの階級に分けて数えます。`pd.cut` で各データを階級に割り当てます。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(10,2,3,'code','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nbins = [20, 40, 60, 80, 100]\npd.cut(df[\"english\"], bins=bins).value_counts().sort_index()',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(11,2,4,'markdown','同じデータをヒストグラムで表示します。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(12,2,5,'code','import matplotlib.pyplot as plt\n\nplt.hist(df[\"english\"], bins=bins, edgecolor=\"white\")\nplt.xlabel(\"english\")\nplt.ylabel(\"count\")\nplt.show()',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(13,2,6,'markdown','## 演習',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(14,2,7,'exercise','',2,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(15,3,1,'markdown','## 概念\n\n代表値とは、データ全体の特徴を1つの数値で表したものです。\n\n- **平均(mean)**:すべての値の合計をデータ数で割った値 $\\bar{x} = \\frac{1}{n}\\sum_{i=1}^{n} x_i$\n- **中央値(median)**:小さい順に並べたとき真ん中にある値。データ数が偶数なら中央2つの平均\n- **最頻値(mode)**:データの中で最も多く現れる値\n\n> **ポイント** 平均は外れ値の影響を強く受けますが、中央値は受けにくい性質があります。年収や住宅価格のように偏りのあるデータでは、中央値もあわせて確認しましょう。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(16,3,2,'markdown','## 例題\n8人のテストの点数から、3つの代表値を求めます。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(17,3,3,'code','import pandas as pd\n\nscores = pd.Series([62, 75, 75, 81, 94, 58, 75, 88])\nprint(scores.mean())     # 平均\nprint(scores.median())   # 中央値\nprint(scores.mode()[0])  # 最頻値',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(18,3,4,'markdown','## 演習',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(19,3,5,'exercise','',3,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(20,4,1,'markdown','## 概念\n\n- **範囲**:最大値 − 最小値\n- **分散**:平均からの差(偏差)の2乗の平均 $s^2 = \\frac{1}{n-1}\\sum_{i=1}^{n}(x_i-\\bar{x})^2$\n- **標準偏差**:分散の平方根。元のデータと同じ単位になるので解釈しやすい\n\npandas の `var()` / `std()` は既定で **不偏分散**(n − 1 で割る、`ddof=1`)を計算します。\nNumPy の `np.var()` は既定で n で割る(`ddof=0`)ため、結果が異なる点に注意しましょう。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(21,4,2,'markdown','## 例題',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(22,4,3,'code','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nmath = df[\"math\"]\nprint(\"範囲:\", math.max() - math.min())\nprint(\"分散:\", round(math.var(), 2))\nprint(\"標準偏差:\", round(math.std(), 2))\nprint(\"標準偏差(ddof=0):\", round(math.std(ddof=0), 2))',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(23,4,4,'markdown','## 演習',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(24,4,5,'exercise','',4,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(25,4,6,'exercise','',5,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(26,5,1,'markdown','## 概念\n\n**相関係数** $r$ は、2つの変数の直線的な関係の強さを −1 〜 1 で表します。\n\n- $r$ が 1 に近い:一方が大きいほど、もう一方も大きい(正の相関)\n- $r$ が −1 に近い:一方が大きいほど、もう一方は小さい(負の相関)\n- $r$ が 0 に近い:直線的な関係はほとんどない\n\n> **注意** 相関があっても、一方が原因でもう一方が起きている(因果関係)とは限りません。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(27,5,2,'markdown','## 例題\n勉強時間と数学の点数の関係を散布図で確認します。',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(28,5,3,'code','import pandas as pd\nimport matplotlib.pyplot as plt\n\ndf = pd.read_csv(\"scores.csv\")\nplt.scatter(df[\"study_hours\"], df[\"math\"])\nplt.xlabel(\"study_hours\")\nplt.ylabel(\"math\")\nplt.show()',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(29,5,4,'code','df[[\"math\", \"english\", \"study_hours\"]].corr().round(2)',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(30,5,5,'markdown','## 演習',NULL,0,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(31,5,6,'exercise','',6,0,'2026-09-30 07:48:03','2026-09-30 07:48:03');
/*!40000 ALTER TABLE `cells` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `course_completions`
--

DROP TABLE IF EXISTS `course_completions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `course_completions` (
  `user_id` int NOT NULL,
  `course_id` int NOT NULL,
  `completed_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`user_id`,`course_id`),
  KEY `course_id` (`course_id`),
  CONSTRAINT `course_completions_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`) ON DELETE CASCADE,
  CONSTRAINT `course_completions_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `course_completions`
--

LOCK TABLES `course_completions` WRITE;
/*!40000 ALTER TABLE `course_completions` DISABLE KEYS */;
/*!40000 ALTER TABLE `course_completions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `course_prerequisites`
--

DROP TABLE IF EXISTS `course_prerequisites`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `course_prerequisites` (
  `course_id` int NOT NULL,
  `prerequisite_id` int NOT NULL,
  PRIMARY KEY (`course_id`,`prerequisite_id`),
  KEY `prerequisite_id` (`prerequisite_id`),
  CONSTRAINT `course_prerequisites_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`) ON DELETE CASCADE,
  CONSTRAINT `course_prerequisites_ibfk_2` FOREIGN KEY (`prerequisite_id`) REFERENCES `courses` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `course_prerequisites`
--

LOCK TABLES `course_prerequisites` WRITE;
/*!40000 ALTER TABLE `course_prerequisites` DISABLE KEYS */;
/*!40000 ALTER TABLE `course_prerequisites` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `courses`
--

DROP TABLE IF EXISTS `courses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `courses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `slug` varchar(100) NOT NULL,
  `title` varchar(200) NOT NULL,
  `summary` text NOT NULL,
  `level` varchar(16) NOT NULL,
  `tags` json NOT NULL,
  `outcomes` json NOT NULL,
  `libraries` json NOT NULL,
  `status` varchar(16) NOT NULL,
  `author_id` int DEFAULT NULL,
  `published_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`),
  KEY `author_id` (`author_id`),
  CONSTRAINT `courses_ibfk_1` FOREIGN KEY (`author_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `courses`
--

LOCK TABLES `courses` WRITE;
/*!40000 ALTER TABLE `courses` DISABLE KEYS */;
INSERT INTO `courses` VALUES (1,'statistics-basics','統計の基礎','データ分析の出発点となる記述統計を、pandas で手を動かしながら学びます。データの種類から代表値、散らばり、相関までを扱い、実データを要約して読み解けるようになることを目指します。','basic','[\"統計\", \"pandas\"]','[\"データの種類に応じた集計方法を選べる\", \"代表値と散らばりでデータを要約できる\", \"相関を計算し、正しく解釈できる\"]','[\"pandas\", \"numpy\", \"matplotlib\"]','published',1,NULL,'2026-09-30 07:48:03','2026-09-30 07:48:03');
/*!40000 ALTER TABLE `courses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `datasets`
--

DROP TABLE IF EXISTS `datasets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `datasets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `course_id` int NOT NULL,
  `filename` varchar(255) NOT NULL,
  `content_type` varchar(100) NOT NULL,
  `content` longblob NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `course_id` (`course_id`),
  CONSTRAINT `datasets_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `datasets`
--

LOCK TABLES `datasets` WRITE;
/*!40000 ALTER TABLE `datasets` DISABLE KEYS */;
INSERT INTO `datasets` VALUES (1,1,'scores.csv','text/csv',0x73747564656E745F69642C636C6173732C6D6174682C656E676C6973682C73747564795F686F7572730D0A533030312C412C37382C34302C372E360D0A533030322C422C33342C36312C322E390D0A533030332C412C37382C36342C362E360D0A533030342C422C35382C34332C332E370D0A533030352C412C33342C36342C342E350D0A533030362C422C36312C36302C362E370D0A533030372C412C38342C36372C382E300D0A533030382C422C38372C35372C392E350D0A533030392C412C34332C34372C342E300D0A533031302C422C37302C36302C382E300D0A533031312C412C37302C35342C362E300D0A533031322C422C33362C35312C332E320D0A533031332C412C35382C34372C362E390D0A533031342C422C36312C36392C342E360D0A533031352C412C36372C38312C362E390D0A533031362C422C34392C36392C342E390D0A533031372C412C37352C37382C372E390D0A533031382C422C35362C34392C342E300D0A533031392C412C36392C34322C352E390D0A533032302C422C36382C36362C342E390D0A533032312C412C35342C38332C362E360D0A533032322C422C34322C36332C332E370D0A533032332C412C36382C39322C352E350D0A533032342C422C37312C37392C372E350D0A533032352C412C38352C38302C392E380D0A533032362C422C37352C36372C372E350D0A533032372C412C38352C36362C392E370D0A533032382C422C36352C34392C362E340D0A533032392C412C36392C37352C372E300D0A533033302C422C39392C37302C31302E380D0A533033312C412C38372C38302C392E330D0A533033322C422C36372C36372C332E390D0A533033332C412C37372C37372C382E330D0A533033342C422C37392C36372C382E370D0A533033352C412C35372C37302C322E390D0A533033362C422C37392C37372C362E380D0A533033372C412C37372C37332C392E310D0A533033382C422C37382C37322C362E360D0A533033392C412C36312C36302C352E350D0A533034302C422C33312C36302C322E310D0A,'2026-09-30 07:48:03','2026-09-30 07:48:03');
/*!40000 ALTER TABLE `datasets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `problems`
--

DROP TABLE IF EXISTS `problems`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `problems` (
  `id` int NOT NULL AUTO_INCREMENT,
  `course_id` int NOT NULL,
  `unit_id` int DEFAULT NULL,
  `kind` varchar(16) NOT NULL,
  `position` int NOT NULL,
  `answer_format` varchar(16) NOT NULL,
  `title` varchar(200) NOT NULL,
  `prompt` mediumtext NOT NULL,
  `hint` text NOT NULL,
  `starter_code` mediumtext NOT NULL,
  `grading` varchar(16) NOT NULL,
  `expected_output` mediumtext NOT NULL,
  `test_code` mediumtext NOT NULL,
  `choices` json NOT NULL,
  `correct_answer` text NOT NULL,
  `tolerance` float NOT NULL,
  `explanation` mediumtext NOT NULL,
  `related_unit_id` int DEFAULT NULL,
  `ai_model_answer` mediumtext NOT NULL,
  `author_answer` mediumtext NOT NULL,
  `verify_status` varchar(16) NOT NULL,
  `content_version` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `course_id` (`course_id`),
  KEY `related_unit_id` (`related_unit_id`),
  KEY `unit_id` (`unit_id`),
  CONSTRAINT `problems_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`) ON DELETE CASCADE,
  CONSTRAINT `problems_ibfk_2` FOREIGN KEY (`related_unit_id`) REFERENCES `units` (`id`) ON DELETE SET NULL,
  CONSTRAINT `problems_ibfk_3` FOREIGN KEY (`unit_id`) REFERENCES `units` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `problems`
--

LOCK TABLES `problems` WRITE;
/*!40000 ALTER TABLE `problems` DISABLE KEYS */;
INSERT INTO `problems` VALUES (1,1,1,'exercise',1,'code','クラスごとの人数','質的データは度数を数えて集計します。`class` 列について、クラスごとの人数をクラス名の順に表示してください。空欄 `____` を埋めて実行し、提出してください。','Series の値ごとの出現回数は value_counts() で数えられます。','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\ncounts = df[\"class\"].____().sort_index()\nprint(counts)','output','class\nA    20\nB    20\nName: count, dtype: int64','','[]','',0.000001,'value_counts() は質的データの集計でよく使います。',NULL,'','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\ncounts = df[\"class\"].value_counts().sort_index()\nprint(counts)','verified',1,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(2,1,2,'exercise',1,'code','数学の度数分布表','数学(`math`)の点数を **10 点刻み**(30〜100 点)の階級に分け、階級の順に度数を表示してください。','階級の区切りは変数 bins に用意してあります。','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nbins = range(30, 101, 10)\ntable = pd.cut(df[\"math\"], bins=____).value_counts().sort_index()\nprint(table)','output','math\n(30, 40]      4\n(40, 50]      3\n(50, 60]      5\n(60, 70]     12\n(70, 80]     10\n(80, 90]      5\n(90, 100]     1\nName: count, dtype: int64','','[]','',0.000001,'(30, 40] は「30 より大きく 40 以下」を表します。',NULL,'','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nbins = range(30, 101, 10)\ntable = pd.cut(df[\"math\"], bins=bins).value_counts().sort_index()\nprint(table)','verified',1,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(3,1,3,'exercise',1,'code','外れ値を含むデータの代表値','9人目として **300点**(入力ミスによる外れ値)が加わりました。このデータの平均と中央値を求めてください。空欄 `____` を埋めて実行し、提出してください。','pandas の Series には .mean() と .median() メソッドがあります。','import pandas as pd\n\nscores = pd.Series([62, 75, 75, 81, 94, 58, 75, 88, 300])\n\nmean = scores.____()\nmedian = scores.____()\n\nprint(f\"平均: {mean:.2f}\")\nprint(f\"中央値: {median}\")','output','平均: 100.89\n中央値: 75.0','','[]','',0.000001,'平均は 76.0 から 100.89 に大きく動きましたが、中央値は 75.0 のままです。',NULL,'','import pandas as pd\n\nscores = pd.Series([62, 75, 75, 81, 94, 58, 75, 88, 300])\n\nmean = scores.mean()\nmedian = scores.median()\n\nprint(f\"平均: {mean:.2f}\")\nprint(f\"中央値: {median}\")','verified',1,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(4,1,4,'exercise',1,'code','英語の標準偏差','英語(`english`)の点数の **標準偏差**(不偏、`ddof=1`)を求め、小数第2位まで表示してください。','df[\"english\"] に対して std() を呼び出します。','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nsd = ____\nprint(round(sd, 2))','output','12.43','','[]','',0.000001,'pandas の std() は既定で ddof=1(不偏)です。',NULL,'','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nsd = df[\"english\"].std()\nprint(round(sd, 2))','verified',1,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(5,1,4,'exercise',2,'code','数学の点数の標準化','平均が 0、標準偏差が 1 になるように変換することを **標準化** といい、変換後の値を **zスコア** と呼びます。\n$z_i = \\frac{x_i - \\bar{x}}{s}$\n\n数学の点数を標準化した Series を変数 `z` に作ってください。この演習はテストコードで採点します(`z` の平均が 0、標準偏差が 1 になっていれば正解です)。','平均を引いて、標準偏差で割ります。','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nmath = df[\"math\"]\nz = ____\nprint(z.head())','test','','assert len(z) == 40\nassert abs(z.mean()) < 1e-9\nassert abs(z.std() - 1) < 1e-9','[]','',0.000001,'zスコアを使うと、単位や平均の異なるデータどうしを比較できます。',NULL,'','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nmath = df[\"math\"]\nz = (math - math.mean()) / math.std()\nprint(z.head())','verified',1,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(6,1,5,'exercise',1,'code','勉強時間と英語の相関係数','勉強時間(`study_hours`)と英語(`english`)の点数の相関係数を求め、小数第3位まで表示してください。','Series どうしの相関係数は corr() で求められます。','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nr = df[\"study_hours\"].____(df[\"english\"])\nprint(round(r, 3))','output','0.326','','[]','',0.000001,'数学より弱いものの、正の相関があります。',NULL,'','import pandas as pd\n\ndf = pd.read_csv(\"scores.csv\")\nr = df[\"study_hours\"].corr(df[\"english\"])\nprint(round(r, 3))','verified',1,'2026-09-30 07:48:03','2026-09-30 07:48:03');
/*!40000 ALTER TABLE `problems` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `submissions`
--

DROP TABLE IF EXISTS `submissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `submissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `problem_id` int NOT NULL,
  `answer` mediumtext NOT NULL,
  `output` mediumtext NOT NULL,
  `passed` tinyint(1) NOT NULL,
  `content_version` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `problem_id` (`problem_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `submissions_ibfk_1` FOREIGN KEY (`problem_id`) REFERENCES `problems` (`id`) ON DELETE CASCADE,
  CONSTRAINT `submissions_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `submissions`
--

LOCK TABLES `submissions` WRITE;
/*!40000 ALTER TABLE `submissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `submissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `unit_progress`
--

DROP TABLE IF EXISTS `unit_progress`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `unit_progress` (
  `user_id` int NOT NULL,
  `unit_id` int NOT NULL,
  `completed_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`user_id`,`unit_id`),
  KEY `unit_id` (`unit_id`),
  CONSTRAINT `unit_progress_ibfk_1` FOREIGN KEY (`unit_id`) REFERENCES `units` (`id`) ON DELETE CASCADE,
  CONSTRAINT `unit_progress_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `unit_progress`
--

LOCK TABLES `unit_progress` WRITE;
/*!40000 ALTER TABLE `unit_progress` DISABLE KEYS */;
/*!40000 ALTER TABLE `unit_progress` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `units`
--

DROP TABLE IF EXISTS `units`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `units` (
  `id` int NOT NULL AUTO_INCREMENT,
  `course_id` int NOT NULL,
  `position` int NOT NULL,
  `title` varchar(200) NOT NULL,
  `summary` text NOT NULL,
  `goals` json NOT NULL,
  `estimated_minutes` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `course_id` (`course_id`),
  CONSTRAINT `units_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `units`
--

LOCK TABLES `units` WRITE;
/*!40000 ALTER TABLE `units` DISABLE KEYS */;
INSERT INTO `units` VALUES (1,1,1,'データの種類','量的データと質的データ、尺度水準の違いを学び、pandas でデータの型を確認します。','[\"量的データと質的データを区別できる\", \"4つの尺度水準を説明できる\", \"pandas でデータを読み込み、列の型を確認できる\"]',20,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(2,1,2,'度数分布とヒストグラム','量的データを階級に分けて数え、分布の形をヒストグラムで確認します。','[\"度数分布表の階級と度数を説明できる\", \"pandas で度数分布表を作れる\", \"matplotlib でヒストグラムを描ける\"]',25,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(3,1,3,'代表値：平均・中央値・最頻値','3つの代表値の違いと、外れ値が与える影響を学びます。','[\"平均・中央値・最頻値の違いを説明できる\", \"pandas で代表値を計算できる\", \"外れ値が代表値に与える影響を理解する\"]',20,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(4,1,4,'散らばり：分散と標準偏差','データが平均の周りにどれくらい散らばっているかを数値で表します。','[\"範囲・分散・標準偏差を説明できる\", \"不偏分散と ddof の意味を理解する\", \"データを標準化(zスコア)できる\"]',25,'2026-09-30 07:48:03','2026-09-30 07:48:03'),(5,1,5,'相関','2つの量的データの関係を、散布図と相関係数で確認します。','[\"散布図から2変数の関係を読み取れる\", \"相関係数を計算し、解釈できる\", \"相関と因果の違いを説明できる\"]',25,'2026-09-30 07:48:03','2026-09-30 07:48:03');
/*!40000 ALTER TABLE `units` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `login_name` varchar(64) NOT NULL,
  `display_name` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `is_admin` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `login_name` (`login_name`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'admin','管理者','scrypt$16384$8$1$Z4kha/IQJIml50IEO99uVw==$tuM780UvC/WJRK0/q9dcWUj+yFe46FcT2IHMTfjIpv727DOUDdEsNXAS7TguuQHOZFKMRO8lUkellS0LVke6WQ==',1,1,'2026-09-30 07:48:01','2026-09-30 07:48:01'),(2,'learner01','受講者 01','scrypt$16384$8$1$eyxyVGVhmhvIU+fuUyOKxQ==$/QU1EzMupxjCGwLt0SxJc9YAjKa43P2JQQM3ivDAFV6oIs7Tqupb9RrkTAtVjUC/zku2nT9a1hAPQ8eGKasqgQ==',0,1,'2026-09-30 07:48:02','2026-09-30 07:48:02');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed
