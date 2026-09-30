"""AI(Azure OpenAI)による講座下書き生成のパッケージ。

- client.py     … AI への接続(差し替え可能。テストでは偽のクライアントを使う)
- schemas.py    … AI の出力の型(Pydantic で検証する)
- prompts.py    … プロンプト(版番号付き。精度改善はここを中心に行う)
- generator.py  … 呼び出し・検証・再試行・記録の流れ
"""
