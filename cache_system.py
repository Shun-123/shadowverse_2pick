# cache_system.py
import time
from typing import Dict, Any, Optional, Tuple
from functools import wraps

class SimpleCache:
    """シンプルなメモリキャッシュシステム"""
    
    def __init__(self, max_size: int = 500, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.access_count = {'hits': 0, 'misses': 0}
    
    def get(self, key: str) -> Optional[Any]:
        """キャッシュから値を取得"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            
            # TTL確認
            if time.time() - timestamp <= self.ttl_seconds:
                self.access_count['hits'] += 1
                return value
            else:
                del self.cache[key]
        
        self.access_count['misses'] += 1
        return None
    
    def set(self, key: str, value: Any):
        """キャッシュに値を設定"""
        # サイズ制限
        if len(self.cache) >= self.max_size:
            # 古いエントリを削除（簡易LRU）
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        self.cache[key] = (value, time.time())
    
    def clear(self):
        """キャッシュをクリア"""
        self.cache.clear()
        self.access_count = {'hits': 0, 'misses': 0}
    
    def get_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        total = self.access_count['hits'] + self.access_count['misses']
        hit_rate = self.access_count['hits'] / total if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_rate': hit_rate,
            'total_requests': total
        }

def cached_method(cache_instance: SimpleCache, key_prefix: str = ""):
    """メソッドキャッシュデコレータ"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # キャッシュキーを生成
            cache_key = f"{key_prefix}_{func.__name__}_{hash(str(args))}"
            
            # キャッシュから取得を試行
            cached_result = cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # キャッシュミス時は実際に実行
            result = func(self, *args, **kwargs)
            
            # 結果をキャッシュに保存
            if result is not None:
                cache_instance.set(cache_key, result)
            
            return result
        return wrapper
    return decorator

# グローバルキャッシュインスタンス
card_info_cache = SimpleCache(max_size=1000, ttl_seconds=600)
