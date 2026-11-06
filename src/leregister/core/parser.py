"""Pure parser for the `New` command (AR7, AR8). No I/O, no AI, no date-guessing library."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import phonenumbers

from leregister.core.ports import Clock

LOCAL_TZ = ZoneInfo("Asia/Beirut")

_MONTH_NAMES: dict[int, tuple[str, ...]] = {
    1: ("janvier", "janv", "jan", "january"),
    2: ("fevrier", "fevr", "fev", "feb", "february"),
    3: ("mars", "mar", "march"),
    4: ("avril", "avr", "apr", "april"),
    5: ("mai", "may"),
    6: ("juin", "jun", "june"),
    7: ("juillet", "juil", "jul", "july"),
    8: ("aout", "aug", "august"),
    9: ("septembre", "sept", "sep", "september"),
    10: ("octobre", "oct", "october"),
    11: ("novembre", "nov", "november"),
    12: ("decembre", "dec", "december"),
}
MONTHS: dict[str, int] = {name: n for n, names in _MONTH_NAMES.items() for name in names}

_SAME_MONTH = re.compile(r"^([0-9]{1,2})-([0-9]{1,2}) ([a-z]+)$")
_TWO_MONTHS = re.compile(r"^([0-9]{1,2}) ([a-z]+)-([0-9]{1,2}) ([a-z]+)$")
_PHONE_SHAPE = re.compile(r"^\+[0-9().-]+$")


@dataclass(frozen=True)
class ParsedNew:
    chalet: int
    name: str
    phone: str  # E.164
    check_in: date
    check_out: date

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


@dataclass(frozen=True)
class Rejected:
    reason: str


ParseResult = ParsedNew | Rejected


def parse_command(text: str, *, clock: Clock, chalet_count: int, max_stay: int) -> ParseResult:
    """Parse a `New <chalet> <name> <phone> <dates>` message, or say why not."""
    tokens = text.split()
    if len(tokens) < 2 or tokens[0].casefold() != "new":
        return Rejected("not a New command")

    chalet_token = tokens[1]
    if not chalet_token.isascii() or not chalet_token.isdigit():
        return Rejected("chalet must be a number")
    chalet = int(chalet_token)
    if not 1 <= chalet <= chalet_count:
        return Rejected(f"chalet {chalet} is outside 1..{chalet_count}")

    rest = tokens[2:]
    phone_at = next((i for i, tok in enumerate(rest) if tok.startswith("+")), None)
    if phone_at is None:
        return Rejected("phone is missing: it must start with + and the country code")
    name = " ".join(rest[:phone_at])
    if not name:
        return Rejected("name is missing")
    phone = _normalize_phone(rest[phone_at])
    if phone is None:
        return Rejected("phone is not a valid number with country code")

    dates = _parse_dates(" ".join(rest[phone_at + 1 :]), today=_today(clock))
    if isinstance(dates, Rejected):
        return dates
    check_in, check_out = dates
    if check_out <= check_in:
        return Rejected("check-out must be after check-in")
    nights = (check_out - check_in).days
    if nights > max_stay:
        return Rejected(f"stay of {nights} nights is over the maximum of {max_stay}")
    return ParsedNew(chalet, name, phone, check_in, check_out)


def _today(clock: Clock) -> date:
    return clock.now().astimezone(LOCAL_TZ).date()


def _normalize_phone(token: str) -> str | None:
    if not _PHONE_SHAPE.match(token):  # no extensions or stray text: echo must match what was typed
        return None
    try:
        number = phonenumbers.parse(token, None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _month(name: str) -> int | None:
    return MONTHS.get(name)


def _parse_dates(text: str, *, today: date) -> tuple[date, date] | Rejected:
    if not text:
        return Rejected("dates are missing")
    s = re.sub(r"\s*[-\u2013\u2014]\s*", "-", _fold(text))
    s = s.replace(".", "")
    if m := _SAME_MONTH.match(s):
        month = _month(m.group(3))
        if month is None:
            return Rejected(f"unknown month '{m.group(3)}'")
        d1, d2 = int(m.group(1)), int(m.group(2))
        check_in = _next_occurrence(d1, month, on_or_after=today)
        if check_in is None or not _valid(check_in.year, month, d2):
            return Rejected("dates are not a real calendar date")
        return check_in, date(check_in.year, month, d2)
    if m := _TWO_MONTHS.match(s):
        month1, month2 = _month(m.group(2)), _month(m.group(4))
        for given, month in ((m.group(2), month1), (m.group(4), month2)):
            if month is None:
                return Rejected(f"unknown month '{given}'")
        assert month1 is not None and month2 is not None
        if (int(m.group(1)), month1) == (int(m.group(3)), month2):
            return Rejected("check-out must be after check-in")
        check_in = _next_occurrence(int(m.group(1)), month1, on_or_after=today)
        if check_in is None:
            return Rejected("dates are not a real calendar date")
        check_out = _next_occurrence(int(m.group(3)), month2, on_or_after=check_in, strictly=True)
        if check_out is None:
            return Rejected("dates are not a real calendar date")
        return check_in, check_out
    return Rejected("dates not understood: use like 12-15 dec or 30 dec-2 jan")


def _valid(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _next_occurrence(day: int, month: int, *, on_or_after: date, strictly: bool = False) -> date | None:
    """First real date with this day and month from `on_or_after` (excluded if `strictly`)."""
    for year in range(on_or_after.year, on_or_after.year + 9):  # covers 29 Feb gaps
        if not _valid(year, month, day):
            continue
        candidate = date(year, month, day)
        if candidate > on_or_after or (candidate == on_or_after and not strictly):
            return candidate
    return None
