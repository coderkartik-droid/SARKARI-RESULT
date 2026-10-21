import hashlib

from django.core.cache import cache


WINDOW_SECONDS = 15 * 60
MAX_FAILED_ATTEMPTS = 5


def _cache_keys(email, ip_address):
    digest = hashlib.sha256(f"{email}\0{ip_address}".encode("utf-8")).hexdigest()
    return f"auth:login:attempts:{digest}", f"auth:login:locked:{digest}"


def is_locked(email, ip_address):
    _, lock_key = _cache_keys(email, ip_address)
    return cache.get(lock_key, False)


def record_failure(email, ip_address):
    attempts_key, lock_key = _cache_keys(email, ip_address)
    cache.add(attempts_key, 0, timeout=WINDOW_SECONDS)
    try:
        attempts = cache.incr(attempts_key)
    except ValueError:
        cache.set(attempts_key, 1, timeout=WINDOW_SECONDS)
        attempts = 1
    if attempts >= MAX_FAILED_ATTEMPTS:
        cache.set(lock_key, True, timeout=WINDOW_SECONDS)


def clear_failures(email, ip_address):
    attempts_key, lock_key = _cache_keys(email, ip_address)
    cache.delete_many((attempts_key, lock_key))
