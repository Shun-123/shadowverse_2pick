# check_class_mapping.py
import sqlite3

def check_class_mapping():
    with sqlite3.connect("shadowverse_cards.db") as conn:
        # クラス別カード数を確認
        cursor = conn.execute("""
            SELECT class_id, class_name, COUNT(*) as count 
            FROM cards 
            WHERE is_token = 0
            GROUP BY class_id, class_name 
            ORDER BY class_id
        """)
        
        print("=== 現在のクラスマッピング ===")
        for class_id, class_name, count in cursor.fetchall():
            print(f"ID {class_id}: {class_name} ({count}枚)")
        
        # 特定カードでクラス確認
        test_cards = [
            ("10062210", "有翼の石像"),  # Haven系カード
            ("10171110", "ビビッドインベンター・イリス")  # Nemesis系カード
        ]
        
        print("\n=== 特定カードでの確認 ===")
        for card_id, expected_name in test_cards:
            cursor = conn.execute("""
                SELECT name, class_id, class_name 
                FROM cards WHERE card_id = ?
            """, (card_id,))
            row = cursor.fetchone()
            if row:
                print(f"{row[0]}: クラスID {row[1]} ({row[2]})")

def fix_class_mapping_if_needed():
    """必要に応じてクラスマッピングを修正"""
    with sqlite3.connect("shadowverse_cards.db") as conn:
        # 修正が必要な場合のみ実行
        corrections = [
            #("UPDATE cards SET class_name='Blood' WHERE class_id=5", "Blood"),
            #("UPDATE cards SET class_name='Haven' WHERE class_id=6", "Haven"), 
            #("UPDATE cards SET class_name='Nemesis' WHERE class_id=7", "Nemesis")
            ("UPDATE cards SET class_name='Elf' WHERE class_id=1", "Elf"),
            ("UPDATE cards SET class_name='Royal' WHERE class_id=2", "Royal"),
            ("UPDATE cards SET class_name='Witch' WHERE class_id=3", "Witch"),
            ("UPDATE cards SET class_name='Dragon' WHERE class_id=4", "Dragon"),
            ("UPDATE cards SET class_name='Nightmare' WHERE class_id=5", "Nightmare"),
            ("UPDATE cards SET class_name='Bishop' WHERE class_id=6", "Bishop"),
            ("UPDATE cards SET class_name='Nemesis' WHERE class_id=7", "Nemesis")
        ]
        
        for sql, class_name in corrections:
            result = conn.execute(sql)
            if result.rowcount > 0:
                print(f"{class_name}クラスのマッピングを修正: {result.rowcount}枚")
        
        conn.commit()

if __name__ == "__main__":
    check_class_mapping()
    # 必要に応じて以下のコメントアウトを外して実行
    # fix_class_mapping_if_needed()

# 0: Neutral (ニュートラル, Neutral)
# 1: Forestcraft (エルフ, Elf)
# 2: Swordcraft (ロイヤル, Royal)
# 3: Runecraft (ウィッチ, Witch)
# 4: Dragoncraft (ドラゴン, Dragon)
# 5: Abysscraft (ナイトメア, Nightmare)
# 6: Havencraft (ビショップ, Bishop)
# 7: Portalcraft (ネメシス, Nemesis)