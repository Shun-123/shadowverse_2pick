import requests
import json
import time
import sqlite3
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class NormalizedCard:
    """正規化されたカードデータ"""
    card_id: str
    name: str
    class_id: int
    class_name: str
    cost: int
    card_type: str
    rarity: str
    attack: Optional[int] = None
    defense: Optional[int] = None
    evolved_attack: Optional[int] = None
    evolved_defense: Optional[int] = None
    skill_text: str = ""
    evo_skill_text: str = ""
    flavour_text: str = ""
    tribes: List[int] = field(default_factory=list)
    card_set_id: Optional[int] = None
    is_token: bool = False
    cv: str = ""
    illustrator: str = ""
    
    # 2Pick用拡張フィールド
    base_rating: float = 50.0
    roles: List[str] = field(default_factory=list)
    synergy_tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

def clean_html_text(text: str) -> str:
    """HTMLタグとルビを除去してクリーンなテキストを生成"""
    if not text:
        return ""
    
    # <ruby>タグの処理（漢字のみ残す）
    text = re.sub(r'<ruby[^>]*>([^<]+)<rt>.*?</rt></ruby>', r'\1', text)
    
    # その他のHTMLタグを除去
    text = re.sub(r'<[^>]+>', '', text)
    
    # 連続する空白を整理
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_keywords(text: str) -> List[str]:
    """スキルテキストからキーワードを抽出"""
    if not text:
        return []
    
    # <color=Keyword>で囲まれたキーワードを抽出
    keywords = re.findall(r'<color=Keyword>(.*?)</color>', text)
    return list(set(keywords))  # 重複除去

