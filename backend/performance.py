"""
Performance Optimization Utilities
- Redis caching
- Connection pooling
- Query optimization
- Rate limiting
"""
import os
import logging
import time
import hashlib
import json
from typing import Any, Optional, Callable
from datetime import datetime, timezone
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
USE_REDIS = os.environ.get('USE_REDIS', 'false').lower() == 'true'

# In-memory cache fallback
class MemoryCache:
    """In-memory cache with TTL"""
    
    def __init__(self):
        self._cache = {}
        self._ttl = {}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            if key in self._ttl and time.time() > self._ttl[key]:
                del self._cache[key]
                del self._ttl[key]
                return None
            return self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = 300):
        self._cache[key] = value
        self._ttl[key] = time.time() + ttl
    
    def delete(self, key: str):
        if key in self._cache:
            del self._cache[key]
        if key in self._ttl:
            del self._ttl[key]
    
    def clear(self):
        self._cache.clear()
        self._ttl.clear()


# Global cache instance
cache = MemoryCache()


def get_cache() -> MemoryCache:
    """Get cache instance"""
    return cache


# Cache decorator
def cached(ttl: int = 300, key_prefix: str = ""):
    """Cache decorator for functions"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [key_prefix or func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            
            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, ttl)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            key_parts = [key_prefix or func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# Connection pool for database
class ConnectionPool:
    """Simple connection pool"""
    
    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self._available = []
        self._in_use = []
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        async with self._lock:
            if self._available:
                conn = self._available.pop()
                self._in_use.append(conn)
                return conn
            returnConnection()
    
    async def release(self, conn):
        async with self._lock:
            if conn in self._in_use:
                self._in_use.remove(conn)
            if len(self._available) < self.max_connections:
                self._available.append(conn)
    
    def __await__(self):
        return self.acquire()


class Connection:
    """Connection placeholder"""
    def close(self):
        pass


def returnConnection() -> Connection:
    """Return a new connection"""
    return Connection()


# Rate limiter
class RateLimiter:
    """Simple rate limiter"""
    
    def __init__(self, max_calls: int, period: int = 60):
        self.max_calls = max_calls
        self.period = period
        self._calls = []
    
    def is_allowed(self) -> bool:
        now = time.time()
        self._calls = [t for t in self._calls if now - t < self.period]
        
        if len(self._calls) >= self.max_calls:
            return False
        
        self._calls.append(now)
        return True
    
    def remaining(self) -> int:
        now = time.time()
        self._calls = [t for t in self._calls if now - t < self.period]
        return max(0, self.max_calls - len(self._calls))
    
    def reset(self):
        self._calls.clear()


# Query optimizer
class QueryOptimizer:
    """Optimize database queries"""
    
    # Index recommendations
    INDEXES = {
        "trades": ["ticker", "executed_at", "status"],
        "positions": ["ticker", "status"],
        "alerts": ["received_at", "ticker"]
    }
    
    @staticmethod
    def optimize_query(collection: str, query: dict) -> dict:
        """Add hints to optimize query"""
        # Add index hints
        if collection in QueryOptimizer.INDEXES:
            query = query.copy()
            query["$hint"] = QueryOptimizer.INDEXES[collection]
        return query
    
    @staticmethod
    def should_cache(collection: str, query: dict) -> bool:
        """Determine if query should be cached"""
        # Cache reads, not writes
        return query.get("$method") in [None, "find", "aggregate"]


# Performance monitor
class PerformanceMonitor:
    """Monitor performance metrics"""
    
    def __init__(self):
        self._metrics = {
            "requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "avg_response_time": 0,
            "response_times": []
        }
    
    def record_request(self, response_time: float):
        self._metrics["requests"] += 1
        self._metrics["response_times"].append(response_time)
        
        # Keep last 100 response times
        if len(self._metrics["response_times"]) > 100:
            self._metrics["response_times"] = self._metrics["response_times"][-100:]
        
        # Update average
        times = self._metrics["response_times"]
        self._metrics["avg_response_time"] = sum(times) / len(times) if times else 0
    
    def record_cache_hit(self):
        self._metrics["cache_hits"] += 1
    
    def record_cache_miss(self):
        self._metrics["cache_misses"] += 1
    
    def record_error(self):
        self._metrics["errors"] += 1
    
    def get_metrics(self) -> dict:
        return {
            **self._metrics,
            "cache_hit_rate": (
                self._metrics["cache_hits"] / 
                (self._metrics["cache_hits"] + self._metrics["cache_misses"]) * 100
                if (self._metrics["cache_hits"] + self._metrics["cache_misses"]) > 0 
                else 0
            )
        }
    
    def reset(self):
        self.__init__()


# Global performance monitor
perf_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Get performance monitor"""
    return perf_monitor


# Batch processor for efficient operations
class BatchProcessor:
    """Process items in batches"""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
    
    async def process(
        self, 
        items: list, 
        processor: Callable,
        max_concurrent: int = 5
    ) -> list:
        """Process items in batches with concurrency"""
        results = []
        
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            
            # Process batch with concurrency limit
            tasks = [processor(item) for item in batch]
            batch_results = await asyncio.gather(*tasks[:max_concurrent], return_exceptions=True)
            
            results.extend(batch_results)
        
        return results


# Export utilities
__all__ = [
    'cache',
    'get_cache',
    'cached',
    'ConnectionPool',
    'RateLimiter',
    'QueryOptimizer',
    'perf_monitor',
    'get_performance_monitor',
    'BatchProcessor'
]