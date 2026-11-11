import pytest

from txpipeline.retry import FaultInjector, RetryError, SimulatedFailure, call_with_retry


def test_succeeds_after_transient_failures():
    fault, delays = FaultInjector(2), []

    def op():
        fault.maybe_fail()
        return "ok"

    assert call_with_retry(op, attempts=3, base_delay=1, sleep=delays.append) == "ok"
    assert fault.calls == 3
    assert delays == [1, 2]  # backoff exponentiel


def test_gives_up_after_max_attempts():
    fault = FaultInjector(10)
    with pytest.raises(RetryError) as info:
        call_with_retry(fault.maybe_fail, attempts=3, sleep=lambda _: None)
    assert isinstance(info.value.__cause__, SimulatedFailure)
    assert fault.calls == 3


def test_does_not_retry_unexpected_errors():
    calls = []

    def op():
        calls.append(1)
        raise KeyError("bug")

    with pytest.raises(KeyError):
        call_with_retry(op, retry_on=(SimulatedFailure,), sleep=lambda _: None)
    assert len(calls) == 1
