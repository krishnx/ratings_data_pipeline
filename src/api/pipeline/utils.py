import functools
import logging
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


def retry(
    *exc_types: type[Exception],
    max_attempts: int = 3,
    base_delay_s: float = 0.5,
    on_retry: Callable[[Exception], None] | None = None,
):
    """Exponential-backoff retry decorator.

    Args:
        *exc_types:     Exception types that trigger a retry.
        max_attempts:   Total number of attempts (first try + retries).
        base_delay_s:   Initial delay in seconds; doubles on each retry.
        on_retry:       Optional callback invoked with the caught exception
                        before each sleep, e.g. ``lambda exc: session.rollback()``.
    """
    if not exc_types:
        raise ValueError("retry() requires at least one exception type")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not isinstance(exc, exc_types):
                        raise
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay_s * (2 ** attempt)
                    log.warning(
                        "Transient error in %s (attempt %d/%d), retrying in %.1fs: %s",
                        func.__name__, attempt + 1, max_attempts, delay, exc,
                    )
                    if on_retry is not None:
                        on_retry(exc)
                    time.sleep(delay)

        return wrapper

    return decorator
