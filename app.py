# app.py
from flask import Flask, render_template, request, jsonify, Response
import json
import logging
import subprocess
import os
from config import DB_PATH, CLASS_NAMES, LOG_FILE, LOG_LEVEL, APP_CONFIG
from enhanced_advisor import EnhancedTwoPickAdvisor
from card_resolver import CardResolver
from learning_system import LearningSystem
from win_predictor import WinRatePredictor


# ログ設定
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# システム初期化
advisor = EnhancedTwoPickAdvisor(db_path=DB_PATH)
resolver = CardResolver(db_path=DB_PATH)
learning_system = LearningSystem()
win_predictor = WinRatePredictor()

logger.info("シャドウバース 2Pickアドバイザー起動")


@app.route('/')
def index():
    """トップページ"""
    return render_template('index.html')

@app.route('/api/search_suggestions')
def search_suggestions():
    """検索候補API"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    suggestions = resolver.get_suggestions(query, limit=8)
    
    # クラス名を追加
    for suggestion in suggestions:
        suggestion['class_name'] = CLASS_NAMES.get(suggestion['class_id'], '不明')
    
    return jsonify(suggestions)

@app.route('/search', methods=['GET', 'POST'])
def card_search():
    """カード検索ページ"""
    card_info = None
    error_message = None
    
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if query:
            card_id = resolver.resolve_card_id(query)
            if card_id:
                card = advisor.get_card_info(card_id)
                if card:
                    # メトリクス情報も取得
                    with sqlite3.connect(DB_PATH) as conn:
                        cursor = conn.execute(
                            "SELECT base_rating, stat_efficiency, role_score, keyword_score, impact_score FROM card_metrics WHERE card_id = ?",
                            (card_id,)
                        )
                        metrics = cursor.fetchone()
                    
                    card_info = {
                        'basic': card,
                        'metrics': {
                            'base_rating': round(metrics[0], 1) if metrics and metrics[0] is not None else 50.0,
                            'stat_efficiency': round(metrics[1], 1) if metrics and metrics[1] is not None else 0.0,
                            'role_score': round(metrics[2], 1) if metrics and metrics[2] is not None else 0.0,
                            'keyword_score': round(metrics[3], 1) if metrics and metrics[3] is not None else 0.0,
                            'impact_score': round(metrics[4], 1) if metrics and metrics[4] is not None else 0.0
                        },
                        'class_display': CLASS_NAMES.get(card['class_id'], '不明')
                    }
                else:
                    error_message = "カード情報の取得に失敗しました"
            else:
                error_message = f"カード '{query}' が見つかりませんでした"
    
    return render_template('search.html', card_info=card_info, error_message=error_message)

@app.route('/advice', methods=['GET', 'POST'])
def pick_advice():
    """2Pickアドバイスページ"""
    advice_result = None
    error_message = None
    
    if request.method == 'POST':
        try:
            candidate1 = request.form.get('candidate1', '').strip()
            candidate2 = request.form.get('candidate2', '').strip()
            deck_input = request.form.get('deck_input', '').strip()
            pick_index = int(request.form.get('pick_index', 1))
            rerolls_left = int(request.form.get('rerolls_left', 2))
            
            if not candidate1 or not candidate2:
                error_message = "候補カード2枚を入力してください"
            else:
                result = advisor.get_pick_advice_by_names(
                    candidate1=candidate1,
                    candidate2=candidate2,
                    deck_input=deck_input,
                    pick_index=pick_index,
                    rerolls_left=rerolls_left
                )
                
                if 'error' in result:
                    error_message = result['error']
                else:
                    advice = result['advice']
                    advice_result = {
                        'action': advice.action,
                        'action_text': 'リロール推奨' if advice.action == 'reroll' else f'{advice.recommended_card_name} を選択',
                        'confidence': round(advice.confidence, 1),
                        'reasoning': advice.reasoning,
                        'card_scores': advice.card_scores,
                        'deck_info': f"デッキ: {result['resolved_deck_count']}/{result['original_deck_count']}枚解決",
                        'recommended_card_id': getattr(advice, 'recommended_card_id', '')
                    }
                
        except ValueError:
            error_message = "ピック番号とリロール回数は数値で入力してください"
        except Exception as e:
            error_message = f"エラーが発生しました: {str(e)}"
    
    return render_template('advice.html', advice_result=advice_result, error_message=error_message, advisor=advisor)

@app.route('/deck_analyzer', methods=['GET', 'POST'])
def deck_analyzer():
    """デッキ分析ページ"""
    analysis_result = None
    error_message = None
    
    if request.method == 'POST':
        try:
            deck_input = request.form.get('deck_input', '').strip()
            if not deck_input:
                error_message = "デッキ内容を入力してください"
            else:
                analysis_result = advisor.get_deck_analysis_detailed(deck_input)
                
        except Exception as e:
            error_message = f"エラーが発生しました: {str(e)}"
    
    return render_template('deck_analyzer.html', analysis_result=analysis_result, error_message=error_message)

@app.route('/meta_info')
def meta_info():
    """メタ情報表示ページ"""
    meta = get_meta_info()
    adjustments = advisor.meta_adjustments
    
    return render_template('meta_info.html', 
                         meta_info=meta, 
                         adjustments=adjustments)
                         
@app.route('/system_stats')
def system_stats():
    """システム統計ページ"""
    cache_stats = advisor.get_cache_stats()
    
    # データベース統計
    with sqlite3.connect(advisor.db_path) as conn:
        total_cards = conn.execute("SELECT COUNT(*) FROM cards WHERE is_token = 0").fetchone()[0]
        total_metrics = conn.execute("SELECT COUNT(*) FROM card_metrics").fetchone()[0]
    
    stats = {
        'database': {
            'total_cards': total_cards,
            'total_metrics': total_metrics
        },
        'cache': cache_stats,
        'meta_info': get_meta_info()
    }
    
    return render_template('system_stats.html', stats=stats)

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """キャッシュクリアAPI"""
    try:
        card_info_cache.clear()
        return jsonify({'success': True, 'message': 'キャッシュをクリアしました'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
        
@app.route('/api/log_pick', methods=['POST'])
def api_log_pick():
    """ピック選択をログに記録"""
    data = request.json or {}
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # セッション確認・作成
            session_id = data.get('session_id')
            if session_id:
                cursor = conn.execute(
                    "SELECT session_id FROM pick_sessions WHERE session_id = ?",
                    (session_id,)
                )
                if not cursor.fetchone():
                    conn.execute(
                        "INSERT INTO pick_sessions (session_id) VALUES (?)",
                        (session_id,)
                    )
            
            # ピックログ記録
            conn.execute("""
                INSERT INTO pick_logs 
                (session_id, pick_index, rerolls_left, candidate1_id, candidate2_id,
                 recommended_id, chosen_id, action, scores_json, deck_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                data.get('pick_index'),
                data.get('rerolls_left'),
                data.get('candidate1_id'),
                data.get('candidate2_id'),
                data.get('recommended_id'),
                data.get('chosen_id'),
                data.get('action'),
                json.dumps(data.get('scores', []), ensure_ascii=False),
                json.dumps(data.get('deck_snapshot', []), ensure_ascii=False)
            ))
            
            conn.commit()
            
        logger.info(f"ピック記録保存: session={session_id}, action={data.get('action')}")
        return jsonify({"success": True})
        
    except Exception as e:
        logger.error(f"ピック記録保存エラー: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/train_weights', methods=['POST'])
def api_train_weights():
    """重み学習を実行"""
    try:
        result = learning_system.train_and_update()
        logger.info(f"重み学習実行: {result}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"重み学習エラー: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/win_prediction', methods=['GET', 'POST'])
def win_prediction():
    """勝率予測ページ"""
    prediction_result = None
    
    if request.method == 'POST':
        deck_input = request.form.get('deck_input', '').strip()
        if deck_input:
            # デッキ分析
            analysis = advisor.get_deck_analysis_detailed(deck_input)
            
            # カードIDリスト作成
            deck_ids = []
            deck_names = [name.strip() for name in deck_input.replace('、', ',').split(',')]
            for name in deck_names:
                card_id = advisor.resolver.resolve_card_id(name)
                if card_id:
                    deck_ids.append(card_id)
            
            # 勝率予測
            prediction = win_predictor.predict_win_rate(deck_ids, analysis)
            prediction_result = prediction
    
    return render_template('win_prediction.html', prediction_result=prediction_result)

@app.route('/update_card_data', methods=['POST'])
def update_card_data():
    """カードデータ更新処理"""
    logger.info("カードデータ更新リクエスト受信")
    
    try:
        # shadowverse_db_builder.py を実行
        result = subprocess.run(
            ["python", "shadowverse_db_builder.py"],
            capture_output=True,
            text=True,
            check=True,
            timeout=300  # 5分でタイムアウト
        )
        
        # メトリクス再構築
        subprocess.run(
            ["python", "build_card_metrics.py"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
        
        logger.info("カードデータ更新完了")
        return jsonify({
            'success': True, 
            'message': 'カードデータとメトリクスの更新が完了しました'
        })
        
    except subprocess.TimeoutExpired:
        logger.error("カードデータ更新がタイムアウトしました")
        return jsonify({
            'success': False, 
            'message': 'カードデータ更新がタイムアウトしました'
        }), 500
    except subprocess.CalledProcessError as e:
        logger.error(f"カードデータ更新エラー: {e.stderr}")
        return jsonify({
            'success': False, 
            'message': f'更新エラー: {e.stderr}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
