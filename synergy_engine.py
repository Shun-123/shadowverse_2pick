# synergy_engine.py
import sqlite3
import json
import re
from typing import Dict, List, Any, Tuple, Set
from dataclasses import dataclass

@dataclass
class SynergyRule:
    """シナジールールの定義"""
    name: str
    enabler_patterns: List[str]  # 基盤を提供するパターン
    payoff_patterns: List[str]   # 基盤を活用するパターン
    min_threshold: int           # 発動最小枚数
    max_bonus: float            # 最大ボーナス
    bonus_per_card: float       # カード1枚あたりのボーナス

class SynergyEngine:
    def __init__(self, db_path: str = "shadowverse_cards.db"):
        self.db_path = db_path
        self.synergy_rules = self._initialize_synergy_rules()

    def _initialize_synergy_rules(self) -> Dict[int, List[SynergyRule]]:
        """クラス別シナジールールを定義"""
        rules = {
            # 0: ニュートラル
            0: [
                SynergyRule("エンハンス", [r"エンハンス"], [r"エンハンス"], 2, 8, 2),
                SynergyRule("守護", [r"守護"], [r"守護"], 2, 6, 1.5),
            ],
            
            # 1: エルフ
            1: [
                SynergyRule("フェアリー", [r"フェアリー.*手札", r"フェアリー.*場"], 
                           [r"フェアリー", r"手札.*枚.*以上"], 3, 12, 3),
                SynergyRule("コンボ", [r"コンボ"], [r"コンボ_\d+"], 2, 15, 4),
                SynergyRule("自然", [r"ナチュラ"], [r"ナチュラ"], 2, 10, 3),
            ],
            
            # 2: ロイヤル
            2: [
                SynergyRule("兵士", [r"兵士.*場"], [r"兵士.*フォロワー"], 3, 12, 2.5),
                SynergyRule("指揮官", [r"指揮官"], [r"指揮官"], 2, 8, 2),
                SynergyRule("連携", [r"連携"], [r"連携"], 2, 10, 3),
            ],
            
            # 3: ウィッチ
            3: [
                SynergyRule("スペルブースト", [r"スペル"], [r"スペルブースト"], 4, 18, 3.5),
                SynergyRule("土の印", [r"土の印.*\+"], [r"土の秘術", r"土の印.*消費"], 3, 15, 4),
                SynergyRule("知恵の光", [r"知恵の光"], [r"知恵の光"], 2, 6, 2),
            ],
            
            # 4: ドラゴン
            4: [
                SynergyRule("覚醒", [r"PP.*増", r"PP.*回復"], [r"覚醒"], 2, 12, 4),
                SynergyRule("竜族", [r"ドラゴン.*フォロワー"], [r"ドラゴン.*フォロワー"], 3, 10, 2.5),
            ],
            
            # 5: ナイトメア
            5: [
                SynergyRule("ネクロマンス", [r"墓場"], [r"ネクロマンス"], 4, 15, 3),
                SynergyRule("ラストワード", [r"ラストワード"], [r"ラストワード"], 3, 10, 2.5),
                SynergyRule("リアニメイト", [r"リアニメイト"], [r"リアニメイト"], 2, 12, 4),
            ],
            
            # 6: ビショップ
            6: [
                SynergyRule("カウントダウン", [r"カウントダウン"], [r"カウントダウン"], 2, 10, 3),
                SynergyRule("守護", [r"守護"], [r"守護"], 3, 12, 2),
                SynergyRule("回復", [r"回復"], [r"回復"], 2, 6, 1.5),
            ],
            
            # 7: ネメシス
            7: [
                SynergyRule("アーティファクト", [r"アーティファクト.*手札", r"アーティファクト.*場"], 
                           [r"アーティファクト"], 3, 15, 3.5),
                SynergyRule("融合", [r"融合"], [r"融合"], 2, 12, 4),
                SynergyRule("共鳴", [r"共鳴"], [r"共鳴"], 2, 8, 3),
            ]
        }
        return rules

    def analyze_deck_synergies(self, card_ids: List[str]) -> Dict[str, Any]:
        """デッキのシナジー分析"""
        if not card_ids:
            return {"synergies": {}, "class_distribution": {}, "synergy_score": 0, "main_class": 0}

        # カード情報を取得
        cards = []
        class_counts = {}
        
        with sqlite3.connect(self.db_path) as conn:
            for card_id in card_ids:
                cursor = conn.execute("""
                    SELECT card_id, name, class_id, skill_text, evo_skill_text, keywords
                    FROM cards WHERE card_id = ?
                """, (card_id,))
                row = cursor.fetchone()
                if row:
                    card_data = {
                        'card_id': row[0],
                        'name': row[1],
                        'class_id': row[2],
                        'skill_text': row[3] or '',
                        'evo_skill_text': row[4] or '',
                        'keywords': json.loads(row[5] or '[]')
                    }
                    cards.append(card_data)
                    class_counts[row[2]] = class_counts.get(row[2], 0) + 1

        # 主要クラスを特定
        main_class = max(class_counts.keys(), key=lambda x: class_counts[x]) if class_counts else 0

        # シナジーカウント
        synergy_counts = {}
        
        # 主要クラスのルールを適用
        for rule in self.synergy_rules.get(main_class, []) + self.synergy_rules.get(0, []):
            enabler_count = 0
            payoff_count = 0
            
            for card in cards:
                full_text = f"{card['skill_text']} {card['evo_skill_text']}"
                
                # エネーブラー（基盤提供）をカウント
                for pattern in rule.enabler_patterns:
                    if re.search(pattern, full_text, re.IGNORECASE):
                        enabler_count += 1
                        break
                
                # ペイオフ（基盤活用）をカウント
                for pattern in rule.payoff_patterns:
                    if re.search(pattern, full_text, re.IGNORECASE):
                        payoff_count += 1
                        break

            if enabler_count > 0 or payoff_count > 0:
                synergy_counts[rule.name] = {
                    'enablers': enabler_count,
                    'payoffs': payoff_count,
                    'total': enabler_count + payoff_count
                }

        # 総合シナジースコア計算
        total_synergy_score = sum(
            min(data['total'] * 2, 10) for data in synergy_counts.values()
        )

        return {
            "synergies": synergy_counts,
            "class_distribution": class_counts,
            "synergy_score": total_synergy_score,
            "main_class": main_class
        }

    def calculate_synergy_bonus(self, candidate_card_id: str, 
                               deck_card_ids: List[str], 
                               pick_index: int) -> Tuple[float, List[str]]:
        """候補カードのシナジーボーナスを計算"""
        if not deck_card_ids:
            return 0.0, []

        # デッキシナジー分析
        deck_synergies = self.analyze_deck_synergies(deck_card_ids)
        main_class = deck_synergies["main_class"]

        # 候補カード情報取得
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT name, class_id, skill_text, evo_skill_text, keywords
                FROM cards WHERE card_id = ?
            """, (candidate_card_id,))
            row = cursor.fetchone()
            
            if not row:
                return 0.0, []
            
            candidate = {
                'name': row[0],
                'class_id': row[1],
                'skill_text': row[2] or '',
                'evo_skill_text': row[3] or '',
                'keywords': json.loads(row[4] or '[]')
            }

        total_bonus = 0.0
        reasons = []
        candidate_text = f"{candidate['skill_text']} {candidate['evo_skill_text']}"

        # 候補カードのクラスまたは主要クラスのルールを適用
        applicable_rules = (self.synergy_rules.get(candidate['class_id'], []) + 
                          self.synergy_rules.get(main_class, []) + 
                          self.synergy_rules.get(0, []))

        for rule in applicable_rules:
            synergy_data = deck_synergies["synergies"].get(rule.name)
            if not synergy_data:
                continue

            # このカードがルールに一致するかチェック
            is_enabler = any(re.search(pattern, candidate_text, re.IGNORECASE) 
                           for pattern in rule.enabler_patterns)
            is_payoff = any(re.search(pattern, candidate_text, re.IGNORECASE) 
                          for pattern in rule.payoff_patterns)

            if is_payoff and synergy_data['enablers'] >= rule.min_threshold:
                # ペイオフカード: 基盤が十分にある場合
                bonus = min(synergy_data['enablers'] * rule.bonus_per_card, rule.max_bonus)
                # ピック進行度による調整
                phase_modifier = 1.0 if pick_index <= 10 else 0.8
                bonus *= phase_modifier
                total_bonus += bonus
                reasons.append(f"{rule.name}活用 (+{bonus:.1f}点, 基盤{synergy_data['enablers']}枚)")
                
            elif is_enabler and synergy_data['payoffs'] > 0:
                # エネーブラー: ペイオフカードがある場合
                bonus = min(synergy_data['payoffs'] * (rule.bonus_per_card * 0.7), 
                          rule.max_bonus * 0.6)
                # 序盤ほど価値が高い
                phase_modifier = 1.2 if pick_index <= 6 else (1.0 if pick_index <= 10 else 0.6)
                bonus *= phase_modifier
                total_bonus += bonus
                reasons.append(f"{rule.name}基盤強化 (+{bonus:.1f}点)")

        return round(total_bonus, 1), reasons
