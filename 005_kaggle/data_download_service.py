import os
import shutil
import kagglehub


# Kaggleにログイン
kagglehub.login()
# データ指定
data_name = 'digit-recognizer'
# 解析対象のデータをダウンロード
path = kagglehub.competition_download(data_name)
print("Kaggleからダウンロードしたデータ:", path)
# ダウンロードしたフォルダを competitions ディレクトリに移動
dest = os.path.join(os.path.dirname(__file__), "competitions", os.path.basename(path))
os.makedirs(os.path.dirname(dest), exist_ok=True)
shutil.move(path, dest)
print("データの移動先:", dest)
