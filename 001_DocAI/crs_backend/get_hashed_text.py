"""
m_usersテーブルのpasswordに登録するハッシュ化文字列を取得するための処理
NOTE 最終的には不要なので消す
"""

if __name__ == "__main__":
    import bcrypt

    # ハッシュ化したい文字列を設定
    text_to_hash = "password"
    print("元の文字列 : ", text_to_hash)
    # ハッシュ値を取得
    hashed = bcrypt.hashpw(text_to_hash.encode(), bcrypt.gensalt())
    print("ハッシュ化した文字列 : ", hashed)
