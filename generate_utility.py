"""
Utility Electricity Data Simulator
Simulates what a facilities team receives when they download billing history
from a utility portal — the kind of CSV you get from portals like:
  - BESCOM (Bangalore), TATA Power, Adani Electricity (India)
  - British Gas, EDF, SSE (UK)
  - Any portal following the Green Button CSV export standard (US)

Two files are generated:
  utility_electricity_IN.csv  — Indian facility (BESCOM-style)
  utility_electricity_UK.csv  — UK facility (Green Button-adjacent)

Realistic dirt injected:
  - Billing periods that are 28–35 days (never clean calendar months)
  - Mixed units: kWh, MWh, kVA (demand charge rows)
  - Peak / off-peak / night tariff rows for the same meter + period
  - Overlapping billing periods (portal bug or meter replacement)
  - Missing meter_id on one row (manual override entry)
  - Consumption spikes 10x normal (equipment fault, left something on)
  - Negative consumption (solar export / net metering credit)
  - Meter reading rollover (meter hit 99999 and restarted from 0)
  - Amount in wrong currency symbol (copy-paste from another portal)
  - Duplicate row with slightly different amount (amended bill)
  - One row where billing_end < billing_start (portal export bug)
  - kVA demand rows mixed in (demand charge, not energy — must not sum with kWh)
  - Gaps between billing periods (missed read, estimated later)
"""

import csv
import random
from datetime import date, timedelta
from decimal import Decimal

random.seed(7)

# ── helpers ────────────────────────────────────────────────────────────────────

def jitter_days(n, spread=4):
    """Return n ± spread. Simulates utility cycle drift."""
    return n + random.randint(-spread, spread)

def round2(x):
    return round(x, 2)

def random_consumption(base, spike_prob=0.04, solar_prob=0.03):
    """Return kWh with occasional spike or solar export (negative)."""
    if random.random() < spike_prob:
        return round2(base * random.uniform(8, 14))   # equipment fault
    if random.random() < solar_prob:
        return round2(-random.uniform(100, 800))       # net metering export
    return round2(base * random.uniform(0.75, 1.3))

# ── Indian facility (BESCOM-style) ─────────────────────────────────────────────

IN_METERS = {
    "MTR-IN-001": {"name": "Main Building - LT Supply",  "base_kwh": 18000, "tariff": "LT-2A"},
    "MTR-IN-002": {"name": "DG Set Meter",               "base_kwh":  3200, "tariff": "LT-2A"},
    "MTR-IN-003": {"name": "HVAC Block - HT Connection", "base_kwh": 42000, "tariff": "HT-1"},
    "MTR-IN-004": {"name": "Canteen + Common Areas",     "base_kwh":  4100, "tariff": "LT-2A"},
    "MTR-IN-005": {"name": "",                           "base_kwh":  9000, "tariff": "LT-2A"},  # missing name
}

IN_TARIFF_SPLITS = {
    "LT-2A": [("Peak",     0.45, 6.25),   # (tariff_band, fraction_of_usage, rate_per_kwh_INR)
              ("Off-Peak", 0.35, 4.50),
              ("Night",    0.20, 3.10)],
    "HT-1":  [("Peak",     0.50, 5.80),
              ("Off-Peak", 0.30, 4.20),
              ("Demand",   None, None)],   # demand charge row — unit is kVA not kWh
}

def generate_in_utility(path, months=14):
    rows = []
    fieldnames = [
        "meter_id", "meter_name", "billing_start", "billing_end",
        "tariff_code", "tariff_band", "reading_from", "reading_to",
        "consumption", "unit", "rate", "amount", "currency", "notes"
    ]

    for meter_id, meta in IN_METERS.items():
        cursor = date(2024, 1, 5) + timedelta(days=random.randint(0, 6))
        prev_reading = random.randint(10000, 50000)

        for i in range(months):
            cycle_days = jitter_days(30, spread=5)
            end = cursor + timedelta(days=cycle_days)

            kwh = random_consumption(meta["base_kwh"] / 12)
            tariff = meta["tariff"]
            bands = IN_TARIFF_SPLITS[tariff]

            # meter rollover simulation
            if prev_reading + int(kwh) > 99999:
                prev_reading = 0
            new_reading = prev_reading + int(kwh)

            for band, fraction, rate in bands:
                if band == "Demand":
                    # demand charge: kVA not kWh — this trips up naive summing
                    demand_kva = round2(meta["base_kwh"] / 12 / 720 * 1.3)
                    amount = round2(demand_kva * 180)  # 180 INR/kVA/month approx
                    row = {
                        "meter_id":      meter_id,
                        "meter_name":    meta["name"],
                        "billing_start": cursor.isoformat(),
                        "billing_end":   end.isoformat(),
                        "tariff_code":   tariff,
                        "tariff_band":   "Demand Charge",
                        "reading_from":  "",
                        "reading_to":    "",
                        "consumption":   demand_kva,
                        "unit":          "kVA",           # ← NOT kWh — must flag
                        "rate":          180,
                        "amount":        amount,
                        "currency":      "INR",
                        "notes":         "Maximum demand charge",
                    }
                else:
                    band_kwh = round2(kwh * fraction)
                    amount = round2(band_kwh * rate)
                    row = {
                        "meter_id":      meter_id,
                        "meter_name":    meta["name"],
                        "billing_start": cursor.isoformat(),
                        "billing_end":   end.isoformat(),
                        "tariff_code":   tariff,
                        "tariff_band":   band,
                        "reading_from":  prev_reading,
                        "reading_to":    new_reading,
                        "consumption":   band_kwh,
                        "unit":          "kWh",
                        "rate":          rate,
                        "amount":        amount,
                        "currency":      "INR",
                        "notes":         "",
                    }
                rows.append(row)

            # inject specific dirt per meter
            dirt = random.random()
            if dirt < 0.08 and i > 0:
                # overlapping period — end of previous overlaps with this start
                rows[-1]["billing_start"] = (cursor - timedelta(days=3)).isoformat()
                rows[-1]["notes"] = "Revised billing period"

            elif dirt < 0.12 and i == 3:
                # billing_end before billing_start (portal export bug)
                bad = dict(rows[-1])
                bad["billing_start"] = end.isoformat()
                bad["billing_end"] = cursor.isoformat()
                bad["notes"] = "Portal export error"
                rows.append(bad)

            elif dirt < 0.15 and i == 6:
                # duplicate with slightly different amount (amended bill)
                dup = dict(rows[-1])
                dup["amount"] = round2(dup["amount"] * 1.04)
                dup["notes"] = "Amended — surcharge applied"
                rows.append(dup)

            # gap: skip one month for MTR-IN-003 (estimated read, posted later)
            if meter_id == "MTR-IN-003" and i == 8:
                cursor = end + timedelta(days=jitter_days(62, spread=3))
            else:
                cursor = end + timedelta(days=1)

            prev_reading = new_reading

    _write_csv(path, fieldnames, rows)
    print(f"[Utility-IN] BESCOM-style CSV -> {path} ({len(rows)} rows)")


