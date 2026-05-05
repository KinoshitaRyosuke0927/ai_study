import os
import shutil
import kagglehub


# Kaggleにログイン
kagglehub.login()
# データ指定
data_name = 'rossmann-store-sales'
# 解析対象のデータをダウンロード
path = kagglehub.competition_download(data_name)
print("Kaggleからダウンロードしたデータ:", path)
# ダウンロードしたフォルダを competitions ディレクトリに移動
dest = os.path.join(os.path.dirname(__file__), "competitions", os.path.basename(path))
os.makedirs(os.path.dirname(dest), exist_ok=True)
shutil.move(path, dest)
print("データの移動先:", dest)


"""
【次にやる課題】
# 毎月Playground Seriesが開催されている
- https://www.kaggle.com/competitions/playground-series-s6e4/overview
# 売上予測
- https://www.kaggle.com/competitions/rossmann-store-sales/overview
# 売上予測2
- https://www.kaggle.com/competitions/m5-forecasting-accuracy/overview
# 花画像分類
- https://www.kaggle.com/competitions/tpu-getting-started/overview
# ペット画像分析
- https://www.kaggle.com/competitions/petfinder-pawpularity-score
# 生成モデルの考え方学習
- https://www.kaggle.com/competitions/gan-getting-started


【学習用教材】
- https://www.kaggle.com/learn/intermediate-machine-learning
- https://www.kaggle.com/learn/feature-engineering
- https://www.kaggle.com/learn/computer-vision

# ラグ、トレンド、季節性、リーク回避の理解
- https://www.kaggle.com/learn/time-series
# Master efficient workflows for cleaning real-world, messy data.
- https://www.kaggle.com/learn/data-cleaning
# なぜ当たったか／外れたか
- https://www.kaggle.com/learn/machine-learning-explainability
# structured data 用のニューラルネットワークを作る入門
- https://www.kaggle.com/learn/intro-to-deep-learning
# Explore practical tools to guide the moral design of AI systems.
- https://www.kaggle.com/learn/intro-to-ai-ethics


"""
