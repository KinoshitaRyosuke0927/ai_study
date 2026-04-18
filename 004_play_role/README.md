# Whisper 最小音声文字起こしアプリ

ブラウザで録音した音声を FastAPI で受け取り、Whisper を使って文字起こしする最小構成のサンプルです。

## 構成

- フロントエンド: HTML + JavaScript
- バックエンド: FastAPI
- 音声認識: Whisper (`openai-whisper`)

## 事前準備

### 1. Python パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. ffmpeg のインストール

Whisper の動作には `ffmpeg` が必要です。

#### Windows
- 公式配布やパッケージマネージャーでインストールし、PATH を通してください。

#### macOS
```bash
brew install ffmpeg
```

#### Ubuntu / Debian
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

## 起動方法

```bash
uvicorn app:app --reload
```

起動後、ブラウザで以下を開いてください。

```text
http://127.0.0.1:8000
```

## 使い方

1. `録音開始` を押す
2. 話す
3. `録音終了` を押す
4. `文字起こし開始` を押す
5. 文字起こし結果を確認する

## 補足

- 最小構成のため Whisper モデルは `small` を使用しています。
- 軽くしたい場合は `tiny` や `base` に変更できます。
- 精度を上げたい場合は `medium` や `large` を検討できますが、処理時間とメモリ使用量が増えます。
