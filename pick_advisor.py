# pick_advisor.py
import sqlite3
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from cache_system import card_info_cache, cached_method

@dataclass
class PickAdvice:
    """ピックアドバイス結果"""
    action: str
    recommended_card_id: Optional[str]
    recommended_card_name: Optional[str]
    confidence: float
    reasoning: List[str]
    card_scores: List[Dict[str, Any]]

class TwoPickAdvisor:
    def __init__(self, db_path: str = "shadowverse_cards.db"):
        self.db_path = db_path
        
        # 理想的なマナカーブ（30枚デッキ）
        self.ideal_curve = {1: 4, 2: 6, 3: 6, 4: 5, 5: 4, 6: 2, 7: 1, 8: 1}
        
        # 役割の目標枚数
        self.role_targets = {
            "removal": 4, "draw": 3, "finisher": 2, "protection": 3, "aoe": 2
        }

    @cached_method(card_info_cache, "card_info")
    def get_card_info(self, card_id: str) -> Optional[Dict[str, Any]]:
        """キャッシュ対応のカード情報取得"""
        # 既存の実装をそのまま使用（デコレータがキャッシュを処理）
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.*, m.base_rating, m.stat_efficiency, m.role_score,
                       m.keyword_score, m.rarity_bonus, m.impact_score
                FROM cards c
                LEFT JOIN card_metrics m ON c.card_id = m.card_id
                WHERE c.card_id = ?
            """, (card_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            card = dict(zip(columns, row))
            
            # JSON文字列を変換
            card["roles"] = json.loads(card["roles"] or "[]")
            card["keywords"] = json.loads(card["keywords"] or "[]")
            
            return card

    def get_cache_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        return card_info_cache.get_stats()

    def analyze_deck(self, deck_card_ids: List[str]) -> Dict[str, Any]:
        """現在のデッキを分析"""
        curve = {}
        roles = {}
        total_cards = len(deck_card_ids)
        
        for card_id in deck_card_ids:
            card = self.get_card_info(card_id)
            if not card:
                continue
            
            # マナカーブ
            cost = card["cost"]
            curve[cost] = curve.get(cost, 0) + 1
            
            # 役割
            for role in card["roles"]:
                roles[role] = roles.get(role, 0) + 1
        
        return {
            "total_cards": total_cards,
            "curve": curve,
            "roles": roles
        }

    def calculate_curve_bonus(self, card_cost: int, deck_analysis: Dict[str, Any], 
                            pick_index: int) -> float:
        """マナカーブ補正を計算"""
        current_count = deck_analysis["curve"].get(card_cost, 0)
        ideal_count = self.ideal_curve.get(card_cost, 1)
        
        # 進行度に応じた目標調整
        progress = deck_analysis["total_cards"] / 30
        adjusted_target = ideal_count * progress
        
        bonus = 0.0
        if current_count < adjusted_target:
            shortage = adjusted_target - current_count
            bonus = min(shortage * 8, 15)
            
            # 序盤は低コスト重視
            if pick_index <= 8 and card_cost <= 3:
                bonus *= 1.3
        elif current_count > adjusted_target * 1.5:
            excess = current_count - adjusted_target
            bonus = -min(excess * 5, 10)
        
        return bonus

    def calculate_role_bonus(self, card_roles: List[str], 
                           deck_analysis: Dict[str, Any]) -> float:
        """役割補正を計算"""
        bonus = 0.0
        
        for role in card_roles:
            if role not in self.role_targets:
                continue
            
            current_count = deck_analysis["roles"].get(role, 0)
            target_count = self.role_targets[role]
            
            if current_count < target_count:
                shortage = target_count - current_count
                bonus += min(shortage * 6, 12)
            elif current_count >= target_count * 1.5:
                bonus -= 5
        
        return bonus

    def calculate_reroll_threshold(self, pick_index: int, rerolls_left: int,
                                 deck_analysis: Dict[str, Any]) -> float:
        """リロール閾値を計算"""
        base_threshold = 60.0
        
        # フェーズ調整
        if pick_index <= 5:
            phase_adj = 8  # 序盤は厳選
        elif pick_index <= 10:
            phase_adj = 0  # 中盤は標準
        else:
            phase_adj = -8  # 終盤は妥協
        
        # リロール残数調整
        reroll_adj = min(rerolls_left * 4, 12)
        
        # 緊急度調整
        urgency_adj = 0
        roles = deck_analysis["roles"]
        
        if roles.get("removal", 0) == 0 and pick_index >= 8:
            urgency_adj += 10
        
        low_cost = sum(deck_analysis["curve"].get(c, 0) for c in [1, 2])
        if low_cost <= 2 and pick_index >= 6:
            urgency_adj += 8
        
        return max(45, min(80, base_threshold + phase_adj + reroll_adj + urgency_adj))

    def get_pick_advice(self, candidate_card_ids: List[str], 
                       current_deck_ids: List[str], pick_index: int, 
                       rerolls_left: int) -> PickAdvice:
        """ピックアドバイスを生成"""
        deck_analysis = self.analyze_deck(current_deck_ids)
        card_scores = []
        
        # 各候補カードを評価
        for card_id in candidate_card_ids:
            card = self.get_card_info(card_id)
            if not card:
                continue
            
            base_score = card.get("base_rating", 50.0)
            curve_bonus = self.calculate_curve_bonus(
                card["cost"], deck_analysis, pick_index
            )
            role_bonus = self.calculate_role_bonus(
                card["roles"], deck_analysis
            )
            
            # 重複ペナルティ
            duplication_penalty = 0
            if card_id in current_deck_ids:
                count = current_deck_ids.count(card_id)
                duplication_penalty = -5 * count
            
            final_score = base_score + curve_bonus + role_bonus + duplication_penalty
            
            card_scores.append({
                "card_id": card_id,
                "name": card["name"],
                "cost": card["cost"],
                "base_score": base_score,
                "curve_bonus": curve_bonus,
                "role_bonus": role_bonus,
                "duplication_penalty": duplication_penalty,
                "final_score": final_score
            })
        
        if not card_scores:
            return PickAdvice("pick", None, None, 0, ["評価可能なカードがありません"], [])
        
        # 最高スコアのカードを特定
        best_card = max(card_scores, key=lambda x: x["final_score"])
        best_score = best_card["final_score"]
        
        # リロール判断
        threshold = self.calculate_reroll_threshold(
            pick_index, rerolls_left, deck_analysis
        )
        
        should_reroll = rerolls_left > 0 and best_score < threshold
        
        # 推奨理由を生成
        reasoning = []
        if should_reroll:
            reasoning.append(f"最高スコア{best_score:.1f}が閾値{threshold:.1f}を下回るためリロール推奨")
            reasoning.append(f"残りリロール回数: {rerolls_left}回")
        else:
            reasoning.append(f"{best_card['name']}を推奨（スコア: {best_score:.1f}）")
            if best_card["curve_bonus"] > 0:
                reasoning.append(f"マナカーブ改善効果: +{best_card['curve_bonus']:.1f}")
            if best_card["role_bonus"] > 0:
                reasoning.append(f"役割補完効果: +{best_card['role_bonus']:.1f}")
        
        confidence = min(90, max(50, abs(best_score - 60) + 50))
        
        return PickAdvice(
            action="reroll" if should_reroll else "pick",
            recommended_card_id=None if should_reroll else best_card["card_id"],
            recommended_card_name=None if should_reroll else best_card["name"],
            confidence=confidence,
            reasoning=reasoning,
            card_scores=card_scores
        )
