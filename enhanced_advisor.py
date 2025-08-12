# enhanced_advisor.py
from pick_advisor import TwoPickAdvisor
from card_resolver import CardResolver
from synergy_engine import SynergyEngine
from archetype_analyzer import ArchetypeAnalyzer
import sqlite3
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class PickAdvice:
    action: str
    recommended_card_id: Optional[str]
    recommended_card_name: Optional[str]
    confidence: float
    reasoning: List[str]
    card_scores: List[Dict[str, Any]]

class EnhancedTwoPickAdvisor(TwoPickAdvisor):
    def __init__(self, db_path: str = "shadowverse_cards.db"):
        super().__init__(db_path)
        self.resolver = CardResolver(db_path)
        self.synergy_engine = SynergyEngine(db_path)
        self.archetype_analyzer = ArchetypeAnalyzer(db_path)

    def get_pick_advice_by_names(self, candidate1: str, candidate2: str, 
                                deck_input: str, pick_index: int, 
                                rerolls_left: int) -> Dict[str, Any]:
        """名前またはIDでアドバイスを取得（シナジー・アーキタイプ対応）"""
        # カードIDに解決
        card1_id = self.resolver.resolve_card_id(candidate1)
        card2_id = self.resolver.resolve_card_id(candidate2)
        
        if not card1_id or not card2_id:
            return {
                'error': f'カードが見つかりません: {candidate1 if not card1_id else candidate2}',
                'resolved': {
                    'candidate1': card1_id,
                    'candidate2': card2_id
                }
            }
        
        # デッキIDリストを解決
        deck_ids = []
        if deck_input.strip():
            deck_names = [name.strip() for name in deck_input.replace('、', ',').split(',') if name.strip()]
            for name in deck_names:
                card_id = self.resolver.resolve_card_id(name)
                if card_id:
                    deck_ids.append(card_id)
        
        # 拡張アドバイス取得
        advice = self.get_pick_advice_enhanced(
            candidate_card_ids=[card1_id, card2_id],
            current_deck_ids=deck_ids,
            pick_index=pick_index,
            rerolls_left=rerolls_left
        )
        
        return {
            'advice': advice,
            'resolved_deck_count': len(deck_ids),
            'original_deck_count': len(deck_names) if deck_input.strip() else 0
        }

    def get_pick_advice_enhanced(self, candidate_card_ids: List[str], 
                               current_deck_ids: List[str], pick_index: int, 
                               rerolls_left: int) -> PickAdvice:
        """シナジー・アーキタイプを考慮した拡張アドバイス"""
        deck_analysis = self.analyze_deck(current_deck_ids)
        card_scores = []
        
        # 各候補カードを評価
        for card_id in candidate_card_ids:
            card = self.get_card_info(card_id)
            if not card:
                continue
            
            # 基本評価
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
            
            # シナジーボーナス
            synergy_bonus, synergy_reasons = self.synergy_engine.calculate_synergy_bonus(
                card_id, current_deck_ids, pick_index
            )
            
            # アーキタイプボーナス
            archetype_bonus, archetype_reasons = self.archetype_analyzer.calculate_archetype_bonus(
                card_id, current_deck_ids
            )
            
            final_score = (base_score + curve_bonus + role_bonus + 
                         duplication_penalty + synergy_bonus + archetype_bonus)
            
            card_scores.append({
                "card_id": card_id,
                "name": card["name"],
                "cost": card["cost"],
                "base_score": round(base_score, 1),
                "curve_bonus": round(curve_bonus, 1),
                "role_bonus": round(role_bonus, 1),
                "duplication_penalty": round(duplication_penalty, 1),
                "synergy_bonus": round(synergy_bonus, 1),
                "archetype_bonus": round(archetype_bonus, 1),
                "final_score": round(final_score, 1),
                "synergy_reasons": synergy_reasons,
                "archetype_reasons": archetype_reasons
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
        
        # 推奨理由を生成（拡張版）
        reasoning = []
        if should_reroll:
            reasoning.append(f"最高スコア{best_score:.1f}が閾値{threshold:.1f}を下回るためリロール推奨")
            reasoning.append(f"残りリロール回数: {rerolls_left}回")
        else:
            reasoning.append(f"{best_card['name']}を推奨（スコア: {best_score:.1f}）")
            
            # 各ボーナスの説明
            if best_card["curve_bonus"] > 0:
                reasoning.append(f"マナカーブ改善: +{best_card['curve_bonus']:.1f}")
            if best_card["role_bonus"] > 0:
                reasoning.append(f"役割補完: +{best_card['role_bonus']:.1f}")
            if best_card["synergy_bonus"] > 0:
                reasoning.append(f"シナジー効果: +{best_card['synergy_bonus']:.1f}")
                if best_card["synergy_reasons"]:
                    reasoning.extend([f"  - {reason}" for reason in best_card["synergy_reasons"][:2]])
            if best_card["archetype_bonus"] > 0:
                reasoning.append(f"アーキタイプ適合: +{best_card['archetype_bonus']:.1f}")
                if best_card["archetype_reasons"]:
                    reasoning.extend([f"  - {reason}" for reason in best_card["archetype_reasons"][:1]])
        
        confidence = min(95, max(50, abs(best_score - 60) + 50))
        
        return PickAdvice(
            action="reroll" if should_reroll else "pick",
            recommended_card_id=None if should_reroll else best_card["card_id"],
            recommended_card_name=None if should_reroll else best_card["name"],
            confidence=confidence,
            reasoning=reasoning,
            card_scores=card_scores
        )

    def get_deck_analysis_detailed(self, deck_input: str) -> Dict[str, Any]:
        """詳細なデッキ分析（シナジー・アーキタイプ対応）"""
        # 既存の分析を取得
        basic_analysis = super().get_deck_analysis_detailed(deck_input)
        
        deck_ids = []
        if deck_input.strip():
            deck_names = [name.strip() for name in deck_input.replace('、', ',').split(',') if name.strip()]
            for name in deck_names:
                card_id = self.resolver.resolve_card_id(name)
                if card_id:
                    deck_ids.append(card_id)
        
        # シナジー分析
        synergy_analysis = self.synergy_engine.analyze_deck_synergies(deck_ids)
        
        # アーキタイプ分析
        archetype_analysis = self.archetype_analyzer.analyze_deck_archetype(deck_ids)
        
        return {
            **basic_analysis,
            'synergy_analysis': synergy_analysis,
            'archetype_analysis': archetype_analysis
        }
