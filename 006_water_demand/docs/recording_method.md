# ウォーターサーバー用重量計の比較資料

対象製品:
- **A&D FGシリーズ**（主に FG-30KBM / FG-60KBM を想定）
- **Brecknell GP100 USB**
- **DYMO S100**

更新日: 2026-07-13

---

## 1. この資料の目的
この資料は、ウォーターサーバーの消費量を重量計測で記録するために、候補となる **A&D FGシリーズ / Brecknell GP100 USB / DYMO S100** を比較し、**どの方式を採用するか判断するための材料**をまとめたものです。

今回の用途では、単に重さが測れればよいだけではなく、以下の観点が重要です。

- **ウォーターサーバーを載せられる容量があるか**
- **PCへデータを取り込めるか**
- **CSV化や継続運用がしやすいか**
- **価格が予算に合うか**
- **日常運用で壊れにくいか、扱いやすいか**

---

## 2. 先に結論
3製品を比較すると、考え方は次のようになります。

- **A&D FGシリーズ**は、価格は高いものの、**容量・安定感・通信オプション・国内調達性**のバランスが最も良い本命候補です。 [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/) [A&D WinCT](https://www.aandd.co.jp/products/software/winct/)
- **Brecknell GP100 USB**は、**A&Dよりかなり安価で、PC通信の扱いやすさが比較的明確**です。USB virtual COM port の記載があるため、自作でCSV取得したい場合に相性が良い候補です。 [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)
- **DYMO S100**は、**もっとも買いやすく、USB接続も分かりやすい安価候補**ですが、発送用途寄りで、PC連携の柔軟性やOS互換情報の新しさではやや不安があります。 [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html) [DYMOユーザーガイド](https://download.dymo.com/dymo/user-guides/Scales/S100_S250_S400_UserGuide_en-US.pdf)

**ただし非常に重要な注意点として、Brecknell GP100 USB と DYMO S100 はどちらも 45kg / 100lb 級です。** ウォーターサーバー本体 + 満水ボトル + 台板の総重量が 45kg を超える可能性がある場合、この2機種はその時点で候補から外すべきです。 [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/) [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html)

---

## 3. 製品別まとめ

## 3-1. A&D FGシリーズ

### 概要
A&D FGシリーズは、国内メーカーの業務用デジタル台はかりです。ウォーターサーバー用途では、ポールなしの **FG-30KBM / FG-60KBM** が比較対象として現実的です。シリーズとして **RS-232C、Bluetooth、USB変換、データ処理ソフト** が揃っており、**重量記録システムを真面目に組む前提では最も整っている候補**です。 [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/) [A&D 通信FAQ](https://www.aandd.jp/support/comfaq.html)

### 公式サイトにある主な仕様
- 想定モデル: **FG-30KBM / FG-60KBM**
- 標準価格: **45,000円（税抜）**
- 計量皿寸法: **300 × 380 mm**
- 容量: **30kg / 60kg**
- 電源: **ACアダプタまたは乾電池**
- 通信オプション:
  - **FG-23JA**: RS-232Cインタフェース（10,000円税抜）
  - **FG-24JA**: RS-232C / コンパレータ出力（12,000円税抜）
  - **FG-27JA**: Bluetooth通信インタフェース（8,000円税抜）
  - **AX-USB-DIN**: USBコンバータ・ケーブルセット（13,000円税抜）
- ソフトウェア:
  - **WinCT**: PCへ計量データを取り込み、テキスト形式やワークシートへ直接入力可能 [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/) [A&D USBコンバータ](https://www.aandd.co.jp/products/weighing/balance/bal-peripherals/usb/) [A&D WinCT](https://www.aandd.co.jp/products/software/winct/)

### 購入候補サイト / 仕様確認サイト
- **A&D公式製品ページ**: 仕様・オプション・標準価格の確認用。 [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/)
- **Yahoo!ショッピング掲載例**: FG-30KBM の国内販売例。検索結果上では **27,600円** や **35,100円** の例が確認できました。 [Yahoo!ショッピング検索例](https://store.shopping.yahoo.co.jp/osc-shop/fg-30kbm-mk.html) [価格.com検索例](https://search.kakaku.com/FG-30KBM/)
- **楽天市場検索例**: FG-30KBM 系の国内販売例。 [楽天市場検索例](https://search.rakuten.co.jp/search/mall/fg%E2%88%9230kbm%E2%88%92k/)

### メリット
- **業務用としての安定感が高い**
- **60kgモデルまで選べるため、ウォーターサーバー用途に現実的**
- **RS-232C / Bluetooth / USB変換 / PCソフト**が揃っており、記録設計の自由度が高い
- **国内メーカーで情報が取りやすい**
- **WinCT や AD-1688 など周辺機器も豊富** [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/) [A&D WinCT](https://www.aandd.co.jp/products/software/winct/) [A&D 通信FAQ](https://www.aandd.jp/support/comfaq.html)

### デメリット
- **本体価格が高い**
- USB直結ではなく、**RS-232Cや変換機器を前提にした構成になることがある**
- 安価な発送用スケールと比べて、初期費用は明らかに重い

### 向いているケース
- ある程度きちんとしたシステムとして運用したい
- 容量不足リスクを避けたい
- PCへの記録やCSV化を安定して行いたい
- 国内調達性や保守性を重視したい

---

## 3-2. Brecknell GP100 USB

### 概要
Brecknell GP100 USB は、発送・倉庫・軽工業向けのポータブルベンチスケールです。公式には **USB virtual COM port** を備え、PCとの通信が可能とされています。NCI protocol を搭載し、一般的な発送ソフトとの接続も想定されています。 **A&Dより安価で、しかもPCからの扱いやすさが比較的明確**という点が強みです。 [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)

### 公式サイトにある主な仕様
- 最大荷重: **100 lb / 45 kg**
- 最小表示: **0.2 lb / 0.1 kg**
- 通信: **USB virtual COM port**
- 寸法: **10.95 × 12.50 × 2.20 in / 278 × 318 × 56 mm**
- 表示: **1 inch のバックライトLCD**
- 電源: **9V電池（付属）**、ACアダプタ対応（別売）
- 構造: **22 gauge steel** のリブ付きベース
- 機能: **Hold / Tare / Units / Auto shut-off**
- 用途: **Shipping/Receiving, Light Industrial, Warehouse** [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)

### 購入候補サイト / 仕様確認サイト
- **Brecknell公式製品ページ**: 仕様確認用。 [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)
- **Scales Plus 商品ページ**: GP100 USB の詳細仕様ページ。カテゴリ上では **MSRP $139.00 / Now $112.00** の表示例が確認できます。 [Scales Plus 商品ページ](https://www.scalesplus.com/brecknell-gp100-usb-bench-scale-100-lb-x-0-2-lb/) [Scales Plus GPカテゴリ](https://www.scalesplus.com/shop-by-brand/brecknell/shop-by-model/brecknell-gp/)
- **Global Industrial**: 検索スニペット上では **$118.13** の表示例が確認できました。 [Global Industrial](https://www.globalindustrial.com/c/tools/scales)
- **Amazon掲載例**: 商品掲載が確認できます。 [Amazon掲載例](https://www.amazon.com/Brecknell-GP100-Electronic-Capacity-Portable/dp/B074T5F9FV)

### メリット
- **A&Dよりかなり安価**
- **USB virtual COM port** のため、PC側で扱いやすい可能性が高い
- 発送用スケールの中では、**通信仕様が比較的明確**
- 構造が金属ベースで、簡易郵便スケールよりはしっかりしている [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)

### デメリット
- **容量は45kgまで**
- **台面が小さめ**で、ウォーターサーバーの足が収まるか要確認
- ACアダプタやUSBケーブルが標準では付かない記載があり、周辺部品確認が必要 [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)
- 国内流通はA&Dほど強くない

### 向いているケース
- 45kg以内に収まることが分かっている
- A&Dは高すぎるが、通信仕様はできるだけ明確なものがほしい
- CSV取得や自作ツール連携を視野に入れている

---

## 3-3. DYMO S100

### 概要
DYMO S100 は、発送用途向けの **Digital USB Shipping Scale** です。公式ページでは、**USBケーブルで PC または Mac に接続**し、オンラインの郵送・発送サービスで使えると説明されています。ユーザーガイドでは、PC接続時に **自動認識** されるとされています。 **購入しやすさとわかりやすさでは有力な安価候補**です。 [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html) [DYMOユーザーガイド](https://download.dymo.com/dymo/user-guides/Scales/S100_S250_S400_UserGuide_en-US.pdf)

### 公式サイトにある主な仕様
- 最大荷重: **100 lb / 45 kg**
- 表示分解能: **0.2 lb increments**
- 接続: **USBでPC/Mac接続**
- 電源: **USB給電（ケーブル付属）または単4電池3本**
- 特徴: **Hold, Tare, Auto shut-off, detachable LCD display**
- 寸法: **3.625" × 18.2" × 17.5"**
- 用途: **Mailing and Shipping**
- 公式ソフト互換: **Windows 8.1 / macOS 10.14 and below** [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html)

### 購入候補サイト / 仕様確認サイト
- **DYMO公式製品ページ**: 公式仕様確認用。 [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html)
- **Office Depot 商品ページ**: 製品掲載あり。 [Office Depot](https://www.officedepot.com/a/products/780198/DYMO-100-lb-Digital-USB-Shipping/)
- **Amazon 商品ページ**: 販売ページが確認できます。 [Amazon](https://www.amazon.com/DYMO-Digital-Shipping-Scale-100-Pound/dp/B0053HCP8K)
- **Staples 商品ページ**: 検索結果上では **$154.99** や **$59.99** の表示例が確認できます。 [Staples 1](https://www.staples.com/dymo-s100-digital-shipping-scale-heavy-duty-black-automatic-shut-off-100lb-capacity-1776111/product_IM1KF6534) [Staples 2](https://www.staples.com/s100-portable-digital-usb-shipping-scale-100-lb/product_PEL1776111)

### メリット
- **USBでPC/Mac接続できる**ことが分かりやすい
- 購入先が比較的見つけやすい
- **USBケーブル付属**の記載があり、始めやすい [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html)
- 価格帯としてはA&Dよりかなり低くなる可能性が高い

### デメリット
- **容量は45kgまで**
- 公式互換OS情報がやや古く、長期運用で不安が残る
- 通信仕様はあるものの、**USB virtual COM のような明確さはなく、PC側の扱いやすさではBrecknellに一歩譲る可能性**がある [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html) [DYMOユーザーガイド](https://download.dymo.com/dymo/user-guides/Scales/S100_S250_S400_UserGuide_en-US.pdf)
- 発送用途色が強く、業務用台はかりとしての剛性感ではA&Dに劣る

### 向いているケース
- 安価に試したい
- PCにつないでとにかく動けばよい
- 45kg以内に収まることが明確
- まずはPoCや試験運用から始めたい

---

## 4. 3製品の比較表

| 項目 | A&D FGシリーズ | Brecknell GP100 USB | DYMO S100 |
|---|---|---|---|
| 想定モデル | FG-30KBM / FG-60KBM | GP100 USB | S100 |
| 価格帯の目安 | 本体45,000円税抜 + 通信オプション | 約 US$112〜139 前後 | おおむね US$100台前半中心 |
| 最大荷重 | 30kg / 60kg | 45kg | 45kg |
| PC接続 | RS-232C / Bluetooth / USB変換 / WinCT | USB virtual COM | USBでPC/Mac接続 |
| 台面サイズ | 300 × 380 mm | 278 × 318 mm | 寸法記載中心、発送用フラット形状 |
| 周辺機器 | 非常に豊富 | 限定的 | 限定的 |
| 国内調達性 | 高い | 中 | 中 |
| 業務用途の安定感 | 高い | 中 | 中〜低 |
| CSV化のしやすさ | 高い | 比較的高い | 中 |
| 初期費用 | 高い | 中 | 低〜中 |

---

## 5. メリット・デメリットの整理

## A&D FGシリーズのメリット / デメリット
### メリット
- 容量と安定感がある
- 通信方法の選択肢が多い
- PC連携の情報が揃っている
- 国内メーカーで長く使いやすい

### デメリット
- 価格が高い
- 通信まで含めるとさらに費用が増える

### 一言でいうと
**「高いが、一番失敗しにくい」方式**です。

---

## Brecknell GP100 USB のメリット / デメリット
### メリット
- A&Dよりかなり安い
- USB virtual COM のため、PCで扱いやすそう
- 構造が比較的しっかりしている

### デメリット
- 45kg上限
- 台面が小さめ
- 国内での調達やサポートはA&Dほど強くない

### 一言でいうと
**「容量が足りるなら、通信と価格のバランスが良い」方式**です。

---

## DYMO S100 のメリット / デメリット
### メリット
- USB接続が分かりやすい
- 購入しやすい
- 導入コストを抑えやすい

### デメリット
- 45kg上限
- 通信仕様の柔軟性ではBrecknellに劣る可能性
- 公式OS互換情報がやや古い

### 一言でいうと
**「まず安価に試すには良いが、本番運用の安心感はやや弱い」方式**です。

---

## 6. どう判断するか

### ケースA: 総重量が 45kg を超える可能性がある
この場合、**Brecknell GP100 USB と DYMO S100 は除外**です。A&D FGシリーズ、少なくとも **FG-60KBM** を軸に考えるべきです。 [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/)

### ケースB: 総重量は 45kg 以内で、PC連携を重視する
この場合、**Brecknell GP100 USB** が有力です。理由は、USB virtual COM が明示されており、CSV取得や定期取り込みなどの実装を考えやすいからです。 [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)

### ケースC: 総重量は 45kg 以内で、とにかく安く早く試したい
この場合、**DYMO S100** が有力です。最初のPoC用途としては十分ありえます。 [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html)

### ケースD: 長期運用を前提に、失敗コストを下げたい
この場合は結局 **A&D FGシリーズ** の方が安全です。価格差はありますが、後から「容量が足りない」「通信が思ったより扱いづらい」「台面が不安」といった手戻りを減らせます。 [A&D FGシリーズ](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/) [A&D 通信FAQ](https://www.aandd.jp/support/comfaq.html)

---

## 7. 最終所感
現時点での判断軸を一言でまとめると、以下です。

- **安心・本命重視**: A&D FGシリーズ
- **価格と通信のバランス重視**: Brecknell GP100 USB
- **まず安く試す重視**: DYMO S100

私なら、まず最初に **ウォーターサーバー本体 + 満水ボトル + 台板の総重量** を見積もります。

- **45kg超の可能性が少しでもあるなら A&D FGシリーズ**
- **45kg以内と確信できるなら Brecknell GP100 USB を第一候補**
- **さらに試験導入寄りなら DYMO S100**

という順で考えます。

---

## 8. 参考リンク一覧

### A&D FGシリーズ
- [A&D FGシリーズ公式](https://www.aandd.co.jp/products/weighing/balance/bal-platform/fg/)
- [A&D USBコンバータ・ケーブルセット](https://www.aandd.co.jp/products/weighing/balance/bal-peripherals/usb/)
- [A&D WinCT](https://www.aandd.co.jp/products/software/winct/)
- [A&D 通信方法FAQ](https://www.aandd.jp/support/comfaq.html)
- [価格.com検索例](https://search.kakaku.com/FG-30KBM/)
- [Yahoo!ショッピング掲載例](https://store.shopping.yahoo.co.jp/osc-shop/fg-30kbm-mk.html)

### Brecknell GP100 USB
- [Brecknell公式](https://www.brecknellscales.com/products/postal-mail-shipping-scales/gp100-usb-gp250-usb/)
- [Scales Plus 商品ページ](https://www.scalesplus.com/brecknell-gp100-usb-bench-scale-100-lb-x-0-2-lb/)
- [Scales Plus GPカテゴリ](https://www.scalesplus.com/shop-by-brand/brecknell/shop-by-model/brecknell-gp/)
- [Global Industrial](https://www.globalindustrial.com/c/tools/scales)
- [Amazon掲載例](https://www.amazon.com/Brecknell-GP100-Electronic-Capacity-Portable/dp/B074T5F9FV)

### DYMO S100
- [DYMO公式](https://www.dymo.com/scales/ship-scale-100lbs-na/SP_2795409.html)
- [DYMOユーザーガイド](https://download.dymo.com/dymo/user-guides/Scales/S100_S250_S400_UserGuide_en-US.pdf)
- [Office Depot](https://www.officedepot.com/a/products/780198/DYMO-100-lb-Digital-USB-Shipping/)
- [Amazon](https://www.amazon.com/DYMO-Digital-Shipping-Scale-100-Pound/dp/B0053HCP8K)
- [Staples 1](https://www.staples.com/dymo-s100-digital-shipping-scale-heavy-duty-black-automatic-shut-off-100lb-capacity-1776111/product_IM1KF6534)
- [Staples 2](https://www.staples.com/s100-portable-digital-usb-shipping-scale-100-lb/product_PEL1776111)
