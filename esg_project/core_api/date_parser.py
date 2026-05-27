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

_P_YYYYMMDD     = re.compile(r"^\d{8}$")
_P_MSEPOCH      = re.compile(r"^/Date\((\d+)\)/$")
_P_DE_DATE      = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_P_SLASH_DMY    = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_P_SLASH_MDY    = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_P_NAMED_MONTH  = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
_P_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_P_ISO_DATE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MONTH_ABBR = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

FUTURE_DATE_THRESHOLD_DAYS = 90
OLD_DATE_THRESHOLD_YEARS   = 5

def parse_date(
    raw: str | None,
    field_name: str = "date",
    source: str = "UNKNOWN",
) -> tuple[date | datetime | None, str | None]:
    if not raw or (isinstance(raw, float)):
        return None, f"[{field_name}] Empty or null value"

    s = str(raw).strip()
    today = date.today()

    if _P_YYYYMMDD.match(s):
        try:
            d = datetime.strptime(s, "%Y%m%d").date()
            return d, _range_flag(d, field_name, today)
        except ValueError:
            pass

    m = _P_MSEPOCH.match(s)
    if m:
        epoch_ms = int(m.group(1))
        d = datetime.utcfromtimestamp(epoch_ms / 1000).date()
        return d, _range_flag(d, field_name, today, extra="Parsed from Microsoft OData /Date() epoch")

    if _P_ISO_DATETIME.match(s):
        try:
            clean = re.sub(r"[+\-]\d{2}:\d{2}$", "", s).replace("Z", "")
            dt = datetime.strptime(clean[:19], "%Y-%m-%dT%H:%M:%S")
            return dt, _range_flag(dt.date(), field_name, today)
        except ValueError:
            pass

    if _P_ISO_DATE.match(s):
        try:
            d = datetime.strptime(s, "%Y-%m-%d").date()
            return d, _range_flag(d, field_name, today)
        except ValueError:
            pass

    m = _P_DE_DATE.match(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                d = date(year, month, day)
                return d, _range_flag(d, field_name, today, extra="Parsed as DD.MM.YYYY (German/EU format)")
            except ValueError:
                pass

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

    m = _P_SLASH_DMY.match(s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12:
            try:
                d = date(year, b, a)
                return d, _range_flag(d, field_name, today, extra="Parsed as DD/MM/YYYY")
            except ValueError:
                pass
        elif b > 12:
            try:
                d = date(year, a, b)
                return d, _range_flag(d, field_name, today, extra="Parsed as MM/DD/YYYY (US)")
            except ValueError:
                pass
        else:
            try:
                d = date(year, b, a)
                flag_msg = _range_flag(d, field_name, today)
                ambig = f"Date '{s}' is ambiguous (both DMY and MDY valid); assumed DD/MM/YYYY"
                return d, f"{flag_msg}; {ambig}" if flag_msg else ambig
            except ValueError:
                pass

    if DATEUTIL_AVAILABLE:
        for dayfirst in (True, False):
            try:
                dt = dateutil_parser.parse(s, dayfirst=dayfirst)
                return dt.date(), _range_flag(dt.date(), field_name, today, extra=f"Parsed via dateutil (dayfirst={dayfirst})")
            except Exception:
                pass

    return None, f"[{field_name}] Cannot parse date value '{s}' — manual review required"

def _range_flag(
    d: date,
    field_name: str,
    today: date,
    extra: str | None = None,
) -> str | None:
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
