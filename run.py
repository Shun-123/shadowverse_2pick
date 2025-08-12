# run.py
from app import app
from config import APP_CONFIG
import logging

if __name__ == '__main__':
    logging.getLogger().info("アプリケーション開始")
    app.run(
        host=APP_CONFIG['host'],
        port=APP_CONFIG['port'],
        debug=APP_CONFIG['debug']
    )
