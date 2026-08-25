"""
Rate limiting (Section 8.2). Applied per-user (falls back to per-IP for
unauthenticated routes like /auth/login) to prevent both abuse and model
extraction attacks — an attacker repeatedly querying /predict or /whatif to
reverse-engineer the model's decision boundary is a real risk for any
exposed scoring API.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_func(request):
    # Prefer the authenticated user id (set by auth dependency into
    # request.state) so rate limits track identity, not just IP — multiple
    # legitimate users behind one NAT/IP shouldn't share a budget, and a
    # single attacker rotating IPs still hits their per-account limit.
    user_id = getattr(request.state, "user_id", None)
    return user_id or get_remote_address(request)


limiter = Limiter(key_func=_key_func)
