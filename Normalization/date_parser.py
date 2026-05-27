"""
date_parser.py
──────────────
Robust date parser that handles every format seen across the three sources.

Formats handled
───────────────
SAP:
  20250415            YYYYMMDD (most common SAP export)
  /Date(1498946400000)/  Microsoft JSON Epoch (OData legacy)
  15.04.2025          DD.MM.YYYY (German locale)
  2025-04-15          ISO 8601
  15/04/2025          DD/MM/YYYY (common in UK/IN portal exports)

Concur/Travel:
  04/15/2025          MM/DD/YYYY (US Concur export)
  15-Apr-2025         DD-Mon-YYYY (Concur named-month format)
  2025-04-15T07:25:00  ISO 8601 with time

Utility:
  2025-04-15          ISO
  2025-03-02          ISO
  (all utility dates in our generators are ISO — but real portals vary)

Strategy
────────
1. Regex-detect known patterns in strict order (most specific first).
2. If none match, fall back to dateutil.parser with dayfirst=True
   (UK/IN convention) then dayfirst=False (US) for a second chance.
3. Always return a timezone-naive date or datetime in UTC.
4. Never return None silently — always return (result, flag_message).
"""

from __future__ import annotations
import re
from datetime import date, datetime
from typing import Union

try:
    from dateutil import parser as dateutil_parser
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False

DateResult = Union[date, datetime, None]

# ── compiled patterns ─────────────────────────────────────────────────────────

_P_YYYYMMDD     = re.compile(r"^\d{8}$")                          # 20250415
_P_MSEPOCH      = re.compile(r"^/Date\((\d+)\)/$")               # /Date(1498946400000)/
_P_DE_DATE      = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$") # 15.04.2025
_P_SLASH_DMY    = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")   # 15/04/2025
_P_SLASH_MDY    = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")   # 04/15/2025 (same regex, resolved by heuristic)
_P_NAMED_MONTH  = re.compile(                                      # 15-Apr-2025 or 15-APR-2025
    r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
_P_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")  # ISO with time
_P_ISO_DATE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")              # 2025-04-15

_MONTH_ABBR = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

FUTURE_DATE_THRESHOLD_DAYS = 90    # flag dates more than 90 days in the future
OLD_DATE_THRESHOLD_YEARS   = 5     # flag dates more than 5 years in the past


def parse_date(
    raw: str | None,
    field_name: str = "date",
    source: str = "UNKNOWN",
) -> tuple[date | datetime | None, str | None]:
    """
    Parse a date string into a Python date/datetime.

    Returns
    ───────
    (parsed_date, flag_message)
    parsed_date is None if parsing fails entirely.
    flag_message is a human-readable warning, or None if clean.
    """
    if not raw or (isinstance(raw, float)):
        return None, f"[{field_name}] Empty or null value"

    s = str(raw).strip()
    today = date.today()

    # ── 1. SAP YYYYMMDD ──────────────────────────────────────────────────────
    if _P_YYYYMMDD.match(s):
        try:
            d = datetime.strptime(s, "%Y%m%d").date()
            return d, _range_flag(d, field_name, today)
        except ValueError:
            pass

    # ── 2. Microsoft JSON Epoch ───────────────────────────────────────────────
    m = _P_MSEPOCH.match(s)
    if m:
        epoch_ms = int(m.group(1))
        d = datetime.utcfromtimestamp(epoch_ms / 1000).date()
        return d, _range_flag(d, field_name, today,
                              extra="Parsed from Microsoft OData /Date() epoch")

    # ── 3. ISO 8601 with time ─────────────────────────────────────────────────
    if _P_ISO_DATETIME.match(s):
        try:
            # strip timezone offset for uniformity; store as naive UTC
            clean = re.sub(r"[+\-]\d{2}:\d{2}$", "", s).replace("Z", "")
            dt = datetime.strptime(clean[:19], "%Y-%m-%dT%H:%M:%S")
            return dt, _range_flag(dt.date(), field_name, today)
        except ValueError:
            pass

    # ── 4. ISO date only ─────────────────────────────────────────────────────
    if _P_ISO_DATE.match(s):
        try:
            d = datetime.strptime(s, "%Y-%m-%d").date()
            return d, _range_flag(d, field_name, today)
        except ValueError:
            pass

    # ── 5. German DD.MM.YYYY ─────────────────────────────────────────────────
    m = _P_DE_DATE.match(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                d = date(year, month, day)
                return d, _range_flag(d, field_name, today,
                                      extra="Parsed as DD.MM.YYYY (German/EU format)")
            except ValueError:
                pass

    # ── 6. Named month: 15-Apr-2025 ──────────────────────────────────────────
    m = _P_NAMED_MONTH.match(s)
    if m:
        day   = int(m.group(1))
        month = _MONTH_ABBR.get(m.group(2).lower())
        year  = int(m.group(3))
        if month:
            try:
                d = date(year, month, day)
                return d, _range_flag(d, field_name, today)
            except ValueError:
                pass

    # ── 7. Slash-separated: resolve DMY vs MDY by heuristic ─────────────────
    m = _P_SLASH_DMY.match(s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # If first number > 12, it MUST be the day (DMY)
        if a > 12:
            try:
                d = date(year, b, a)
                return d, _range_flag(d, field_name, today,
                                      extra="Parsed as DD/MM/YYYY")
            except ValueError:
                pass
        # If second number > 12, it MUST be the day (MDY — US format)
        elif b > 12:
            try:
                d = date(year, a, b)
                return d, _range_flag(d, field_name, today,
                                      extra="Parsed as MM/DD/YYYY (US)")
            except ValueError:
                pass
        else:
            # Ambiguous: default to DMY (UK/IN convention for utility/SAP)
            # but flag it
            try:
                d = date(year, b, a)
                flag_msg = _range_flag(d, field_name, today)
                ambig = f"Date '{s}' is ambiguous (both DMY and MDY valid); assumed DD/MM/YYYY"
                return d, f"{flag_msg}; {ambig}" if flag_msg else ambig
            except ValueError:
                pass

    # ── 8. dateutil fallback ─────────────────────────────────────────────────
    if DATEUTIL_AVAILABLE:
        for dayfirst in (True, False):
            try:
                dt = dateutil_parser.parse(s, dayfirst=dayfirst)
                return dt.date(), _range_flag(dt.date(), field_name, today,
                    extra=f"Parsed via dateutil (dayfirst={dayfirst})")
            except Exception:
                pass

    return None, f"[{field_name}] Cannot parse date value '{s}' — manual review required"


def _range_flag(
    d: date,
    field_name: str,
    today: date,
    extra: str | None = None,
) -> str | None:
    """Flag future or very old dates."""
    flags = []
    delta = (d - today).days
    if delta > FUTURE_DATE_THRESHOLD_DAYS:
        flags.append(f"[{field_name}] Date {d} is {delta} days in the future — likely a data entry error")
    elif delta > 0:
        flags.append(f"[{field_name}] Date {d} is slightly in the future ({delta} days)")

    years_ago = (today - d).days / 365.25
    if years_ago > OLD_DATE_THRESHOLD_YEARS:
        flags.append(f"[{field_name}] Date {d} is {years_ago:.1f} years old — verify reporting period")

    if extra:
        flags.append(extra)

    return "; ".join(flags) if flags else None
