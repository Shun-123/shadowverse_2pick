# enhanced_advisor.py
from pick_advisor import TwoPickAdvisor, PickAdvice
from card_resolver import CardResolver
from synergy_engine import SynergyEngine
from archetype_analyzer import ArchetypeAnalyzer
import sqlite3
import json
from typing import Dict, List, Any, Optional
from meta_adjustments import get_meta_adjustments, get_meta_info
from weights_manager import WeightsManager
import config

class EnhancedTwoPickAdvisor(TwoPickAdvisor):
    def __init__(self, db_path: str = config.DB_PATH):
        super().__init__(db_path)
        self.resolver = CardResolver(db_path)
        self.synergy_engine = SynergyEngine(db_path)
        self.archetype_analyzer = ArchetypeAnalyzer(db_path)
        self.weights_manager = WeightsManager()  # 追加
        
        # メタ調整情報を読み込み
        from meta_adjustments import get_meta_adjustments, get_meta_info
        self.meta_adjustments = get_meta_adjustments()
        self.meta_info = get_meta_info()

    
    def _calculate_meta_bonus(self, card: Dict[str, Any], 
                            detected_archetype: Optional[str], 
                            deck_class_name: str) -> float:
        """メタ調整ボーナスを計算"""
        bonus = 0.0
        
        # カードID直接調整
        if card['card_id'] in self.meta_adjustments.get('card_id', {}):
            bonus += self.meta_adjustments['card_id'][card['card_id']]
        
        # アーキタイプ調整
        if detected_archetype and detected_archetype in self.meta_adjustments.get('archetype', {}):
            bonus += self.meta_adjustments['archetype'][detected_archetype]
        
        # クラス調整（候補カードのクラスがデッキの主要クラスと一致する場合）
        card_class_name = card['class_name']
        if card_class_name == deck_class_name and card_class_name in self.meta_adjustments.get('class_name', {}):
            bonus += self.meta_adjustments['class_name'][card_class_name]
        elif card_class_name == 'Neutral' and deck_class_name in self.meta_adjustments.get('class_name', {}):
            # ニュートラルカードはデッキクラスの半分の調整を受ける
            bonus += self.meta_adjustments['class_name'][deck_class_name] * 0.5
        
        return round(bonus, 1)
        
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
        """メタ調整を含む拡張アドバイス"""
        deck_analysis = self.analyze_deck(current_deck_ids)
        
        # デッキの主要クラスとアーキタイプを事前取得
        synergy_analysis = self.synergy_engine.analyze_deck_synergies(current_deck_ids)
        archetype_analysis = self.archetype_analyzer.analyze_deck_archetype(current_deck_ids)
        
        # 主要クラス名を取得
        main_class_id = synergy_analysis.get("main_class", 0)
        class_mapping = {0: "Neutral", 1: "Elf", 2: "Royal", 3: "Witch", 4: "Dragon", 5: "Nightmare", 6: "Bishop", 7: "Nemesis"}
        deck_class_name = class_mapping.get(main_class_id, "Neutral")
        detected_archetype = archetype_analysis.get("detected_archetype")
        
        card_scores = []
        weights = self.weights_manager.get_weights() 
        
        # 各候補カードを評価
        for card_id in candidate_card_ids:
            card = self.get_card_info(card_id)
            if not card:
                continue
            
            # 基本評価
            base_score = card.get("base_rating", 50.0)
            curve_bonus = self.calculate_curve_bonus(card["cost"], deck_analysis, pick_index)
            role_bonus = self.calculate_role_bonus(card["roles"], deck_analysis)
            
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
            
            # メタボーナス（新規追加）
            meta_bonus = self._calculate_meta_bonus(card, detected_archetype, deck_class_name)
            
            final_score = (
                weights.get("base", 1.0) * base_score +
                weights.get("curve", 1.0) * curve_bonus +
                weights.get("role", 1.0) * role_bonus +
                weights.get("duplication", 1.0) * duplication_penalty +
                weights.get("synergy", 1.0) * synergy_bonus +
                weights.get("archetype", 1.0) * archetype_bonus +
                weights.get("meta", 1.0) * meta_bonus
            )
            
            card_scores.append({
                "card_id": card_id,
                "name": card["name"],
                "cost": card["cost"],
                "base_score": base_score,
                "curve_bonus": curve_bonus,
                "role_bonus": role_bonus,
                "duplication_penalty": duplication_penalty,
                "synergy_bonus": synergy_bonus,
                "archetype_bonus": archetype_bonus,
                "meta_bonus": meta_bonus,  # 新規追加
                "final_score": final_score,
                "synergy_reasons": synergy_reasons,
                "archetype_reasons": archetype_reasons
            })
        
        if not card_scores:
            return PickAdvice("pick", None, None, 0, ["評価可能なカードがありません"], [])
        
        # 最高スコアのカードを特定
        best_card = max(card_scores, key=lambda x: x["final_score"])
        best_score = best_card["final_score"]
        
        # リロール判断
        threshold = self.calculate_reroll_threshold(pick_index, rerolls_left, deck_analysis)
        should_reroll = rerolls_left > 0 and best_score < threshold
        
        # 推奨理由を生成（メタ調整対応）
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
            if best_card["meta_bonus"] != 0:  # 新規追加
                reasoning.append(f"メタ環境調整: {best_card['meta_bonus']:+.1f}")
        
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
        deck_ids = []
        unresolved = []
        
        if deck_input.strip():
            deck_names = [name.strip() for name in deck_input.replace('、', ',').split(',') if name.strip()]
            for name in deck_names:
                card_id = self.resolver.resolve_card_id(name)
                if card_id:
                    deck_ids.append(card_id)
                else:
                    unresolved.append(name)
        
        basic_analysis = self.analyze_deck(deck_ids)
        
        # 追加分析
        card_details = []
        total_rating = 0
        class_distribution = {}
        type_distribution = {}
        
        for card_id in deck_ids:
            card = self.get_card_info(card_id)
            if card:
                card_details.append(card)
                total_rating += card.get('base_rating', 50)
                
                class_name = card['class_name']
                class_distribution[class_name] = class_distribution.get(class_name, 0) + 1
                
                card_type = card['card_type']
                type_distribution[card_type] = type_distribution.get(card_type, 0) + 1
        
        # 評価とアドバイス
        avg_rating = total_rating / len(card_details) if card_details else 50
        strength_assessment = self._assess_deck_strength(avg_rating, basic_analysis)
        recommendations = self._generate_recommendations(basic_analysis, card_details)
        
        # シナジー分析
        synergy_analysis = self.synergy_engine.analyze_deck_synergies(deck_ids)
        
        # アーキタイプ分析
        archetype_analysis = self.archetype_analyzer.analyze_deck_archetype(deck_ids)
        
        return {
            **basic_analysis,
            'avg_rating': round(avg_rating, 1),
            'strength_assessment': strength_assessment,
            'class_distribution': class_distribution,
            'type_distribution': type_distribution,
            'recommendations': recommendations,
            'unresolved_cards': unresolved,
            'card_details': card_details[:10],
            'synergy_analysis': synergy_analysis,
            'archetype_analysis': archetype_analysis
        }

    def _assess_deck_strength(self, avg_rating: float, analysis: Dict) -> Dict[str, Any]:
        """デッキ強度を評価"""
        curve = analysis['curve']
        early_game = sum(curve.get(i, 0) for i in [1, 2, 3])
        
        # カーブペナルティ
        curve_penalty = max(0, 8 - early_game) * 2
        adjusted_rating = avg_rating - curve_penalty
        
        if adjusted_rating >= 70:
            tier = "S"
            description = "非常に強力なデッキです"
        elif adjusted_rating >= 65:
            tier = "A"
            description = "強いデッキです"
        elif adjusted_rating >= 60:
            tier = "B"
            description = "バランスの取れたデッキです"
        elif adjusted_rating >= 55:
            tier = "C"
            description = "改善の余地があります"
        else:
            tier = "D"
            description = "大幅な改善が必要です"
        
        return {
            'tier': tier,
            'adjusted_rating': round(adjusted_rating, 1),
            'description': description,
            'curve_penalty': curve_penalty
        }

    def _generate_recommendations(self, analysis: Dict, cards: List[Dict]) -> List[str]:
        """改善提案を生成"""
        recommendations = []
        curve = analysis['curve']
        roles = analysis['roles']
        
        # カーブ分析
        early_cards = sum(curve.get(i, 0) for i in [1, 2, 3])
        if early_cards < 8:
            recommendations.append(f"序盤カード（1-3コスト）を増やしましょう（現在{early_cards}枚）")
        
        heavy_cards = sum(curve.get(i, 0) for i in [6, 7, 8, 9, 10])
        if heavy_cards > 4:
            recommendations.append(f"重いカード（6コスト以上）を減らしましょう（現在{heavy_cards}枚）")
        
        # 役割分析
        if roles.get('removal', 0) < 3:
            recommendations.append("除去手段を増やしましょう")
        
        if roles.get('finisher', 0) == 0:
            recommendations.append("フィニッシャーとなるカードを追加しましょう")
        
        # 戦略提案
        avg_cost = sum(cost * count for cost, count in curve.items()) / max(1, sum(curve.values()))
        if avg_cost < 3.5:
            recommendations.append("アグロ戦略: 序盤から積極的に攻めましょう")
        elif avg_cost > 4.5:
            recommendations.append("コントロール戦略: リソース管理を重視しましょう")
        else:
            recommendations.append("ミッドレンジ戦略: テンポを重視しましょう")
        
        return recommendations
