"""Unit tests for the retry decorator in api.pipeline.utils."""

import pytest

from api.pipeline.utils import retry


class _Transient(Exception):
    pass


class _Permanent(Exception):
    pass


def test_succeeds_first_attempt():
    calls = []

    @retry(_Transient, max_attempts=3, base_delay_s=0)
    def fn():
        calls.append(1)
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 1


def test_retries_on_known_exception_and_succeeds():
    attempts = []

    @retry(_Transient, max_attempts=3, base_delay_s=0)
    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise _Transient("transient")
        return "done"

    assert fn() == "done"
    assert len(attempts) == 3


def test_raises_after_max_attempts():
    calls = []

    @retry(_Transient, max_attempts=3, base_delay_s=0)
    def fn():
        calls.append(1)
        raise _Transient("always fails")

    with pytest.raises(_Transient):
        fn()
    assert len(calls) == 3


def test_unknown_exception_not_retried():
    calls = []

    @retry(_Transient, max_attempts=3, base_delay_s=0)
    def fn():
        calls.append(1)
        raise _Permanent("not retryable")

    with pytest.raises(_Permanent):
        fn()
    assert len(calls) == 1


def test_on_retry_called_on_each_retry():
    retried_excs = []

    @retry(_Transient, max_attempts=3, base_delay_s=0, on_retry=retried_excs.append)
    def fn():
        raise _Transient("boom")

    with pytest.raises(_Transient):
        fn()

    assert len(retried_excs) == 2  # called before each of the 2 retries


def test_on_retry_not_called_on_final_failure():
    retried_excs = []

    @retry(_Transient, max_attempts=1, base_delay_s=0, on_retry=retried_excs.append)
    def fn():
        raise _Transient("boom")

    with pytest.raises(_Transient):
        fn()

    assert len(retried_excs) == 0


def test_requires_at_least_one_exc_type():
    with pytest.raises(ValueError):
        retry()


def test_preserves_function_return_value():
    @retry(_Transient, max_attempts=2, base_delay_s=0)
    def fn(x, y=10):
        return x + y

    assert fn(5, y=3) == 8


def test_multiple_exc_types():
    class _OtherTransient(Exception):
        pass

    calls = []

    @retry(_Transient, _OtherTransient, max_attempts=3, base_delay_s=0)
    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise _Transient("first")
        if len(calls) == 2:
            raise _OtherTransient("second")
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 3
