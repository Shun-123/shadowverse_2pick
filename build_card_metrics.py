# build_card_metrics.py
import sqlite3
import json
import re
import logging
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "shadowverse_cards.db"

class CardMetricsBuilder:
    def __init__(self):
        # 基本評価重み
        self.rarity_bonus = {
            "bronze": 0, "silver": 5, "gold": 10, "legendary": 15
        }
        
        # 役割重み（2Pick重要度）
        self.role_weights = {
            "removal": 15,    # 除去
            "aoe": 18,        # 全体除去
            "draw": 8,        # ドロー
            "finisher": 12,   # フィニッシャー
            "protection": 8,  # 守護等
            "heal": 4         # 回復
        }
        
        # キーワード重み
        self.keyword_weights = {
            "疾走": 12, "突進": 8, "守護": 6, "必殺": 8,
            "ドレイン": 6, "ファンファーレ": 3, "ラストワード": 3
        }
        
        # コスト別期待ステータス（攻撃力+体力）
        self.expected_stats = {
            1: 2, 2: 4, 3: 6, 4: 8, 5: 10, 6: 12, 7: 14, 8: 16, 9: 18, 10: 20
        }

    def create_metrics_table(self):
        """メトリクステーブル作成"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_metrics (
                    card_id TEXT PRIMARY KEY,
                    base_rating REAL,
                    stat_efficiency REAL,
                    role_score REAL,
                    keyword_score REAL,
                    rarity_bonus REAL,
                    impact_score REAL,
                    notes TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(card_id) REFERENCES cards(card_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_rating 
                ON card_metrics(base_rating)
            """)
            conn.commit()
            logger.info("card_metricsテーブルを作成しました")

    def load_cards(self) -> List[Dict[str, Any]]:
        """カードデータを読み込み"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT card_id, name, class_id, class_name, cost, card_type, 
                       rarity, attack, defense, is_token, roles, keywords, skill_text
                FROM cards
            """)
            
            columns = [desc[0] for desc in cursor.description]
            cards = []
            
            for row in cursor.fetchall():
                card = dict(zip(columns, row))
                # JSON文字列をリストに変換
                card["roles"] = json.loads(card["roles"] or "[]")
                card["keywords"] = json.loads(card["keywords"] or "[]")
                cards.append(card)
            
            return cards

    def calculate_stat_efficiency(self, card: Dict[str, Any]) -> float:
        """ステータス効率を計算"""
        if card["card_type"] != "follower" or not card["attack"] or not card["defense"]:
            return 0.0
        
        actual_stats = card["attack"] + card["defense"]
        expected_stats = self.expected_stats.get(card["cost"], card["cost"] * 2)
        
        # 1ポイント差につき2点の補正
        return (actual_stats - expected_stats) * 2.0

    def calculate_role_score(self, card: Dict[str, Any]) -> float:
        """役割スコアを計算"""
        score = 0.0
        for role in card["roles"]:
            if role in self.role_weights:
                score += self.role_weights[role]
        return score

    def calculate_keyword_score(self, card: Dict[str, Any]) -> float:
        """キーワードスコアを計算"""
        score = 0.0
        for keyword in card["keywords"]:
            if keyword in self.keyword_weights:
                score += self.keyword_weights[keyword]
        
        # クラス特有の補正
        if card["class_id"] == 4 and "覚醒" in card["keywords"]:  # Dragon
            score += 5
        
        return score

    def calculate_impact_score(self, card: Dict[str, Any]) -> float:
        """即時影響力スコアを計算"""
        score = 0.0
        skill_text = card.get("skill_text", "")
        
        # スペルは基本的に即時影響
        if card["card_type"] == "spell":
            score += 8
        
        # 疾走・突進は即時影響
        keywords = set(card["keywords"])
        if "疾走" in keywords:
            score += 10
        elif "突進" in keywords:
            score += 6
        
        # テキストから即時効果を判定
        if re.search(r"(破壊|消滅|ダメージ)", skill_text):
            score += 8
        if re.search(r"(ドロー|引く)", skill_text):
            score += 5
        
        # 重いカードで即時影響がない場合はペナルティ
        if card["cost"] >= 6 and score == 0:
            score -= 8
        
        return score

    def calculate_base_rating(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """基本評価を計算"""
        # カードタイプ別基準値
        type_base = {
            "follower": 45, "spell": 50, "amulet": 40, "countdown_amulet": 42
        }.get(card["card_type"], 45)
        
        # 各要素を計算
        stat_eff = self.calculate_stat_efficiency(card)
        role_score = self.calculate_role_score(card)
        keyword_score = self.calculate_keyword_score(card)
        rarity_bonus = self.rarity_bonus.get(card["rarity"], 0)
        impact_score = self.calculate_impact_score(card)
        
        # 基本評価値
        base_rating = type_base + stat_eff + role_score + keyword_score + rarity_bonus + impact_score
        
        # トークンは基本的に評価を下げる
        if card["is_token"]:
            base_rating -= 15
        
        # 評価値を適切な範囲に調整
        base_rating = max(10, min(95, base_rating))
        
        return {
            "base_rating": round(base_rating, 1),
            "stat_efficiency": round(stat_eff, 1),
            "role_score": round(role_score, 1),
            "keyword_score": round(keyword_score, 1),
            "rarity_bonus": rarity_bonus,
            "impact_score": round(impact_score, 1),
            "notes": json.dumps([
                f"タイプ基準値: {type_base}",
                f"ステータス効率: {stat_eff:+.1f}",
                f"役割スコア: {role_score:+.1f}",
                f"キーワード: {keyword_score:+.1f}",
                f"レアリティ: {rarity_bonus:+.1f}",
                f"即時影響: {impact_score:+.1f}"
            ], ensure_ascii=False)
        }

    def build_all_metrics(self):
        """全カードのメトリクスを構築"""
        self.create_metrics_table()
        cards = self.load_cards()
        
        with sqlite3.connect(DB_PATH) as conn:
            for card in cards:
                metrics = self.calculate_base_rating(card)
                
                conn.execute("""
                    INSERT OR REPLACE INTO card_metrics 
                    (card_id, base_rating, stat_efficiency, role_score, 
                     keyword_score, rarity_bonus, impact_score, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    card["card_id"], metrics["base_rating"], 
                    metrics["stat_efficiency"], metrics["role_score"],
                    metrics["keyword_score"], metrics["rarity_bonus"],
                    metrics["impact_score"], metrics["notes"]
                ))
            
            conn.commit()
            logger.info(f"{len(cards)}枚のカードメトリクスを構築しました")

    def show_top_cards(self, limit: int = 10):
        """上位評価カードを表示"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT c.name, c.class_name, c.cost, c.card_type, m.base_rating
                FROM card_metrics m
                JOIN cards c ON m.card_id = c.card_id
                WHERE c.is_token = 0
                ORDER BY m.base_rating DESC
                LIMIT ?
            """, (limit,))
            
            print(f"\n=== 上位{limit}枚のカード ===")
            for name, class_name, cost, card_type, rating in cursor.fetchall():
                print(f"{name} ({class_name}, {cost}コスト, {card_type}): {rating:.1f}点")

def main():
    builder = CardMetricsBuilder()
    builder.build_all_metrics()
    builder.show_top_cards(15)

if __name__ == "__main__":
    main()
