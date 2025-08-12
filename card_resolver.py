# card_resolver.py
import sqlite3
import re
from typing import Optional, List, Dict, Any

class CardResolver:
    def __init__(self, db_path: str = "shadowverse_cards.db"):
        self.db_path = db_path
        self._cache = {}  # 簡易キャッシュ

    def resolve_card_id(self, name_or_id: str) -> Optional[str]:
        """カード名またはIDからcard_idを解決"""
        if not name_or_id:
            return None
        
        query = name_or_id.strip()
        
        # キャッシュチェック
        if query in self._cache:
            return self._cache[query]
        
        # 数字のみの場合はIDとして扱う
        if re.match(r'^\d+$', query):
            if self._card_exists(query):
                self._cache[query] = query
                return query
            return None
        
        # 名前で検索（完全一致優先）
        with sqlite3.connect(self.db_path) as conn:
            # 完全一致
            cursor = conn.execute(
                "SELECT card_id FROM cards WHERE name = ? AND is_token = 0 LIMIT 1",
                (query,)
            )
            result = cursor.fetchone()
            if result:
                card_id = result[0]
                self._cache[query] = card_id
                return card_id
            
            # 部分一致（前方一致優先）
            cursor = conn.execute(
                "SELECT card_id, name FROM cards WHERE name LIKE ? AND is_token = 0 ORDER BY LENGTH(name), name LIMIT 1",
                (f"{query}%",)
            )
            result = cursor.fetchone()
            if result:
                card_id = result[0]
                self._cache[query] = card_id
                return card_id
        
        return None

    def _card_exists(self, card_id: str) -> bool:
        """カードIDの存在確認"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM cards WHERE card_id = ? LIMIT 1",
                (card_id,)
            )
            return cursor.fetchone() is not None

    def get_suggestions(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """検索候補を取得"""
        if len(query) < 2:
            return []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT card_id, name, class_id, cost, rarity, 
                       CASE WHEN name = ? THEN 0 ELSE 1 END as priority
                FROM cards 
                WHERE name LIKE ? AND is_token = 0
                ORDER BY priority, LENGTH(name), name
                LIMIT ?
            """, (query, f"%{query}%", limit))
            
            return [{
                'card_id': row[0],
                'name': row[1],
                'class_id': row[2],
                'cost': row[3],
                'rarity': row[4]
            } for row in cursor.fetchall()]
