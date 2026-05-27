"""
unit_normalizer.py
──────────────────
Unit conversion + emission factor application.

Sources used:
  - DEFRA 2023 Greenhouse Gas Reporting Conversion Factors
    (https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023)
  - ICAO carbon calculator methodology (uplift factor for flights)
  - UK grid: DEFRA 2023 "Purchased electricity - UK" = 0.20493 kgCO2e/kWh
  - India grid: CEA 2022 CO2 baseline = 0.82 kgCO2e/kWh

Design
──────
All fuel quantities are first converted to a canonical base unit (LITRES
for liquids, KG for solids/gases), then multiplied by the emission factor
(kgCO2e per canonical unit) to yield kgCO2e.

Electricity is converted to kWh, then multiplied by grid factor.

Travel distances (passenger-km) are multiplied by cabin-class-adjusted
factors.
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import re

# ── Unit conversion to canonical base ─────────────────────────────────────────
# Target base unit: LITRES for liquids, KG for solids, KWH for electricity

UNIT_TO_LITRES: dict[str, float] = {
    # liquid fuel
    "L": 1.0, "LTR": 1.0, "LITRE": 1.0, "LITRES": 1.0, "LITER": 1.0,
    "ML": 0.001,
    "M3": 1000.0, "CBM": 1000.0, "CUBICMETRE": 1000.0,
    "GAL": 3.78541,   # US gallon
    "IGL": 4.54609,   # Imperial gallon (UK)
    "USGAL": 3.78541,
    "BBL": 158.987,   # oil barrel
    "KL": 1000.0,     # kilolitre
}

UNIT_TO_KG: dict[str, float] = {
    # solid / compressed fuel
    "KG": 1.0, "KILOGRAM": 1.0, "KILOGRAMS": 1.0,
    "G": 0.001, "GRAM": 0.001,
    "TO": 1000.0, "T": 1000.0, "MT": 1000.0,   # metric ton
    "LB": 0.453592, "LBS": 0.453592,
    "TONNE": 1000.0, "TONNES": 1000.0,
    # natural gas: SAP often gives M3, convert to kg via density
    "M3_GAS": 0.717,   # methane at STP, kg/m³
}

UNIT_TO_KWH: dict[str, float] = {
    "KWH": 1.0, "kWh": 1.0, "kwh": 1.0,
    "MWH": 1000.0, "MWh": 1000.0, "mwh": 1000.0,
    "GWH": 1_000_000.0,
    "WH": 0.001,
    "KVA": None,      # demand charge — cannot convert to kWh, must flag
    "MVA": None,
}

# ── Emission factors (kgCO2e per canonical unit) ───────────────────────────────

# DEFRA 2023 — Fuel combustion (Scope 1)
# Source: DEFRA GHG Conversion Factors 2023, "Fuels" sheet
FUEL_EMISSION_FACTORS: dict[str, dict] = {
    # liquid fuels → kgCO2e per LITRE
    "DIESEL":           {"factor": 2.6187, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-diesel"},
    "HEAVYFUELOIL":     {"factor": 3.1790, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-hfo"},
    "PETROL":           {"factor": 2.3122, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-petrol"},
    "GASOIL":           {"factor": 2.7569, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-gasoil"},
    "ATF":              {"factor": 2.5400, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-atf"},  # Aviation Turbine Fuel
    "KEROSENE":         {"factor": 2.5200, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-kerosene"},
    # gaseous fuels → kgCO2e per KG
    "NATURALGAS":       {"factor": 2.0400, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-natgas"},
    "LPG":              {"factor": 1.5550, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-lpg"},
    "CNG":              {"factor": 2.0400, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-cng"},
    # solid fuels → kgCO2e per KG
    "COAL":             {"factor": 2.4230, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-coal"},
    "COKE":             {"factor": 3.1760, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-coke"},
    "BIOMASSPELLETS":   {"factor": 0.0390, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-biomass"},  # biogenic
    "LUBRICANTOIL":     {"factor": 2.6187, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-diesel"},  # proxy
    "REFRIGERANT":      {"factor": 1924.0, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-r410a"},  # R-410A GWP
    "SOLVENT":          {"factor": 2.3122, "base_unit": "L",  "scope": 3, "defra_ref": "DEFRA2023-F-petrol"},  # proxy, Scope 3 Cat 1
}

# Electricity grid factors → kgCO2e per kWh (Scope 2, location-based)
GRID_FACTORS: dict[str, float] = {
    "IN":  0.8200,   # India — CEA 2022 CO2 baseline database
    "GB":  0.2053,   # UK — DEFRA 2023 "UK electricity"
    "US":  0.3860,   # USA — EPA eGRID 2022 national average
    "DE":  0.3850,   # Germany — UBA 2022
    "SG":  0.4080,   # Singapore — EMA 2022
    "AE":  0.4500,   # UAE — proxy
    "DEFAULT": 0.4330,  # Global average, IEA 2022
}

# Travel emission factors — DEFRA 2023 "Business Travel - Air"
# kgCO2e per passenger-km (already includes RFI where stated)
FLIGHT_FACTORS: dict[str, float] = {
    "ECONOMY":       {"short": 0.15553, "long": 0.19085},   # <1500 km / ≥1500 km
    "PREMIUMECONOMY":{"short": 0.15553, "long": 0.28627},
    "BUSINESS":      {"short": 0.22174, "long": 0.47019},
    "FIRST":         {"short": 0.22174, "long": 0.75078},
}
FLIGHT_UPLIFT = 1.08     # ICAO 8% distance uplift for routing inefficiency

# DEFRA 2023 "Business Travel - Hotels"
HOTEL_FACTOR_PER_NIGHT = {
    "DEFAULT": 21.4,   # kgCO2e per room per night — DEFRA 2023
    "IN":      18.0,   # India — lower energy intensity
    "GB":      17.5,
    "US":      29.0,
}

# DEFRA 2023 "Business Travel - Land"  kgCO2e per km
GROUND_FACTORS: dict[str, float] = {
    "TAXI":      0.14931,
    "UBER/OLA":  0.14931,   # proxy as taxi
    "COMPANYCAR":0.16844,
    "METRO":     0.02770,
    "RAIL":      0.03549,
    "TRAIN":     0.03549,
    "CARHIRE":   0.16844,
    "BUS":       0.10312,
    "DEFAULT":   0.14931,
}

# ── Material → fuel type lookup ───────────────────────────────────────────────
# Maps SAP material description fragments → canonical fuel type key
MATERIAL_TO_FUEL: list[tuple[str, str]] = [
    ("diesel",       "DIESEL"),
    ("heavy fuel",   "HEAVYFUELOIL"),
    ("hfo",          "HEAVYFUELOIL"),
    ("natural gas",  "NATURALGAS"),
    ("nat gas",      "NATURALGAS"),
    ("lpg",          "LPG"),
    ("propane",      "LPG"),
    ("petrol",       "PETROL"),
    ("gasoline",     "PETROL"),
    ("gas",          "PETROL"),
    ("atf",          "ATF"),
    ("aviation",     "ATF"),
    ("kerosene",     "KEROSENE"),
    ("coal",         "COAL"),
    ("coke",         "COKE"),
    ("biomass",      "BIOMASSPELLETS"),
    ("pellet",       "BIOMASSPELLETS"),
    ("lubricant",    "LUBRICANTOIL"),
    ("lubric",       "LUBRICANTOIL"),
    ("oil",          "LUBRICANTOIL"),
    ("refrigerant",  "REFRIGERANT"),
    ("r-410",        "REFRIGERANT"),
    ("solvent",      "SOLVENT"),
    ("generator",    "DIESEL"),   # "Generator Diesel"
]

def infer_fuel_type(material_description: str) -> str | None:
    """Match a SAP material description string to a canonical fuel type."""
    if not material_description:
        return None
    desc = material_description.lower()
    for fragment, fuel_key in MATERIAL_TO_FUEL:
        if fragment in desc:
            return fuel_key
    return None


# ── Unit normalisation ────────────────────────────────────────────────────────

@dataclass
class ConversionResult:
    success: bool
    canonical_qty: float | None  # in canonical unit (L or KG or kWh)
    canonical_unit: str | None
    kgco2e: float | None
    emission_factor: float | None
    emission_factor_source: str | None
    scope: int | None
    flag: str | None               # human-readable problem description


def normalize_fuel(
    raw_qty: float,
    raw_unit: str,
    material_description: str,
    fuel_type_override: str | None = None,
) -> ConversionResult:
    """
    Convert a SAP fuel / procurement record to kgCO2e.
    raw_unit is the SAP MEINS value.
    """
    unit_key = raw_unit.strip().upper()
    fuel_type = fuel_type_override or infer_fuel_type(material_description)

    if fuel_type is None:
        return ConversionResult(False, None, None, None, None, None, None,
            f"Cannot infer fuel type from description '{material_description}'")

    ef_record = FUEL_EMISSION_FACTORS.get(fuel_type)
    if ef_record is None:
        return ConversionResult(False, None, None, None, None, None, None,
            f"No emission factor for fuel type '{fuel_type}'")

    base_unit = ef_record["base_unit"]
    factor    = ef_record["factor"]
    scope     = ef_record["scope"]
    ref       = ef_record["defra_ref"]

    # Convert to canonical base unit
    if base_unit == "L":
        conv = UNIT_TO_LITRES.get(unit_key)
        if conv is None:
            # Try kg→L using diesel density 0.835 kg/L as fallback
            conv_kg = UNIT_TO_KG.get(unit_key)
            if conv_kg:
                canonical_qty = raw_qty * conv_kg / 0.835
                flag = f"Unit '{raw_unit}' treated as mass; converted to L via density 0.835 kg/L (diesel proxy)"
            else:
                return ConversionResult(False, None, None, None, None, None, None,
                    f"Unknown unit '{raw_unit}' for liquid fuel '{fuel_type}'")
        else:
            canonical_qty = raw_qty * conv
            flag = None

    elif base_unit == "KG":
        # Special case: SAP may give M3 for natural gas
        if unit_key == "M3":
            canonical_qty = raw_qty * UNIT_TO_KG["M3_GAS"]
            flag = "Natural gas M3 converted to KG via density 0.717 kg/m³"
        else:
            conv = UNIT_TO_KG.get(unit_key)
            if conv is None:
                return ConversionResult(False, None, None, None, None, None, None,
                    f"Unknown unit '{raw_unit}' for solid/gas fuel '{fuel_type}'")
            canonical_qty = raw_qty * conv
            flag = None
    else:
        return ConversionResult(False, None, None, None, None, None, None,
            f"Unexpected base_unit '{base_unit}' in emission factor table")

    kgco2e = canonical_qty * factor
    return ConversionResult(True, canonical_qty, base_unit, kgco2e, factor, ref, scope, flag)


def normalize_electricity(
    raw_qty: float,
    raw_unit: str,
    country_code: str = "DEFAULT",
) -> ConversionResult:
    """Convert a utility electricity record to kgCO2e."""
    unit_key = raw_unit.strip().upper()

    # kVA demand charge: cannot convert, must flag
    conv = UNIT_TO_KWH.get(unit_key) or UNIT_TO_KWH.get(raw_unit)  # try original case too
    if conv is None:
        return ConversionResult(False, None, None, None, None, None, None,
            f"Unknown electricity unit '{raw_unit}'")
    if conv is None or (unit_key in ("KVA", "MVA")):
        return ConversionResult(False, None, None, None, None, None, None,
            f"Unit '{raw_unit}' is a demand charge (kVA) — cannot convert to kWh for Scope 2")

    kwh = raw_qty * conv
    grid_factor = GRID_FACTORS.get(country_code.upper(), GRID_FACTORS["DEFAULT"])
    kgco2e = kwh * grid_factor
    ref = f"DEFRA2023-grid-{country_code.upper()}" if country_code in GRID_FACTORS else "IEA2022-global-avg"

    return ConversionResult(True, kwh, "kWh", kgco2e, grid_factor, ref, 2, None)


def normalize_flight(
    distance_km: float | None,
    dep_iata: str,
    arr_iata: str,
    cabin_class: str,
    airport_coords: dict,   # { IATA: (lat, lon) }
) -> ConversionResult:
    """
    Compute flight kgCO2e.
    If distance_km is None/blank, derive it via haversine.
    Apply ICAO 8% uplift, then DEFRA cabin-class factor.
    """
    import math

    # Step 1: get or derive distance
    if not distance_km:
        coords1 = airport_coords.get(dep_iata.upper())
        coords2 = airport_coords.get(arr_iata.upper())
        if not coords1:
            return ConversionResult(False, None, None, None, None, None, None,
                f"Unknown IATA code '{dep_iata}' — cannot derive distance")
        if not coords2:
            return ConversionResult(False, None, None, None, None, None, None,
                f"Unknown IATA code '{arr_iata}' — cannot derive distance")
        lat1, lon1 = map(math.radians, coords1)
        lat2, lon2 = map(math.radians, coords2)
        a = (math.sin((lat2-lat1)/2)**2 +
             math.cos(lat1) * math.cos(lat2) * math.sin((lon2-lon1)/2)**2)
        distance_km = round(6371 * 2 * math.asin(math.sqrt(a)), 1)
        dist_derived = True
    else:
        dist_derived = False

    if dep_iata.upper() == arr_iata.upper():
        return ConversionResult(False, None, None, None, None, None, None,
            "Departure airport equals arrival airport — data entry error")

    # Step 2: apply 8% ICAO uplift
    uplifted_km = distance_km * FLIGHT_UPLIFT

    # Step 3: resolve cabin class → DEFRA factor
    cabin_key = re.sub(r"[^a-zA-Z]", "", cabin_class).upper()
    # normalize common abbreviations
    cabin_map = {"Y": "ECONOMY", "W": "PREMIUMECONOMY", "J": "BUSINESS",
                 "C": "BUSINESS", "F": "FIRST"}
    cabin_key = cabin_map.get(cabin_key, cabin_key)

    factors = FLIGHT_FACTORS.get(cabin_key)
    if factors is None:
        cabin_key = "ECONOMY"
        factors = FLIGHT_FACTORS["ECONOMY"]
        flag_cabin = f"Unknown cabin class '{cabin_class}'; defaulted to Economy"
    else:
        flag_cabin = None

    ef = factors["short"] if distance_km < 1500 else factors["long"]
    kgco2e = uplifted_km * ef

    flag_parts = []
    if dist_derived:
        flag_parts.append(f"Distance derived via haversine ({distance_km:.0f} km)")
    if flag_cabin:
        flag_parts.append(flag_cabin)
    # Suspicious: business class on short hop
    if cabin_key in ("BUSINESS", "FIRST") and distance_km < 500:
        flag_parts.append(f"Business/First class on short route ({distance_km:.0f} km) — review required")

    return ConversionResult(
        True, uplifted_km, "passenger_km", round(kgco2e, 3),
        ef, f"DEFRA2023-air-{cabin_key.lower()}", 3,
        "; ".join(flag_parts) if flag_parts else None,
    )


def normalize_hotel(nights: int, country_code: str = "DEFAULT") -> ConversionResult:
    factor = HOTEL_FACTOR_PER_NIGHT.get(country_code.upper(),
                                        HOTEL_FACTOR_PER_NIGHT["DEFAULT"])
    if not nights or nights <= 0:
        return ConversionResult(False, None, None, None, None, None, None,
            f"Hotel nights is {nights} — cannot compute")
    kgco2e = nights * factor
    return ConversionResult(True, float(nights), "nights", round(kgco2e, 3),
        factor, "DEFRA2023-hotel", 3, None)


def normalize_ground(distance_km: float, transport_type: str) -> ConversionResult:
    key = re.sub(r"[^a-zA-Z/]", "", transport_type).upper()
    ef = GROUND_FACTORS.get(key, GROUND_FACTORS["DEFAULT"])
    flag = None
    if distance_km == 0:
        flag = f"Ground distance is 0 for '{transport_type}' — flat-rate fare, distance unknown; kgCO2e set to 0"
        kgco2e = 0.0
    else:
        kgco2e = distance_km * ef
    return ConversionResult(True, distance_km, "km", round(kgco2e, 3),
        ef, "DEFRA2023-ground", 3, flag)
