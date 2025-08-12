# config.py（新規作成）
import os

# データベース設定
DB_PATH = "./shadowverse_cards.db"

# ログ設定
LOG_FILE = "app.log"
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# クラス表示名マッピング
CLASS_NAMES = {
    0: "ニュートラル", 1: "エルフ", 2: "ロイヤル", 3: "ウィッチ",
    4: "ドラゴン", 5: "ナイトメア", 6: "ビショップ", 7: "ネメシス"
}

# アプリケーション設定
APP_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': True
}

# キャッシュ設定
CACHE_CONFIG = {
    'max_size': 1000,
    'ttl_seconds': 600
}

# 重み設定ファイルのパス
WEIGHTS_FILE = "weights.json"

# デフォルト重み設定
DEFAULT_WEIGHTS = {
    "version": 1,
    "weights": {
        "base": 1.0,
        "curve": 1.0,
        "role": 1.0,
        "duplication": 1.0,
        "synergy": 1.0,
        "archetype": 1.0,
        "meta": 1.0
    }
}