# ── UK facility (Green Button adjacent) ───────────────────────────────────────

UK_METERS = {
    "MTR-UK-001": {"name": "Office Block A - Domestic Supply", "base_kwh": 9200,  "supplier": "British Gas"},
    "MTR-UK-002": {"name": "Data Centre UPS Feed",            "base_kwh": 38000, "supplier": "EDF Energy"},
    "MTR-UK-003": {"name": "Car Park EV Chargers",            "base_kwh": 2100,  "supplier": "Octopus Energy"},
}

UK_TARIFF_BANDS = [("Day", 0.6, 0.28), ("Night", 0.4, 0.14)]  # fraction, £/kWh

def generate_uk_utility(path, months=14):
    rows = []
    fieldnames = [
        "account_id", "mpan", "meter_id", "supplier", "site_name",
        "period_start", "period_end", "tariff_name", "consumption_kwh",
        "unit", "unit_rate_gbp", "standing_charge_gbp",
        "total_amount_gbp", "vat_pct", "is_estimated", "notes"
    ]

    acct_counter = 900
    for meter_id, meta in UK_METERS.items():
        acct_counter += 1
        mpan = f"{''.join([str(random.randint(0,9)) for _ in range(13)])}"
        cursor = date(2024, 1, 15)
        is_mwh = (meter_id == "MTR-UK-002")   # data centre reports in MWh

        for i in range(months):
            cycle_days = jitter_days(30, spread=5)
            end = cursor + timedelta(days=cycle_days)
            kwh = random_consumption(meta["base_kwh"] / 12, spike_prob=0.03)

            for band, fraction, rate in UK_TARIFF_BANDS:
                band_kwh = round2(kwh * fraction)
                unit = "MWh" if is_mwh else "kWh"
                consumption = round2(band_kwh / 1000) if is_mwh else band_kwh
                amount = round2(band_kwh * rate)
                standing = round2(random.uniform(0.25, 0.35) * cycle_days)
                estimated = random.random() < 0.12   # 12% of reads are estimated

                row = {
                    "account_id":         f"ACC-{acct_counter}",
                    "mpan":               mpan,
                    "meter_id":           meter_id,
                    "supplier":           meta["supplier"],
                    "site_name":          meta["name"],
                    "period_start":       cursor.isoformat(),
                    "period_end":         end.isoformat(),
                    "tariff_name":        f"{band} Rate",
                    "consumption_kwh":    consumption,
                    "unit":               unit,
                    "unit_rate_gbp":      rate,
                    "standing_charge_gbp": standing,
                    "total_amount_gbp":   round2(amount + standing),
                    "vat_pct":            5.0,
                    "is_estimated":       estimated,
                    "notes":              "Estimated read" if estimated else "",
                }
                rows.append(row)

            cursor = end + timedelta(days=1)

        # inject: missing meter_id on one row (manual override)
        rows[random.randint(0, len(rows)-1)]["meter_id"] = ""

    _write_csv(path, fieldnames, rows)
    print(f"[Utility-UK] Green Button-style CSV -> {path} ({len(rows)} rows)")


# ── shared ─────────────────────────────────────────────────────────────────────

def _write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(base_dir, "sample_data", "utility")
    os.makedirs(out, exist_ok=True)
    generate_in_utility(os.path.join(out, "utility_electricity_IN.csv"))
    generate_uk_utility(os.path.join(out, "utility_electricity_UK.csv"))
    print("\nUtility sample data generated.")
