from datetime import date, datetime, timezone

import pytest

from leregister.core.parser import ParsedNew, Rejected, parse_command


class FixedClock:
    def __init__(self, y=2026, m=11, d=6, hour=12):
        self._now = datetime(y, m, d, hour, 0, tzinfo=timezone.utc)

    def now(self):
        return self._now


def parse(text, clock=None, chalet_count=40, max_stay=60):
    return parse_command(text, clock=clock or FixedClock(), chalet_count=chalet_count, max_stay=max_stay)


def test_basic():
    assert parse("New 2 Sam +96171123456 12-15 dec") == ParsedNew(
        2, "Sam", "+96171123456", date(2026, 12, 12), date(2026, 12, 15)
    )


def test_multi_word_name_case_and_cross_year():
    r = parse("new 2 Mary Ann +96171123456 30 DEC-2 Jan")
    assert r == ParsedNew(2, "Mary Ann", "+96171123456", date(2026, 12, 30), date(2027, 1, 2))


@pytest.mark.parametrize("month", ["déc", "décembre", "dec", "december", "DÉCEMBRE", "Dec."])
def test_month_spellings(month):
    r = parse(f"New 2 Sam +96171123456 12-15 {month}")
    assert isinstance(r, ParsedNew) and r.check_in == date(2026, 12, 12)


@pytest.mark.parametrize(
    "month,n", [("janvier", 1), ("fév", 2), ("mars", 3), ("avril", 4), ("mai", 5), ("juin", 6),
                ("juillet", 7), ("août", 8), ("sept", 9), ("octobre", 10), ("novembre", 11), ("jul", 7)]
)
def test_other_months(month, n):
    r = parse(f"New 2 Sam +96171123456 10-12 {month}")
    assert isinstance(r, ParsedNew) and r.check_in.month == n


def test_year_less_rolls_to_next_year_in_beirut_today():
    r = parse("New 2 Sam +96171123456 12-15 dec", clock=FixedClock(2026, 12, 20))
    assert r.check_in == date(2027, 12, 12)


def test_today_counts_and_beirut_midnight_rollover():
    # 22:30 UTC on 11 Dec is already 12 Dec in Beirut (UTC+2), so 12 Dec is still "today"
    r = parse("New 2 Sam +96171123456 12-15 dec", clock=FixedClock(2026, 12, 11, 22))
    assert r.check_in == date(2026, 12, 12)
    r = parse("New 2 Sam +96171123456 11-15 dec", clock=FixedClock(2026, 12, 11, 22))
    assert r.check_in == date(2027, 12, 11)


def test_two_month_checkout_is_first_after_checkin():
    r = parse("New 2 Sam +96171123456 28 feb-3 mar", clock=FixedClock(2026, 11, 6))
    assert (r.check_in, r.check_out) == (date(2027, 2, 28), date(2027, 3, 3))


@pytest.mark.parametrize(
    "text,part",
    [
        ("New 2 Sam 12-15 dec", "phone"),
        ("New 2 Sam 96171123456 12-15 dec", "phone"),
        ("New 2 Sam +961 12-15 dec", "phone"),
        ("New 2 Sam +1234 12-15 dec", "phone"),
        ("New 2 +96171123456 12-15 dec", "name"),
        ("New 2 Sam +96171123456 12-15 xyz", "unknown month"),
        ("New 2 Sam +96171123456 12 dec-15 xyz", "unknown month"),
        ("New 0 Sam +96171123456 12-15 dec", "chalet"),
        ("New 41 Sam +96171123456 12-15 dec", "chalet"),
        ("New x Sam +96171123456 12-15 dec", "chalet"),
        ("New 2 Sam +96171123456 12-12 dec", "check-out must be after"),
        ("New 2 Sam +96171123456 15-12 dec", "check-out must be after"),
        ("New 2 Sam +96171123456 1 dec-31 jan", "over the maximum"),
        ("New 2 Sam +96171123456", "dates"),
        ("New 2 Sam +96171123456 soon", "dates"),
        ("New 2 Sam +96171123456 31-32 dec", "calendar"),
        ("New 2 Sam +96171123456 30-31 apr", "calendar"),
        ("hello", "not a New"),
        ("Cancel 2", "not a New"),
        ("", "not a New"),
        ("New", "not a New"),
    ],
)
def test_rejections_name_the_failing_part(text, part):
    r = parse(text)
    assert isinstance(r, Rejected) and part in r.reason


def test_stay_limits_use_config():
    assert isinstance(parse("New 2 Sam +96171123456 1 dec-31 dec", max_stay=30), ParsedNew)
    assert isinstance(parse("New 2 Sam +96171123456 1 dec-31 dec", max_stay=29), Rejected)
    assert isinstance(parse("New 41 Sam +96171123456 12-15 dec", chalet_count=50), ParsedNew)


def test_leap_day_checkin_finds_next_leap_year():
    r = parse("New 2 Sam +96171123456 29 feb-2 mar", clock=FixedClock(2026, 11, 6))
    assert (r.check_in, r.check_out) == (date(2028, 2, 29), date(2028, 3, 2))


def test_two_month_same_day_is_rejected_for_the_real_reason():
    r = parse("New 2 Sam +96171123456 5 dec-5 dec")
    assert isinstance(r, Rejected) and "check-out must be after" in r.reason


@pytest.mark.parametrize("phone", ["+96171123456;ext=12", "+96171123456x", "+96171123456abc"])
def test_phone_with_extra_text_is_rejected(phone):
    r = parse(f"New 2 Sam {phone} 12-15 dec")
    assert isinstance(r, Rejected) and "phone" in r.reason


def test_non_ascii_digits_in_dates_are_rejected():
    assert isinstance(parse("New 2 Sam +96171123456 ١٢-١٥ dec"), Rejected)


def test_parser_never_reads_system_time(monkeypatch):
    import leregister.core.parser as parser_module

    class NoToday(date):
        @classmethod
        def today(cls):
            raise AssertionError("parser must use the Clock port")

    monkeypatch.setattr(parser_module, "date", NoToday)
    assert isinstance(parse("New 2 Sam +96171123456 12-15 dec"), ParsedNew)
