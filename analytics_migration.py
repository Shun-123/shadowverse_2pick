# analytics_migration.py
import sqlite3
from config import DB_PATH

def migrate_analytics_tables():
    """分析用テーブルを作成"""
    with sqlite3.connect(DB_PATH) as conn:
        # ピックセッション
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pick_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                class_name TEXT,
                final_wins INTEGER,
                final_losses INTEGER,
                notes TEXT
            )
        """)
        
        # ピックログ
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pick_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                pick_index INTEGER,
                rerolls_left INTEGER,
                candidate1_id TEXT,
                candidate2_id TEXT,
                recommended_id TEXT,
                chosen_id TEXT,
                action TEXT,
                scores_json TEXT,
                deck_snapshot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES pick_sessions(session_id)
            )
        """)
        
        # ユーザーフィードバック
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_type TEXT,
                content TEXT,
                rating INTEGER,
                card_context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # インデックス作成
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pick_logs_session ON pick_logs(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pick_logs_created ON pick_logs(created_at)")
        
        conn.commit()
        print("分析用テーブルの作成が完了しました")

if __name__ == "__main__":
    migrate_analytics_tables()
