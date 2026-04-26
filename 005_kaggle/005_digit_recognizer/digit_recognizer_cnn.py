"""
https://www.kaggle.com/competitions/digit-recognizer/overview
手書き数字画像（0〜9）の多クラス分類問題。
評価指標: Accuracy（正解率）

ベースライン(LightGBM): CV Accuracy = 0.9753

CNN（畳み込みニューラルネットワーク）モデル:
  画像認識に特化した構造で、ピクセルの「空間的なつながり」を学習できる。
  LightGBM が 784 個のピクセル値を独立した特徴量として扱うのに対し、
  CNN は隣接するピクセルのパターン（縦線・横線・曲線など）を捉えられる。

アーキテクチャ:
  入力(28×28×1)
    → 畳み込みブロック1: Conv2D(32) → BatchNorm → Conv2D(32) → MaxPool → Dropout
    → 畳み込みブロック2: Conv2D(64) → BatchNorm → Conv2D(64) → MaxPool → Dropout
    → 畳み込みブロック3: Conv2D(128) → BatchNorm → Dropout
    → Flatten → Dense(256) → Dropout → 出力(10クラス, softmax)

データ拡張（Data Augmentation）:
  学習画像をランダムに変形して水増しし、過学習を防ぐ。
  手書き文字は書く人によって傾きや大きさが異なるため、
  それを模倣した変形が汎化性能を高める。
"""

import numpy as np
import pandas as pd
from pathlib import Path

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from sklearn.model_selection import train_test_split

DATA_DIR = Path(r"C:\azure_ai\education\005_kaggle\competitions\digit-recognizer")

print(f"TensorFlow: {tf.__version__}")

train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

## データの前処理
# LightGBM: (N, 784) のまま使用
# CNN    : (N, 28, 28, 1) に reshape が必要（高さ×幅×チャンネル数）
X      = train.drop("label", axis=1).values.reshape(-1, 28, 28, 1) / 255.0
y      = train["label"].values
X_test = test.values.reshape(-1, 28, 28, 1) / 255.0

print(f"X shape: {X.shape}")  # (42000, 28, 28, 1)

# 検証データを分離（学習中の過学習モニタリング用）
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.1, random_state=1, stratify=y
)
print(f"学習: {X_train.shape[0]:,}枚  検証: {X_val.shape[0]:,}枚")


## データ拡張（Data Augmentation）の設定
# 実際の手書き文字は傾き・大きさ・位置が様々 → それをランダムに再現して汎化性能を上げる
# 注意: 数字は上下反転すると別の数字になるため flip は使わない（6→9 など）
data_augmentation = keras.Sequential([
    layers.RandomRotation(0.08),       # ±8% 回転（約±29度）
    layers.RandomTranslation(0.1, 0.1),  # 上下左右に ±10% シフト
    layers.RandomZoom(0.1),            # ±10% ズーム
], name="data_augmentation")


## CNNモデルの構築
def build_model():
    inputs = keras.Input(shape=(28, 28, 1))

    # 学習時のみデータ拡張を適用（推論時はスキップ）
    x = data_augmentation(inputs)

    # ---- 畳み込みブロック1 ----
    # Conv2D: フィルター（小さな窓）をスライドさせて局所パターンを検出する
    # filters=32: 32種類のパターン（横線・縦線・曲線など）を学習
    # kernel_size=3: 3×3ピクセルの窓で特徴を捉える
    x = layers.Conv2D(32, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Conv2D(32, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    # MaxPooling: 2×2領域の最大値を取り、特徴マップを半分のサイズに圧縮
    # → 位置の微小なズレに頑健になり、計算コストも削減
    x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.25)(x)

    # ---- 畳み込みブロック2 ----
    # filters=64: より複雑なパターン（数字の部分的な形状）を学習
    x = layers.Conv2D(64, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Conv2D(64, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.25)(x)

    # ---- 畳み込みブロック3 ----
    # filters=128: さらに抽象的なパターン（数字全体の形）を学習
    x = layers.Conv2D(128, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.25)(x)

    # ---- 全結合層 ----
    # Flatten: 2次元の特徴マップを1次元ベクトルに変換
    x = layers.Flatten()(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.5)(x)

    # 出力層: 10クラスの確率を出力（softmax で合計=1 になる）
    outputs = layers.Dense(10, activation="softmax")(x)

    model = keras.Model(inputs, outputs)
    return model


model = build_model()
model.summary()

## コンパイル
# Adam: 学習率を自動調整する最適化アルゴリズム
# sparse_categorical_crossentropy: 多クラス分類の損失関数
model.compile(
    optimizer=keras.optimizers.Adam(learning_rate=1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

## コールバックの設定
callbacks = [
    # 検証 accuracy が改善しなくなったら学習を早期終了
    EarlyStopping(
        monitor="val_accuracy",
        patience=10,        # 10 epoch 改善なしで停止
        restore_best_weights=True,  # 最良の重みを復元
        verbose=1,
    ),
    # 検証 loss が改善しなくなったら学習率を自動で下げる
    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,         # 学習率を半分に
        patience=4,
        min_lr=1e-6,
        verbose=1,
    ),
]

## 学習
print("\n学習開始")
history = model.fit(
    X_train, y_train,
    epochs=50,
    batch_size=64,
    validation_data=(X_val, y_val),
    callbacks=callbacks,
    verbose=1,
)

## 検証精度の確認
val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
print(f"\n検証 Accuracy: {val_acc:.4f}")
print(f"ベースライン(LightGBM) との比較: 0.9753 → {val_acc:.4f}")

## 予測・提出ファイルの出力
predictions = np.argmax(model.predict(X_test), axis=1)

output = pd.DataFrame({
    "ImageId": range(1, len(predictions) + 1),
    "Label":   predictions,
})
output.to_csv(
    Path(__file__).parent / "submission_cnn.csv",
    index=False
)
print(f"\n予測結果（先頭5件）:")
print(output.head())
print("submission_cnn.csv を出力しました")
