# win_predictor.py
import sqlite3
import json
import math
from typing import Dict, List, Any
from config import DB_PATH

class WinRatePredictor:
    def __init__(self):
        self.db_path = DB_PATH
        
        # 勝率要因の重み（経験値ベース）
        self.factors = {
            'avg_rating': 0.30,      # 平均カード評価
            'curve_quality': 0.25,   # マナカーブの質
            'synergy_strength': 0.20, # シナジー強度
            'role_coverage': 0.15,   # 役割カバー率
            'consistency': 0.10      # デッキの一貫性
        }
    
    def predict_win_rate(self, deck_card_ids: List[str], 
                        deck_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """勝率を予測"""
        
        if not deck_card_ids:
            return {'win_rate': 50.0, 'confidence': 0, 'factors': {}}
        
        factors = {}
        
        # 1. 平均評価値
        avg_rating = deck_analysis.get('avg_rating', 50)
        factors['avg_rating'] = self._normalize_rating(avg_rating)
        
        # 2. マナカーブの質
        factors['curve_quality'] = self._evaluate_curve_quality(deck_analysis.get('curve', {}))
        
        # 3. シナジー強度
        synergy_score = deck_analysis.get('synergy_analysis', {}).get('synergy_score', 0)
        factors['synergy_strength'] = min(synergy_score / 20, 1.0)
        
        # 4. 役割カバー率
        factors['role_coverage'] = self._evaluate_role_coverage(deck_analysis.get('roles', {}))
        
        # 5. 一貫性
        factors['consistency'] = self._evaluate_consistency(deck_card_ids)
        
        # 重み付き合計
        weighted_score = sum(factors[k] * self.factors[k] for k in factors.keys())
        
        # 勝率に変換（35-75%の範囲）
        win_rate = 35 + (weighted_score * 40)
        win_rate = max(25, min(85, win_rate))
        
        # 信頼度（デッキサイズに基づく）
        confidence = min(100, len(deck_card_ids) * 4)
        
        return {
            'win_rate': round(win_rate, 1),
            'confidence': confidence,
            'factors': {k: round(v, 2) for k, v in factors.items()},
            'recommendations': self._generate_recommendations(factors)
        }
    
    def _normalize_rating(self, rating: float) -> float:
        """評価値を0-1に正規化"""
        return max(0, min(1, (rating - 40) / 30))
    
    def _evaluate_curve_quality(self, curve: Dict[int, int]) -> float:
        """マナカーブの質を評価"""
        ideal = {1: 4, 2: 6, 3: 6, 4: 5, 5: 4, 6: 2}
        total_cards = sum(curve.values())
        
        if total_cards == 0:
            return 0.5
        
        quality = 0
        for cost, ideal_count in ideal.items():
            current = curve.get(cost, 0)
            expected = ideal_count * (total_cards / 30)
            
            # 理想との差が小さいほど高評価
            diff = abs(current - expected)
            cost_quality = max(0, 1 - diff / 3)
            quality += cost_quality
        
        return quality / len(ideal)
    
    def _evaluate_role_coverage(self, roles: Dict[str, int]) -> float:
        """役割カバー率を評価"""
        important_roles = {'removal': 3, 'draw': 2, 'finisher': 2, 'protection': 2}
        coverage = 0
        
        for role, target in important_roles.items():
            current = roles.get(role, 0)
            coverage += min(current / target, 1.0)
        
        return coverage / len(important_roles)
    
    def _evaluate_consistency(self, deck_card_ids: List[str]) -> float:
        """デッキの一貫性を評価"""
        if not deck_card_ids:
            return 0.5
        
        # 重複カードの評価
        card_counts = {}
        for card_id in deck_card_ids:
            card_counts[card_id] = card_counts.get(card_id, 0) + 1
        
        duplicates = sum(1 for count in card_counts.values() if count >= 2)
        duplicate_score = min(duplicates / 4, 1.0)
        
        return duplicate_score
    
    def _generate_recommendations(self, factors: Dict[str, float]) -> List[str]:
        """改善推奨を生成"""
        recommendations = []
        
        if factors['avg_rating'] < 0.6:
            recommendations.append("より高評価のカードを優先しましょう")
        
        if factors['curve_quality'] < 0.6:
            recommendations.append("マナカーブを改善しましょう（特に2-4コスト）")
        
        if factors['synergy_strength'] < 0.4:
            recommendations.append("シナジーを意識したカード選択を心がけましょう")
        
        if factors['role_coverage'] < 0.6:
            recommendations.append("除去・ドロー・フィニッシャーのバランスを改善しましょう")
        
        if not recommendations:
            recommendations.append("バランスの取れた強力なデッキです！")
        
        return recommendations
