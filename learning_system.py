# learning_system.py
import sqlite3
import json
import numpy as np
from typing import Dict, List, Any, Optional
from weights_manager import WeightsManager
from config import DB_PATH

class LearningSystem:
    def __init__(self):
        self.db_path = DB_PATH
        self.weights_manager = WeightsManager()
    
    def collect_training_data(self) -> List[Dict[str, Any]]:
        """学習用データを収集"""
        training_data = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT chosen_id, scores_json, recommended_id
                FROM pick_logs 
                WHERE action = 'pick' AND chosen_id IS NOT NULL AND scores_json IS NOT NULL
            """)
            
            for chosen_id, scores_json, recommended_id in cursor.fetchall():
                try:
                    scores = json.loads(scores_json)
                    if len(scores) >= 2:
                        # ユーザーが選んだカードと推奨カードの特徴差分を計算
                        chosen_score = next((s for s in scores if s['card_id'] == chosen_id), None)
                        other_scores = [s for s in scores if s['card_id'] != chosen_id]
                        
                        if chosen_score and other_scores:
                            for other_score in other_scores:
                                # 特徴差分を計算（chosen - other）
                                feature_diff = {
                                    'base': chosen_score.get('base_score', 0) - other_score.get('base_score', 0),
                                    'curve': chosen_score.get('curve_bonus', 0) - other_score.get('curve_bonus', 0),
                                    'role': chosen_score.get('role_bonus', 0) - other_score.get('role_bonus', 0),
                                    'duplication': chosen_score.get('duplication_penalty', 0) - other_score.get('duplication_penalty', 0),
                                    'synergy': chosen_score.get('synergy_bonus', 0) - other_score.get('synergy_bonus', 0),
                                    'archetype': chosen_score.get('archetype_bonus', 0) - other_score.get('archetype_bonus', 0),
                                    'meta': chosen_score.get('meta_bonus', 0) - other_score.get('meta_bonus', 0)
                                }
                                
                                training_data.append({
                                    'features': feature_diff,
                                    'label': 1,  # ユーザーが選択
                                    'agreement': chosen_id == recommended_id
                                })
                
                except (json.JSONDecodeError, KeyError):
                    continue
        
        return training_data
    
    def optimize_weights(self, training_data: List[Dict[str, Any]]) -> Dict[str, float]:
        """重みを最適化"""
        if not training_data:
            return self.weights_manager.get_weights()
        
        # 特徴マトリックスとラベルを準備
        features = ['base', 'curve', 'role', 'duplication', 'synergy', 'archetype', 'meta']
        X = np.array([[sample['features'][f] for f in features] for sample in training_data])
        y = np.array([sample['label'] for sample in training_data])
        
        if len(X) < 5:  # 最小データ数
            return self.weights_manager.get_weights()
        
        # 簡易線形回帰（正則化付き）
        try:
            # L2正則化項を追加
            lambda_reg = 0.01
            XtX = X.T @ X + lambda_reg * np.eye(len(features))
            Xty = X.T @ y
            
            # 重み計算
            optimal_weights = np.linalg.solve(XtX, Xty)
            
            # 重みを正規化（極端な値を避ける）
            optimal_weights = np.clip(optimal_weights, 0.1, 3.0)
            
            # 辞書形式に変換
            new_weights = {features[i]: float(optimal_weights[i]) for i in range(len(features))}
            
            return new_weights
            
        except np.linalg.LinAlgError:
            # 数値的に不安定な場合は現在の重みを維持
            return self.weights_manager.get_weights()
    
    def train_and_update(self) -> Dict[str, Any]:
        """学習を実行し重みを更新"""
        training_data = self.collect_training_data()
        
        if not training_data:
            return {
                'success': False,
                'message': '学習用データが不足しています',
                'data_count': 0
            }
        
        # 現在の重み
        old_weights = self.weights_manager.get_weights()
        
        # 新しい重みを計算
        new_weights = self.optimize_weights(training_data)
        
        # 重みを更新
        self.weights_manager.update_weights(new_weights)
        
        # 統計情報
        agreement_rate = sum(1 for d in training_data if d['agreement']) / len(training_data)
        
        return {
            'success': True,
            'message': f'{len(training_data)}件のデータから学習しました',
            'data_count': len(training_data),
            'agreement_rate': round(agreement_rate * 100, 1),
            'weight_changes': {
                k: round(new_weights[k] - old_weights[k], 3) 
                for k in new_weights.keys()
            }
        }
