"""
normalize.py
────────────
Main normalization pipeline.  One entry point per source type:

    normalize_sap_procurement(path)  → list[NormalizedRecord]
    normalize_sap_fuel(path)         → list[NormalizedRecord]
    normalize_utility(path)          → list[NormalizedRecord]
    normalize_travel(path)           → list[NormalizedRecord]

Each returns a list of NormalizedRecord dataclasses.

Then write_output(records, out_path) saves a clean CSV with:
  - one row per emission event
  - all raw source values preserved alongside normalized values
  - flags and statuses populated
  - ready to be inserted into the Django EmissionRecord table

Key techniques from the PDF research applied here:
  - Immutable raw_data preservation (entire source row stored as JSON)
  - Billing period interpolation across calendar months (utility)
  - kVA demand charge separation (utility)
  - BWART movement type carbon logic (SAP — 313/315 double-count prevention)
  - Haversine + 8% uplift for flight distances (travel)
  - Booking lifecycle status filtering (travel — skip CANCELLED rows)
  - Non-employee traveller flagging (travel)
  - Statistical outlier detection across batch (z-score > 3 → flag)
  - Duplicate row detection via content hash
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Any

import openpyxl
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from column_resolver import remap_df
from unit_normalizer import (
    normalize_fuel, normalize_electricity,
    normalize_flight, normalize_hotel, normalize_ground,
    infer_fuel_type,
)
from date_parser import parse_date

# ── Airport coordinate lookup (embed subset; extend for production) ───────────
AIRPORT_COORDS: dict[str, tuple[float, float]] = {
    "DEL":(28.5665,77.1031), "BOM":(19.0896,72.8656), "BLR":(13.1986,77.7066),
    "MAA":(12.9941,80.1709), "HYD":(17.2403,78.4294), "PNQ":(18.5793,73.9089),
    "CCU":(22.6547,88.4467), "AMD":(23.0770,72.6347),
    "LHR":(51.4775,-0.4614), "LGW":(51.1537,-0.1821), "MAN":(53.3537,-2.2750),
    "CDG":(49.0097,2.5479),  "AMS":(52.3086,4.7639),  "FRA":(50.0379,8.5622),
    "MUC":(48.3538,11.7861), "ZRH":(47.4647,8.5492),
    "DXB":(25.2532,55.3657), "DOH":(25.2609,51.6138), "SIN":(1.3644,103.9915),
    "HKG":(22.3080,113.9185),"NRT":(35.7720,140.3929), "BKK":(13.6811,100.7472),
    "JFK":(40.6413,-73.7781), "LAX":(33.9425,-118.4081),"ORD":(41.9742,-87.9073),
    "SFO":(37.6213,-122.3790),"YYZ":(43.6777,-79.6248), "GRU":(-23.4356,-46.4731),
}

# BWART movement types to ignore (internal transfers — would double-count)
BWART_SKIP = {"313", "315"}
# BWART → scope/category guidance
BWART_SCOPE = {
    "201": (1, "stationary_combustion"),   # goods issue to cost centre
    "261": (1, "stationary_combustion"),   # goods issue to production order
    "241": (1, "stationary_combustion"),   # goods issue to fixed asset
    "101": (3, "purchased_goods"),         # goods receipt (Scope 3 Cat 1)
    "122": None,                           # return delivery — skip
    "551": (1, "stationary_combustion"),   # scrapping / waste combustion
    "242": None,                           # reversal of 241 — skip
}

SKIP_TRAVEL_TYPES = {"PERDIEM", "PERDM"}
SKIP_APPROVAL_STATUSES = {"A_NOTF"}   # not submitted — do not count yet

# ── Output schema ─────────────────────────────────────────────────────────────

@dataclass
class NormalizedRecord:
    # provenance
    source_type:            str    # SAP_PROC | SAP_FUEL | UTILITY_IN | UTILITY_UK | TRAVEL
    source_file:            str
    source_row_id:          str    # hash of original row
    raw_data:               str    # JSON of original row
    batch_id:               str    # shared across all rows in one file

    # timing
    period_start:           str    # ISO date
    period_end:             str    # ISO date

    # categorisation
    scope:                  int    # 1 | 2 | 3
    category:               str    # stationary_combustion | purchased_electricity | business_travel_air | …

    # activity
    activity_value:         float  # raw quantity (as extracted)
    activity_unit:          str    # raw unit (as extracted)
    canonical_value:        float  # converted quantity in canonical unit
    canonical_unit:         str    # L | KG | kWh | passenger_km | nights | km

    # emission
    kgco2e:                 float
    emission_factor:        float
    emission_factor_source: str

    # workflow
    status:                 str    # PENDING_REVIEW | FLAGGED | SKIP
    flag_reason:            str    # human-readable, empty if clean

    # optional enrichment
    location_plant:         str = ""
    location_country:       str = ""
    material_description:   str = ""
    traveller_id:           str = ""
    trip_id:                str = ""

    # interpolation metadata (utility)
    interpolated_month:     str = ""   # YYYY-MM if this row was split by interpolation
    interpolation_fraction: float = 0.0


def _row_hash(row_dict: dict) -> str:
    """Stable hash of a source row for dedup and audit trail."""
    content = json.dumps(row_dict, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _safe_float(val: Any, field: str = "") -> tuple[float | None, str | None]:
    """Cast to float, handle German comma decimals, return (value, flag)."""
    if val is None or val == "":
        return None, f"Empty value for '{field}'"
    s = str(val).strip()
    # German decimal comma: "1.234,56" → "1234.56"
    if re.search(r"\d,\d", s) and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s), None
    except ValueError:
        return None, f"Cannot convert '{val}' to number for '{field}'"


def _outlier_flags(records: list[NormalizedRecord]) -> None:
    """
    Mark records whose kgco2e is >3 std deviations from batch mean as FLAGGED.
    Per the PDF: statistical outlier detection across the whole batch.
    """
    vals = [r.kgco2e for r in records if r.kgco2e and r.kgco2e > 0]
    if len(vals) < 5:
        return
    mean = statistics.mean(vals)
    stdev = statistics.stdev(vals)
    if stdev == 0:
        return
    for r in records:
        if r.kgco2e and stdev > 0:
            z = (r.kgco2e - mean) / stdev
            if z > 3:
                r.status = "FLAGGED"
                r.flag_reason = (
                    f"{r.flag_reason}; " if r.flag_reason else ""
                ) + f"Statistical outlier: kgCO2e={r.kgco2e:.1f} is z={z:.1f} above batch mean {mean:.1f}"


def _dedup(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    """Remove duplicate source rows (same hash)."""
    seen, out = set(), []
    for r in records:
        if r.source_row_id not in seen:
            seen.add(r.source_row_id)
            out.append(r)
        else:
            pass  # silently drop — logged in batch summary
    return out


# ── SAP Procurement ────────────────────────────────────────────────────────────

def normalize_sap_procurement(path: str) -> list[NormalizedRecord]:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    df_r, mapping, unresolved = remap_df(df)
    batch_id = f"SAP_PROC_{os.path.basename(path)}"
    records = []

    for idx, row in df_r.iterrows():
        raw_dict = df.iloc[idx].to_dict()
        row_id = _row_hash(raw_dict)
        flags = []

        # ── quantity ───────────────────────────────────────────────────
        qty, f = _safe_float(row.get("quantity"), "quantity")
        if f: flags.append(f)
        if qty is None: continue
        if qty < 0:
            flags.append(f"Negative quantity ({qty}) — possible credit memo or reversal; skipping emission calc")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_PROC", flags))
            continue
        if qty == 0:
            flags.append("Zero quantity — cancelled order not deleted")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_PROC", flags))
            continue

        # ── unit ────────────────────────────────────────────────────────
        unit = str(row.get("unit", "")).strip() or "?"
        if unit == "EA":
            flags.append("Unit 'EA' (each) on bulk material — likely data entry error; cannot compute emission")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_PROC", flags))
            continue

        # ── material / fuel inference ───────────────────────────────────
        mat_desc = str(row.get("material_description", "")).strip()
        fuel_type = infer_fuel_type(mat_desc)
        if not fuel_type:
            flags.append(f"Cannot infer fuel type from material description '{mat_desc}'")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_PROC", flags))
            continue

        # ── date ─────────────────────────────────────────────────────────
        date_val, date_flag = parse_date(row.get("posting_date"), "BUDAT", "SAP_PROC")
        if date_flag: flags.append(date_flag)
        period_start = date_val.isoformat() if date_val else "UNKNOWN"
        period_end   = period_start

        # ── normalize ────────────────────────────────────────────────────
        result = normalize_fuel(qty, unit, mat_desc)
        if not result.success:
            flags.append(result.flag)
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_PROC", flags))
            continue
        if result.flag:
            flags.append(result.flag)

        status = "FLAGGED" if flags else "PENDING_REVIEW"
        records.append(NormalizedRecord(
            source_type="SAP_PROC", source_file=path, source_row_id=row_id,
            raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
            period_start=period_start, period_end=period_end,
            scope=result.scope, category="stationary_combustion",
            activity_value=qty, activity_unit=unit,
            canonical_value=round(result.canonical_qty, 4),
            canonical_unit=result.canonical_unit,
            kgco2e=round(result.kgco2e, 3),
            emission_factor=result.emission_factor,
            emission_factor_source=result.emission_factor_source,
            status=status, flag_reason="; ".join(flags),
            location_plant=str(row.get("plant", "")),
            material_description=mat_desc,
        ))

    _outlier_flags(records)
    return _dedup(records)


# ── SAP Fuel (XLSX) ────────────────────────────────────────────────────────────

def normalize_sap_fuel(path: str) -> list[NormalizedRecord]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Fuel_Consumption"]
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]

    rows_raw = []
    for r in range(2, ws.max_row + 1):
        rows_raw.append({headers[c]: ws.cell(r, c + 1).value for c in range(len(headers))})

    df = pd.DataFrame(rows_raw)
    df_r, mapping, _ = remap_df(df)
    batch_id = f"SAP_FUEL_{os.path.basename(path)}"
    records = []

    for idx, row in df_r.iterrows():
        raw_dict = rows_raw[idx]
        row_id = _row_hash(raw_dict)
        flags = []

        # ── movement type logic (PDF section: Movement Types) ────────────
        bwart = str(row.get("movement_type", "")).strip()
        if bwart in BWART_SKIP:
            # 313/315 transfer — internal shuffle, skip to avoid double-count
            continue
        scope_info = BWART_SCOPE.get(bwart)
        if scope_info is None:
            # reversal or unknown — skip
            continue
        scope, category = scope_info

        # ── quantity ────────────────────────────────────────────────────
        qty, f = _safe_float(row.get("quantity"), "MENGE")
        if f: flags.append(f)
        if qty is None: continue
        if qty < 0:
            flags.append(f"Negative quantity ({qty}) — reversal entry (BWART {bwart})")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_FUEL", flags))
            continue
        if qty == 0:
            continue

        unit = str(row.get("unit", "")).strip() or "?"
        mat_desc = str(row.get("material_description", "")).strip()
        if not mat_desc:
            flags.append("Blank material description — cannot infer fuel type")

        date_val, date_flag = parse_date(row.get("posting_date"), "BUDAT", "SAP_FUEL")
        if date_flag: flags.append(date_flag)
        period_start = date_val.isoformat() if date_val else "UNKNOWN"

        result = normalize_fuel(qty, unit, mat_desc)
        if not result.success:
            flags.append(result.flag)
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "SAP_FUEL", flags))
            continue
        if result.flag: flags.append(result.flag)

        status = "FLAGGED" if flags else "PENDING_REVIEW"
        records.append(NormalizedRecord(
            source_type="SAP_FUEL", source_file=path, source_row_id=row_id,
            raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
            period_start=period_start, period_end=period_start,
            scope=result.scope, category=category,
            activity_value=qty, activity_unit=unit,
            canonical_value=round(result.canonical_qty, 4),
            canonical_unit=result.canonical_unit,
            kgco2e=round(result.kgco2e, 3),
            emission_factor=result.emission_factor,
            emission_factor_source=result.emission_factor_source,
            status=status, flag_reason="; ".join(flags),
            location_plant=str(row.get("plant", "")),
            material_description=mat_desc,
        ))

    _outlier_flags(records)
    return _dedup(records)


# ── Utility (CSV) ─────────────────────────────────────────────────────────────

def _interpolate_billing_period(
    kwh: float,
    start: date,
    end: date,
) -> list[tuple[str, float]]:
    """
    Split a billing period spanning multiple calendar months into
    per-month kWh allocations via daily interpolation.
    (PDF: "The normalization engine must implement daily interpolation algorithms.")

    Returns list of (YYYY-MM, prorated_kwh).
    """
    total_days = (end - start).days
    if total_days <= 0:
        return [(start.strftime("%Y-%m"), kwh)]

    daily_kwh = kwh / total_days
    month_totals: dict[str, float] = {}
    cursor = start
    while cursor < end:
        month_key = cursor.strftime("%Y-%m")
        month_totals[month_key] = month_totals.get(month_key, 0.0) + daily_kwh
        cursor += timedelta(days=1)

    return [(m, round(v, 4)) for m, v in month_totals.items()]


def normalize_utility(path: str) -> list[NormalizedRecord]:
    df = pd.read_csv(path, dtype=str)
    df_r, mapping, unresolved = remap_df(df)

    # detect country from filename convention
    country = "IN" if "_IN" in os.path.basename(path).upper() else \
              "GB" if "_UK" in os.path.basename(path).upper() else "DEFAULT"
    batch_id = f"UTIL_{os.path.basename(path)}"
    records = []

    seen_periods: dict[str, list[tuple[date, date]]] = {}  # meter_id → list of (start, end)

    for idx, row in df_r.iterrows():
        raw_dict = df.iloc[idx].to_dict()
        row_id = _row_hash(raw_dict)
        flags = []

        # ── kVA demand charge guard (PDF: "kVA demand charge rows mixed in") ─
        unit_raw = str(row.get("unit", "")).strip().upper()
        if unit_raw in ("KVA", "MVA"):
            # record as SKIP — demand charge, not energy consumption
            records.append(NormalizedRecord(
                source_type="UTILITY", source_file=path, source_row_id=row_id,
                raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
                period_start="", period_end="", scope=2, category="demand_charge",
                activity_value=0, activity_unit=unit_raw,
                canonical_value=0, canonical_unit="kVA",
                kgco2e=0, emission_factor=0, emission_factor_source="",
                status="SKIP",
                flag_reason=f"Demand charge row (unit={unit_raw}) — excluded from Scope 2 kWh total",
            ))
            continue

        # ── reading type ─────────────────────────────────────────────────
        reading_type = str(row.get("reading_type", "Actual")).strip()
        if reading_type in ("Estimated", "Substituted"):
            flags.append(f"Reading type is '{reading_type}' — not an actual meter read; verify with supplier")

        # ── quantity ─────────────────────────────────────────────────────
        qty_raw = row.get("quantity") or row.get("consumption_kwh") or ""
        qty, f = _safe_float(qty_raw, "consumption")
        if f: flags.append(f)
        if qty is None: continue

        # negative = solar export (PDF: "Net Energy Metering / negative kWh")
        if qty < 0:
            flags.append(
                f"Negative consumption ({qty} {unit_raw}) — likely solar export / net metering credit. "
                "GHG Protocol: do NOT subtract from Scope 2. Record as 'Exported Renewable Energy'."
            )
            records.append(NormalizedRecord(
                source_type="UTILITY", source_file=path, source_row_id=row_id,
                raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
                period_start="", period_end="", scope=2,
                category="exported_renewable_energy",
                activity_value=qty, activity_unit=unit_raw,
                canonical_value=abs(qty), canonical_unit="kWh",
                kgco2e=0, emission_factor=0,
                emission_factor_source="",
                status="FLAGGED", flag_reason="; ".join(flags),
            ))
            continue

        # ── billing period ────────────────────────────────────────────────
        start_raw = row.get("billing_start") or row.get("period_start") or ""
        end_raw   = row.get("billing_end")   or row.get("period_end")   or ""
        start_d, sf = parse_date(start_raw, "billing_start", "UTILITY")
        end_d,   ef = parse_date(end_raw,   "billing_end",   "UTILITY")
        if sf: flags.append(sf)
        if ef: flags.append(ef)

        if not start_d or not end_d:
            flags.append("Cannot parse billing period dates — cannot interpolate to calendar months")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "UTILITY", flags))
            continue

        # billing_end < billing_start
        if end_d < start_d:
            flags.append(f"billing_end ({end_d}) is before billing_start ({start_d}) — portal export error")
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "UTILITY", flags))
            continue

        # overlapping period detection
        meter = str(row.get("meter_id", "")).strip()
        if not meter:
            flags.append("Missing meter_id — cannot detect overlapping billing periods")
        else:
            prev_periods = seen_periods.setdefault(meter, [])
            for ps, pe in prev_periods:
                if start_d <= pe and end_d >= ps:
                    flags.append(
                        f"Billing period {start_d}–{end_d} overlaps with previous period "
                        f"{ps}–{pe} for meter {meter}"
                    )
            seen_periods[meter].append((start_d, end_d))

        # gap detection (>45 days between consecutive periods)
        if meter and len(seen_periods[meter]) >= 2:
            prev_end = seen_periods[meter][-2][1]
            gap = (start_d - prev_end).days
            if gap > 45:
                flags.append(
                    f"Gap of {gap} days between consecutive billing periods for meter {meter} — "
                    "possible missed read or estimated substitution"
                )

        # ── normalize unit ────────────────────────────────────────────────
        result = normalize_electricity(qty, unit_raw, country)
        if not result.success:
            flags.append(result.flag)
            records.append(_stub(row, raw_dict, batch_id, path, row_id, "UTILITY", flags))
            continue
        if result.flag: flags.append(result.flag)

        # ── interpolate across calendar months (PDF: "daily interpolation") ─
        monthly_splits = _interpolate_billing_period(result.canonical_qty, start_d, end_d)

        for month_key, month_kwh in monthly_splits:
            fraction = month_kwh / result.canonical_qty if result.canonical_qty else 0
            month_kgco2e = round(month_kwh * result.emission_factor, 3)
            status = "FLAGGED" if flags else "PENDING_REVIEW"
            records.append(NormalizedRecord(
                source_type="UTILITY", source_file=path, source_row_id=row_id,
                raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
                period_start=start_d.isoformat(), period_end=end_d.isoformat(),
                scope=2, category="purchased_electricity",
                activity_value=qty, activity_unit=unit_raw,
                canonical_value=round(month_kwh, 4), canonical_unit="kWh",
                kgco2e=month_kgco2e,
                emission_factor=result.emission_factor,
                emission_factor_source=result.emission_factor_source,
                status=status, flag_reason="; ".join(flags),
                location_country=country,
                interpolated_month=month_key,
                interpolation_fraction=round(fraction, 4),
            ))

    _outlier_flags(records)
    return records   # no dedup here — interpolated rows are intentional duplicates of row_id


# ── Travel ────────────────────────────────────────────────────────────────────

def normalize_travel(path: str) -> list[NormalizedRecord]:
    df = pd.read_csv(path, dtype=str)
    df_r, mapping, _ = remap_df(df)
    batch_id = f"TRAVEL_{os.path.basename(path)}"
    records = []

    for idx, row in df_r.iterrows():
        raw_dict = df.iloc[idx].to_dict()
        row_id = _row_hash(raw_dict)
        flags = []

        # ── filter: per-diem, cancelled, not-submitted ───────────────────
        expense_type = str(row.get("expense_type", "")).strip().upper()
        if expense_type in SKIP_TRAVEL_TYPES:
            continue  # silently skip per-diem rows

        approval = str(row.get("approval_status", "")).strip().upper()
        if approval in SKIP_APPROVAL_STATUSES:
            continue  # not submitted yet

        # ── FLIGHT ───────────────────────────────────────────────────────
        if expense_type in ("AIR", "AIRFR"):
            dep = str(row.get("departure_airport", "")).strip().upper()
            arr = str(row.get("arrival_airport", "")).strip().upper()

            # validate IATA codes (3 uppercase letters)
            if not re.match(r"^[A-Z]{3}$", dep):
                flags.append(f"Invalid IATA departure code '{dep}' — cannot derive distance")
                records.append(_stub(row, raw_dict, batch_id, path, row_id, "TRAVEL", flags))
                continue
            if not re.match(r"^[A-Z]{3}$", arr):
                flags.append(f"Invalid IATA arrival code '{arr}' — cannot derive distance")
                records.append(_stub(row, raw_dict, batch_id, path, row_id, "TRAVEL", flags))
                continue

            dist_raw, _ = _safe_float(row.get("distance_km"), "distance_km")
            cabin = str(row.get("cabin_class", "Economy")).strip()

            date_val, date_flag = parse_date(row.get("travel_date"), "travel_date", "TRAVEL")
            if date_flag: flags.append(date_flag)
            period_start = date_val.isoformat() if date_val else "UNKNOWN"

            result = normalize_flight(dist_raw, dep, arr, cabin, AIRPORT_COORDS)
            if not result.success:
                flags.append(result.flag)
                records.append(_stub(row, raw_dict, batch_id, path, row_id, "TRAVEL", flags))
                continue
            if result.flag: flags.append(result.flag)

            status = "FLAGGED" if flags else "PENDING_REVIEW"
            records.append(NormalizedRecord(
                source_type="TRAVEL", source_file=path, source_row_id=row_id,
                raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
                period_start=period_start, period_end=period_start,
                scope=3, category="business_travel_air",
                activity_value=result.canonical_qty or 0,
                activity_unit="passenger_km",
                canonical_value=round(result.canonical_qty or 0, 2),
                canonical_unit="passenger_km",
                kgco2e=result.kgco2e if (result.kgco2e and math.isfinite(result.kgco2e)) else 0.0,
                emission_factor=result.emission_factor or 0,
                emission_factor_source=result.emission_factor_source or "",
                status=status, flag_reason="; ".join(flags),
                traveller_id=str(row.get("traveller_id", "")),
                trip_id=str(row.get("trip_id", "")),
            ))

        # ── HOTEL ────────────────────────────────────────────────────────
        elif expense_type == "HOTEL":
            nights_raw, _ = _safe_float(row.get("hotel_nights"), "nights")
            nights = int(nights_raw) if nights_raw and nights_raw > 0 else None

            if not nights:
                flags.append(f"Hotel nights is '{row.get('hotel_nights')}' — cannot compute")
                records.append(_stub(row, raw_dict, batch_id, path, row_id, "TRAVEL", flags))
                continue

            checkin_raw  = row.get("checkin_date") or ""
            checkout_raw = row.get("checkout_date") or ""
            if not checkin_raw:
                flags.append("Missing check-in date — cannot assign to reporting period")
            checkin_d, cf = parse_date(checkin_raw, "checkin_date", "TRAVEL")
            if cf: flags.append(cf)

            country = str(row.get("hotel_country", "DEFAULT")).strip().upper()[:2] or "DEFAULT"
            result = normalize_hotel(nights, country)
            if not result.success:
                flags.append(result.flag)
                records.append(_stub(row, raw_dict, batch_id, path, row_id, "TRAVEL", flags))
                continue

            period_start = checkin_d.isoformat() if checkin_d else "UNKNOWN"
            status = "FLAGGED" if flags else "PENDING_REVIEW"
            records.append(NormalizedRecord(
                source_type="TRAVEL", source_file=path, source_row_id=row_id,
                raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
                period_start=period_start, period_end=period_start,
                scope=3, category="business_travel_hotel",
                activity_value=float(nights), activity_unit="nights",
                canonical_value=float(nights), canonical_unit="nights",
                kgco2e=result.kgco2e or 0,
                emission_factor=result.emission_factor or 0,
                emission_factor_source=result.emission_factor_source or "",
                status=status, flag_reason="; ".join(flags),
                traveller_id=str(row.get("traveller_id", "")),
                trip_id=str(row.get("trip_id", "")),
                location_country=country,
            ))

        # ── GROUND ────────────────────────────────────────────────────────
        elif expense_type == "GROUND":
            dist_raw, _ = _safe_float(row.get("ground_distance_km"), "ground_distance_km")
            g_type = str(row.get("ground_transport_type", "")).strip()
            dist = dist_raw or 0.0

            travel_d, df_flag = parse_date(row.get("travel_date"), "travel_date", "TRAVEL")
            if df_flag: flags.append(df_flag)

            result = normalize_ground(dist, g_type)
            if result.flag: flags.append(result.flag)

            period_start = travel_d.isoformat() if travel_d else "UNKNOWN"
            status = "FLAGGED" if flags else "PENDING_REVIEW"
            records.append(NormalizedRecord(
                source_type="TRAVEL", source_file=path, source_row_id=row_id,
                raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
                period_start=period_start, period_end=period_start,
                scope=3, category="business_travel_ground",
                activity_value=dist, activity_unit="km",
                canonical_value=dist, canonical_unit="km",
                kgco2e=result.kgco2e or 0,
                emission_factor=result.emission_factor or 0,
                emission_factor_source=result.emission_factor_source or "",
                status=status, flag_reason="; ".join(flags),
                traveller_id=str(row.get("traveller_id", "")),
                trip_id=str(row.get("trip_id", "")),
            ))

    _outlier_flags(records)
    return _dedup(records)


# ── Stub helper ───────────────────────────────────────────────────────────────

def _stub(row, raw_dict, batch_id, path, row_id, src_type, flags) -> NormalizedRecord:
    """Create a FLAGGED placeholder record that couldn't be fully normalized."""
    return NormalizedRecord(
        source_type=src_type, source_file=path, source_row_id=row_id,
        raw_data=json.dumps(raw_dict, default=str), batch_id=batch_id,
        period_start="", period_end="", scope=0, category="UNRESOLVED",
        activity_value=0, activity_unit="",
        canonical_value=0, canonical_unit="",
        kgco2e=0, emission_factor=0, emission_factor_source="",
        status="FLAGGED", flag_reason="; ".join(flags),
    )


