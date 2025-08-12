# archetype_analyzer.py
import sqlite3
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

@dataclass
class Archetype:
    name: str
    class_id: int
    key_patterns: List[str]
    ideal_curve: Dict[int, int]
    strategy_description: str
    min_cards_threshold: int

class ArchetypeAnalyzer:
    def __init__(self, db_path: str = "shadowverse_cards.db"):
        self.db_path = db_path
        self.archetypes = self._initialize_archetypes()

    def _initialize_archetypes(self) -> List[Archetype]:
        """アーキタイプ定義"""
        return [
            # エルフ
            Archetype(
                name="フェアリーテンポ",
                class_id=1,
                key_patterns=[r"フェアリー", r"コンボ_[2-4]"],
                ideal_curve={1: 4, 2: 6, 3: 5, 4: 4, 5: 3},
                strategy_description="フェアリーを活用した序中盤制圧",
                min_cards_threshold=4
            ),
            
            # ロイヤル
            Archetype(
                name="兵士展開",
                class_id=2,
                key_patterns=[r"兵士", r"指揮官", r"連携"],
                ideal_curve={1: 3, 2: 7, 3: 6, 4: 4, 5: 3},
                strategy_description="兵士シナジーによる盤面制圧",
                min_cards_threshold=5
            ),
            
            # ウィッチ
            Archetype(
                name="スペルブースト",
                class_id=3,
                key_patterns=[r"スペルブースト", r"スペル"],
                ideal_curve={1: 3, 2: 4, 3: 5, 4: 6, 5: 5},
                strategy_description="スペルでブーストし大型展開",
                min_cards_threshold=6
            ),
            
            Archetype(
                name="土の秘術",
                class_id=3,
                key_patterns=[r"土の印", r"土の秘術"],
                ideal_curve={1: 4, 2: 6, 3: 5, 4: 4, 5: 3},
                strategy_description="土の印を活用した除去制圧",
                min_cards_threshold=4
            ),
            
            # ドラゴン
            Archetype(
                name="ランプ",
                class_id=4,
                key_patterns=[r"PP.*増", r"PP.*回復", r"覚醒"],
                ideal_curve={1: 2, 2: 4, 3: 3, 4: 4, 5: 5, 6: 4},
                strategy_description="PPブーストから大型展開",
                min_cards_threshold=3
            ),
            
            # ナイトメア
            Archetype(
                name="ネクロマンス",
                class_id=5,
                key_patterns=[r"ネクロマンス", r"墓場"],
                ideal_curve={1: 4, 2: 5, 3: 5, 4: 4, 5: 4},
                strategy_description="墓場活用による後半戦略",
                min_cards_threshold=4
            ),
            
            # ビショップ
            Archetype(
                name="守護回復",
                class_id=6,
                key_patterns=[r"守護", r"回復", r"カウントダウン"],
                ideal_curve={1: 3, 2: 5, 3: 4, 4: 5, 5: 4},
                strategy_description="守護と回復による長期戦略",
                min_cards_threshold=5
            ),
            
            # ネメシス
            Archetype(
                name="アーティファクト",
                class_id=7,
                key_patterns=[r"アーティファクト", r"融合"],
                ideal_curve={1: 3, 2: 4, 3: 5, 4: 5, 5: 4},
                strategy_description="アーティファクト生成・活用",
                min_cards_threshold=4
            ),
        ]

    def analyze_deck_archetype(self, card_ids: List[str]) -> Dict[str, Any]:
        """デッキのアーキタイプを分析"""
        if not card_ids:
            return {"detected_archetype": None, "confidence": 0, "recommendations": []}

        # カード情報取得
        cards = []
        class_counts = {}
        
        with sqlite3.connect(self.db_path) as conn:
            for card_id in card_ids:
                cursor = conn.execute("""
                    SELECT name, class_id, cost, skill_text, evo_skill_text
                    FROM cards WHERE card_id = ?
                """, (card_id,))
                row = cursor.fetchone()
                if row:
                    cards.append({
                        'name': row[0],
                        'class_id': row[1],
                        'cost': row[2],
                        'skill_text': row[3] or '',
                        'evo_skill_text': row[4] or ''
                    })
                    class_counts[row[1]] = class_counts.get(row[1], 0) + 1

        if not cards:
            return {"detected_archetype": None, "confidence": 0, "recommendations": []}

        # 主要クラス特定（空の場合の安全処理）
        main_class = max(class_counts.keys(), key=lambda x: class_counts[x]) if class_counts else 0

        # アーキタイプスコア計算
        best_archetype = None
        best_score = 0
        
        for archetype in self.archetypes:
            if archetype.class_id != main_class:
                continue
                
            score = 0
            matching_cards = 0
            
            for card in cards:
                card_text = f"{card['skill_text']} {card['evo_skill_text']}"
                for pattern in archetype.key_patterns:
                    if re.search(pattern, card_text, re.IGNORECASE):
                        score += 2
                        matching_cards += 1
                        break
            
            if matching_cards >= archetype.min_cards_threshold and score > best_score:
                best_score = score
                best_archetype = archetype

        # 推奨事項生成
        recommendations = self._generate_recommendations(cards, best_archetype)
        
        confidence = min(90, best_score * 8) if best_archetype else 0

        return {
            "detected_archetype": best_archetype.name if best_archetype else None,
            "archetype_description": best_archetype.strategy_description if best_archetype else None,
            "confidence": confidence,
            "recommendations": recommendations
        }

    def _generate_recommendations(self, cards: List[Dict], 
                                archetype: Optional[Archetype]) -> List[str]:
        """推奨事項生成"""
        if not archetype:
            return ["明確なアーキタイプが検出されませんでした。バランス型を目指しましょう。"]
        
        recommendations = [f"戦略: {archetype.strategy_description}"]
        
        # マナカーブチェック
        current_curve = {}
        for card in cards:
            cost = min(card['cost'], 6)
            current_curve[cost] = current_curve.get(cost, 0) + 1
        
        for cost, ideal_count in archetype.ideal_curve.items():
            current_count = current_curve.get(cost, 0)
            if current_count < ideal_count * 0.7:
                recommendations.append(
                    f"{cost}コストを増やしましょう（現在{current_count}枚、理想{ideal_count}枚）"
                )
        
        return recommendations

    def calculate_archetype_bonus(self, candidate_card_id: str, 
                                deck_card_ids: List[str]) -> Tuple[float, List[str]]:
        """候補カードのアーキタイプボーナス"""
        if not deck_card_ids:
            return 0.0, []

        # デッキアーキタイプ分析
        archetype_analysis = self.analyze_deck_archetype(deck_card_ids)
        detected_archetype = archetype_analysis.get("detected_archetype")
        
        if not detected_archetype:
            return 0.0, []

        # 候補カード情報取得
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT name, skill_text, evo_skill_text
                FROM cards WHERE card_id = ?
            """, (candidate_card_id,))
            row = cursor.fetchone()
            
            if not row:
                return 0.0, []
            
            candidate_text = f"{row[1] or ''} {row[2] or ''}"

        # アーキタイプ情報取得
        archetype = next((a for a in self.archetypes if a.name == detected_archetype), None)
        if not archetype:
            return 0.0, []

        # パターンマッチング
        bonus = 0.0
        reasons = []
        
        for pattern in archetype.key_patterns:
            if re.search(pattern, candidate_text, re.IGNORECASE):
                bonus += 8.0
                reasons.append(f"{detected_archetype}キーカード (+8.0点)")
                break
        
        return round(bonus, 1), reasons
