# weights_manager.py
import json
import os
from typing import Dict, Any
from config import WEIGHTS_FILE, DEFAULT_WEIGHTS

class WeightsManager:
    def __init__(self):
        self.weights_file = WEIGHTS_FILE
        self.weights = self._load_weights()
    
    def _load_weights(self) -> Dict[str, float]:
        """重み設定を読み込み"""
        if os.path.exists(self.weights_file):
            try:
                with open(self.weights_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('weights', DEFAULT_WEIGHTS['weights'])
            except (json.JSONDecodeError, KeyError) as e:
                print(f"重み設定読み込みエラー: {e}")
                return DEFAULT_WEIGHTS['weights']
        else:
            # 初期ファイル作成
            self._save_weights(DEFAULT_WEIGHTS['weights'])
            return DEFAULT_WEIGHTS['weights']
    
    def _save_weights(self, weights: Dict[str, float]):
        """重み設定を保存"""
        data = {
            "version": DEFAULT_WEIGHTS['version'],
            "weights": weights
        }
        with open(self.weights_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_weights(self) -> Dict[str, float]:
        """現在の重みを取得"""
        return self.weights.copy()
    
    def update_weights(self, new_weights: Dict[str, float]):
        """重みを更新"""
        self.weights.update(new_weights)
        self._save_weights(self.weights)
    
    def reset_to_default(self):
        """デフォルト重みにリセット"""
        self.weights = DEFAULT_WEIGHTS['weights'].copy()
        self._save_weights(self.weights)
