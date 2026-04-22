from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _build_login_cache_key(username, ip_address):
    normalized_username = (username or '').strip().lower() or '<empty>'
    normalized_ip = ip_address or 'unknown'
    return f'login-throttle:{normalized_ip}:{normalized_username}'


def get_login_lockout_remaining_seconds(username, ip_address):
    state = cache.get(_build_login_cache_key(username, ip_address))
    if not state or not state.get('blocked_until'):
        return 0

    remaining = int((state['blocked_until'] - timezone.now()).total_seconds())
    if remaining <= 0:
        reset_failed_logins(username, ip_address)
        return 0
    return remaining


def register_failed_login(username, ip_address):
    timeout_seconds = getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 300)
    limit = getattr(settings, 'LOGIN_FAILURE_LIMIT', 5)
    key = _build_login_cache_key(username, ip_address)
    state = cache.get(key) or {'failures': 0, 'blocked_until': None}
    state['failures'] += 1

    if state['failures'] >= limit:
        state['blocked_until'] = timezone.now() + timedelta(seconds=timeout_seconds)

    cache.set(key, state, timeout_seconds)
    return state


def reset_failed_logins(username, ip_address):
    cache.delete(_build_login_cache_key(username, ip_address))