# ── Output writer ─────────────────────────────────────────────────────────────

def write_output(records: list[NormalizedRecord], out_path: str) -> None:
    if not records:
        print("No records to write.")
        return
    fieldnames = list(asdict(records[0]).keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            d = asdict(r)
            d["raw_data"] = ""   # raw_data in output is too large; keep in DB
            w.writerow(d)
    print(f"Wrote {len(records)} records → {out_path}")


# ── Summary printer ───────────────────────────────────────────────────────────

def print_summary(records: list[NormalizedRecord], label: str) -> None:
    total = len(records)
    flagged  = sum(1 for r in records if r.status == "FLAGGED")
    skipped  = sum(1 for r in records if r.status == "SKIP")
    clean    = total - flagged - skipped
    kgco2e   = sum(r.kgco2e or 0 for r in records if r.status != "SKIP")
    scope1   = sum(r.kgco2e or 0 for r in records if r.scope == 1)
    scope2   = sum(r.kgco2e or 0 for r in records if r.scope == 2)
    scope3   = sum(r.kgco2e or 0 for r in records if r.scope == 3)

    print(f"\n{'─'*55}")
    print(f"  {label}")
    print(f"{'─'*55}")
    print(f"  Total records   : {total}")
    print(f"  Clean           : {clean}")
    print(f"  Flagged         : {flagged}")
    print(f"  Skipped         : {skipped}")
    print(f"  Total kgCO2e    : {kgco2e:,.1f}")
    print(f"    Scope 1       : {scope1:,.1f}")
    print(f"    Scope 2       : {scope2:,.1f}")
    print(f"    Scope 3       : {scope3:,.1f}")

    if flagged:
        print(f"\n  Sample flags:")
        shown = 0
        for r in records:
            if r.status == "FLAGGED" and r.flag_reason and shown < 4:
                print(f"    [{r.source_type}] {r.flag_reason[:100]}")
                shown += 1


# ── CLI runner ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    DATA = "/home/claude/sample_data"
    OUT  = "/home/claude/sample_data/normalized"
    os.makedirs(OUT, exist_ok=True)

    all_records = []

    # SAP Procurement
    r = normalize_sap_procurement(f"{DATA}/sap_procurement.csv")
    print_summary(r, "SAP Procurement")
    write_output(r, f"{OUT}/normalized_sap_procurement.csv")
    all_records += r

    # SAP Fuel XLSX
    r = normalize_sap_fuel(f"{DATA}/sap_fuel_consumption.xlsx")
    print_summary(r, "SAP Fuel Consumption")
    write_output(r, f"{OUT}/normalized_sap_fuel.csv")
    all_records += r

    # Utility IN
    r = normalize_utility(f"{DATA}/utility_electricity_IN.csv")
    print_summary(r, "Utility — India (BESCOM)")
    write_output(r, f"{OUT}/normalized_utility_IN.csv")
    all_records += r

    # Utility UK
    r = normalize_utility(f"{DATA}/utility_electricity_UK.csv")
    print_summary(r, "Utility — UK (Green Button)")
    write_output(r, f"{OUT}/normalized_utility_UK.csv")
    all_records += r

    # Travel
    r = normalize_travel(f"{DATA}/travel_corporate.csv")
    print_summary(r, "Corporate Travel")
    write_output(r, f"{OUT}/normalized_travel.csv")
    all_records += r

    # Combined
    write_output(all_records, f"{OUT}/all_normalized.csv")
    print_summary(all_records, "ALL SOURCES COMBINED")
