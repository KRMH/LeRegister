from datetime import timedelta

from leregister.adapters.clock import SystemClock


def test_system_clock_is_timezone_aware_utc():
    now = SystemClock().now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)