class ShadowverseCardFetcher:
    def __init__(self):
        # https://shadowverse-wb.com/web/CardList/cardList?offset=0&class=0,1,2,3,4,5,6,7&cost=0,1,2,3,4,5,6,7,8,9,10
        self.base_url = "https://shadowverse-wb.com/web/CardList/cardList"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9'
        })
        
        # 基本マッピング
        self.class_mapping = {
            0: "Neutral", 1: "Elf", 2: "Royal", 3: "Witch",
            4: "Dragon", 5: "Nightmare", 6: "Bishop", 7: "Nemesis"
        }
        
        self.type_mapping = {
            1: "follower", 2: "amulet", 3: "countdown_amulet", 4: "spell"
        }
        
        self.rarity_mapping = {
            1: "bronze", 2: "silver", 3: "gold", 4: "legendary"
        }
        
        # APIから取得するマッピング
        self.tribe_names = {}
        self.card_set_names = {}
        self.skill_names = {}

    def fetch_single_page(self, page: int) -> Optional[Dict[str, Any]]:
        """単一ページのデータを取得"""
        self.session.headers.update({'Referer': f'https://shadowverse-wb.com/ja/deck/cardslist/?page={page}&class=0,1,2,3,4,5,6,7&cost=0,1,2,3,4,5,6,7,8,9,10'})
        
        params = {
            'offset': 30 * (page - 1),
            'class': '0,1,2,3,4,5,6,7',
            'cost': '0,1,2,3,4,5,6,7,8,9,10'
        }
        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # レスポンス検証
            if not self._validate_response(data):
                logger.error(f"ページ {page}: 無効なレスポンス")
                return None
                
            return data
            
        except requests.RequestException as e:
            logger.error(f"ページ {page} 取得エラー: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"ページ {page} JSON解析エラー: {e}")
            return None
        except Exception as e:
            logger.error(e)

    def _validate_response(self, data: Dict[str, Any]) -> bool:
        """レスポンス構造を検証"""
        if not isinstance(data, dict):
            return False
        
        headers = data.get('data_headers', {})
        if headers.get('result_code') != 1:
            logger.warning(f"API エラー: result_code = {headers.get('result_code')}")
            return False
            
        return 'data' in data

    def fetch_all_cards(self) -> List[Dict[str, Any]]:
        """全カードデータを取得"""
        all_cards = []
        page = 1
        max_pages = 100  # 安全装置
        consecutive_empty = 0
        
        logger.info("カードデータ取得開始...")
        
        while page <= max_pages and consecutive_empty < 3:
            logger.info(f"ページ {page} 処理中...")
            
            response_data = self.fetch_single_page(page)
            if not response_data:
                consecutive_empty += 1
                page += 1
                time.sleep(1)
                continue
            
            data = response_data.get('data', {})
            
            # 初回のみマッピング情報を取得
            if page == 1:
                self.tribe_names = {int(k): v for k, v in data.get('tribe_names', {}).items()}
                self.card_set_names = {int(k): v for k, v in data.get('card_set_names', {}).items()}
                self.skill_names = {int(k): v for k, v in data.get('skill_names', {}).items()}
                
                total_count = data.get('count', 0)
                logger.info(f"総カード数: {total_count}")
            
            # カードデータを抽出
            card_details = data.get('card_details', {})
            sort_card_ids = data.get('sort_card_id_list', [])
            
            if not sort_card_ids:
                logger.info("カードリスト終了")
                break
            
            page_cards = []
            for card_id in sort_card_ids:
                card_id_str = str(card_id)
                if card_id_str in card_details:
                    card_info = card_details[card_id_str]
                    if 'common' in card_info:
                        page_cards.append(card_info)
            
            if page_cards:
                all_cards.extend(page_cards)
                consecutive_empty = 0
                logger.info(f"ページ {page}: {len(page_cards)}枚取得 (累計: {len(all_cards)}枚)")
            else:
                consecutive_empty += 1
            
            page += 1
            time.sleep(0.5)  # レート制限対策
        
        logger.info(f"取得完了: 合計 {len(all_cards)} 枚")
        return all_cards

class CardDataProcessor:
    def __init__(self, fetcher: ShadowverseCardFetcher):
        self.class_mapping = fetcher.class_mapping
        self.type_mapping = fetcher.type_mapping
        self.rarity_mapping = fetcher.rarity_mapping
        self.tribe_names = fetcher.tribe_names
        
        # 役割判定パターン（2Pick用）
        self.role_patterns = {
            'removal': [
                r'破壊', r'消滅', r'ダメージ.*与える', r'選ぶ.*破壊'
            ],
            'draw': [
                r'カードを.*引く', r'ドロー', r'手札に加える'
            ],
            'heal': [
                r'回復', r'体力.*回復'
            ],
            'aoe': [
                r'すべての.*フォロワー', r'全ての.*フォロワー'
            ],
            'finisher': [
                r'リーダー.*ダメージ'
            ],
            'protection': [
                r'守護', r'バリア'
            ]
        }
        
        # シナジータグパターン
        self.synergy_patterns = {
            'spellboost': [r'スペルブースト'],
            'earth_rite': [r'土の印', r'土の秘術'],
            'combo': [r'コンボ'],
            'necromancy': [r'ネクロマンス'],
            'enhance': [r'エンハンス'],
            'fusion': [r'融合'],
            'awakening': [r'覚醒']
        }

    def normalize_card(self, raw_card: Dict[str, Any]) -> Optional[NormalizedCard]:
        """カードデータを正規化"""
        try:
            common = raw_card.get('common', {})
            evo = raw_card.get('evo', {})
            
            # 必須フィールドの確認
            card_id = common.get('card_id')
            name = common.get('name')
            class_id = common.get('class')
            cost = common.get('cost')
            
            if not all([card_id, name, class_id is not None, cost is not None]):
                logger.warning(f"必須フィールド不足: {name or 'Unknown'}")
                return None
            
            # 基本情報の抽出
            class_name = self.class_mapping.get(class_id, "Unknown")
            card_type = self.type_mapping.get(common.get('type', 1), "unknown")
            rarity = self.rarity_mapping.get(common.get('rarity', 1), "bronze")
            
            # テキスト処理
            skill_text_raw = common.get('skill_text', '')
            skill_text = clean_html_text(skill_text_raw)
            evo_skill_text = clean_html_text(evo.get('skill_text', '')) if isinstance(evo, dict) else ''
            flavour_text = clean_html_text(common.get('flavour_text', ''))
            
            # キーワード抽出
            keywords = extract_keywords(skill_text_raw)
            if isinstance(evo, dict) and evo.get('skill_text'):
                keywords.extend(extract_keywords(evo.get('skill_text', '')))
            keywords = list(set(keywords))  # 重複除去
            
            # カード作成
            card = NormalizedCard(
                card_id=str(card_id),
                name=name,
                class_id=class_id,
                class_name=class_name,
                cost=cost,
                card_type=card_type,
                rarity=rarity,
                attack=common.get('atk'),
                defense=common.get('life'),
                evolved_attack=evo.get('atk') if isinstance(evo, dict) else None,
                evolved_defense=evo.get('life') if isinstance(evo, dict) else None,
                skill_text=skill_text,
                evo_skill_text=evo_skill_text,
                flavour_text=flavour_text,
                tribes=common.get('tribes', []),
                card_set_id=common.get('card_set_id'),
                is_token=common.get('is_token', False),
                cv=common.get('cv', ''),
                illustrator=common.get('illustrator', ''),
                keywords=keywords
            )
            
            # 役割とシナジーの分析
            card.roles = self._analyze_roles(skill_text + ' ' + evo_skill_text)
            card.synergy_tags = self._analyze_synergies(skill_text + ' ' + evo_skill_text, keywords)
            
            return card
            
        except Exception as e:
            logger.error(f"カード正規化エラー: {e}")
            return None

    def _analyze_roles(self, text: str) -> List[str]:
        """役割を分析"""
        roles = []
        text_lower = text.lower()
        
        for role, patterns in self.role_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    roles.append(role)
                    break
        
        return roles

    def _analyze_synergies(self, text: str, keywords: List[str]) -> List[str]:
        """シナジーを分析"""
        synergies = []
        
        # テキストパターンから
        for synergy, patterns in self.synergy_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    synergies.append(synergy)
                    break
        
        # キーワードから直接
        keyword_synergies = {
            'ファンファーレ': 'fanfare',
            'ラストワード': 'lastword',
            '守護': 'ward',
            '疾走': 'storm',
            '突進': 'rush'
        }
        
        for keyword in keywords:
            if keyword in keyword_synergies:
                synergies.append(keyword_synergies[keyword])
        
        return list(set(synergies))

class CardDatabase:
    def __init__(self, db_path: str = "shadowverse_cards.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """データベース初期化"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    card_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    class_id INTEGER NOT NULL,
                    class_name TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    card_type TEXT NOT NULL,
                    rarity TEXT,
                    attack INTEGER,
                    defense INTEGER,
                    evolved_attack INTEGER,
                    evolved_defense INTEGER,
                    skill_text TEXT,
                    evo_skill_text TEXT,
                    flavour_text TEXT,
                    tribes TEXT,  -- JSON
                    card_set_id INTEGER,
                    is_token BOOLEAN,
                    cv TEXT,
                    illustrator TEXT,
                    base_rating REAL DEFAULT 50.0,
                    roles TEXT,  -- JSON
                    synergy_tags TEXT,  -- JSON
                    keywords TEXT,  -- JSON
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # インデックス作成
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_class_cost ON cards (class_id, cost)",
                "CREATE INDEX IF NOT EXISTS idx_card_type ON cards (card_type)",
                "CREATE INDEX IF NOT EXISTS idx_rarity ON cards (rarity)",
                "CREATE INDEX IF NOT EXISTS idx_is_token ON cards (is_token)"
            ]
            
            for index_sql in indexes:
                conn.execute(index_sql)
            
            conn.commit()
    
    def insert_cards(self, cards: List[NormalizedCard]):
        """カードデータ一括挿入"""
        with sqlite3.connect(self.db_path) as conn:
            for card in cards:
                conn.execute("""
                    INSERT OR REPLACE INTO cards 
                    (card_id, name, class_id, class_name, cost, card_type, rarity,
                     attack, defense, evolved_attack, evolved_defense,
                     skill_text, evo_skill_text, flavour_text, tribes, card_set_id,
                     is_token, cv, illustrator, base_rating, roles, synergy_tags, keywords,
                     updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    card.card_id, card.name, card.class_id, card.class_name,
                    card.cost, card.card_type, card.rarity, card.attack, card.defense,
                    card.evolved_attack, card.evolved_defense, card.skill_text,
                    card.evo_skill_text, card.flavour_text, json.dumps(card.tribes),
                    card.card_set_id, card.is_token, card.cv, card.illustrator,
                    card.base_rating, json.dumps(card.roles), json.dumps(card.synergy_tags),
                    json.dumps(card.keywords)
                ))
            
            conn.commit()
            logger.info(f"{len(cards)} 枚のカードを保存")

    def get_cards_by_class_cost(self, class_id: int, cost: int) -> List[Dict[str, Any]]:
        """クラスとコストでカード検索（2Pick用）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM cards 
                WHERE class_id IN (0, ?) AND cost = ? AND is_token = 0
                ORDER BY base_rating DESC
            """, (class_id, cost))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

def main():
    """メイン実行関数"""
    try:
        # Step 1: データ取得
        fetcher = ShadowverseCardFetcher()
        raw_cards = fetcher.fetch_all_cards()
        
        if not raw_cards:
            logger.error("カードデータが取得できませんでした")
            return
        
        # バックアップ保存
        backup_file = f"raw_cards_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(raw_cards, f, ensure_ascii=False, indent=2)
        logger.info(f"バックアップ保存: {backup_file}")
        
        # Step 2: データ正規化
        processor = CardDataProcessor(fetcher)
        normalized_cards = []
        failed_count = 0
        
        for raw_card in raw_cards:
            normalized = processor.normalize_card(raw_card)
            if normalized:
                normalized_cards.append(normalized)
            else:
                failed_count += 1
        
        logger.info(f"正規化完了: {len(normalized_cards)} 枚 (失敗: {failed_count} 枚)")
        
        # Step 3: データベース保存
        db = CardDatabase()
        db.insert_cards(normalized_cards)
        
        # Step 4: 統計表示
        display_statistics(db)
        
        logger.info("データベース構築完了!")
        
    except Exception as e:
        logger.error(f"エラー発生: {e}")
        import traceback
        traceback.print_exc()
        raise

def display_statistics(db: CardDatabase):
    """統計情報表示"""
    with sqlite3.connect(db.db_path) as conn:
        # 基本統計
        total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        tokens = conn.execute("SELECT COUNT(*) FROM cards WHERE is_token = 1").fetchone()[0]
        regular = total - tokens
        
        logger.info(f"=== データベース統計 ===")
        logger.info(f"総カード数: {total}")
        logger.info(f"通常カード: {regular}")
        logger.info(f"トークン: {tokens}")
        
        # クラス別統計
        class_stats = conn.execute("""
            SELECT class_name, COUNT(*) as count 
            FROM cards WHERE is_token = 0
            GROUP BY class_name ORDER BY count DESC
        """).fetchall()
        
        logger.info("=== クラス別カード数 ===")
        for class_name, count in class_stats:
            logger.info(f"{class_name}: {count} 枚")
        
        # コスト分布
        cost_stats = conn.execute("""
            SELECT cost, COUNT(*) as count 
            FROM cards WHERE is_token = 0
            GROUP BY cost ORDER BY cost
        """).fetchall()
        
        logger.info("=== コスト分布 ===")
        for cost, count in cost_stats:
            logger.info(f"コスト {cost}: {count} 枚")

if __name__ == "__main__":
    main()
