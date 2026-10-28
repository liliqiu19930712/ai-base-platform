"""简易内存限流：全局 / 租户 / 智能体 三级。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.errors import AppError

_lock = Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)

# 默认：每分钟请求上限
LIMITS = {
    "global": 600,
    "tenant": 120,
    "agent": 60,
}


def _check(key: str, limit: int, window_sec: int = 60) -> None:
    now = time.time()
    with _lock:
        q = _buckets[key]
        while q and now - q[0] > window_sec:
            q.popleft()
        if len(q) >= limit:
            raise AppError("RATE_LIMITED", f"触发限流: {key}", 429)
        q.append(now)


def check_rate_limit(tenant_id: str, agent_id: str) -> None:
    _check("global", LIMITS["global"])
    _check(f"tenant:{tenant_id}", LIMITS["tenant"])
    _check(f"agent:{tenant_id}:{agent_id}", LIMITS["agent"])
