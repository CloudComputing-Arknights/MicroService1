import os, json, hashlib
from cachetools import TTLCache

TTL = int(os.getenv("API_CACHE_TTL_SECONDS", "60"))  # default 60s

# object caches
user_cache = TTLCache(maxsize=1000, ttl=TTL)
address_cache = TTLCache(maxsize=2000, ttl=TTL)

# list caches (queries with filters/pagination)
user_list_cache = TTLCache(maxsize=200, ttl=TTL)
address_list_cache = TTLCache(maxsize=200, ttl=TTL)

def filters_key(filters: dict, limit: int = 50, offset: int = 0) -> str:
    blob = json.dumps({"filters": filters, "limit": limit, "offset": offset}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()

def invalidate_user(user_id):
    user_cache.pop(str(user_id), None)
    user_list_cache.clear()  # any list might include this user

def invalidate_address(address_id):
    address_cache.pop(str(address_id), None)
    address_list_cache.clear()