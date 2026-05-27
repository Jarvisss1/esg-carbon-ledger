from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import re

UNIT_TO_LITRES: dict[str, float] = {
    "L": 1.0, "LTR": 1.0, "LITRE": 1.0, "LITRES": 1.0, "LITER": 1.0,
    "ML": 0.001,
    "M3": 1000.0, "CBM": 1000.0, "CUBICMETRE": 1000.0,
    "GAL": 3.78541,
    "IGL": 4.54609,
    "USGAL": 3.78541,
    "BBL": 158.987,
    "KL": 1000.0,
}

UNIT_TO_KG: dict[str, float] = {
    "KG": 1.0, "KILOGRAM": 1.0, "KILOGRAMS": 1.0,
    "G": 0.001, "GRAM": 0.001,
    "TO": 1000.0, "T": 1000.0, "MT": 1000.0,
    "LB": 0.453592, "LBS": 0.453592,
    "TONNE": 1000.0, "TONNES": 1000.0,
    "M3_GAS": 0.717,
}

UNIT_TO_KWH: dict[str, float] = {
    "KWH": 1.0, "kWh": 1.0, "kwh": 1.0,
    "MWH": 1000.0, "MWh": 1000.0, "mwh": 1000.0,
    "GWH": 1_000_000.0,
    "WH": 0.001,
    "KVA": None,
    "MVA": None,
}

FUEL_EMISSION_FACTORS: dict[str, dict] = {
    "DIESEL":           {"factor": 2.6187, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-diesel"},
    "HEAVYFUELOIL":     {"factor": 3.1790, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-hfo"},
    "PETROL":           {"factor": 2.3122, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-petrol"},
    "GASOIL":           {"factor": 2.7569, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-gasoil"},
    "ATF":              {"factor": 2.5400, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-atf"},
    "KEROSENE":         {"factor": 2.5200, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-kerosene"},
    "NATURALGAS":       {"factor": 2.0400, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-natgas"},
    "LPG":              {"factor": 1.5550, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-lpg"},
    "CNG":              {"factor": 2.0400, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-cng"},
    "COAL":             {"factor": 2.4230, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-coal"},
    "COKE":             {"factor": 3.1760, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-coke"},
    "BIOMASSPELLETS":   {"factor": 0.0390, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-biomass"},
    "LUBRICANTOIL":     {"factor": 2.6187, "base_unit": "L",  "scope": 1, "defra_ref": "DEFRA2023-F-diesel"},
    "REFRIGERANT":      {"factor": 1924.0, "base_unit": "KG", "scope": 1, "defra_ref": "DEFRA2023-F-r410a"},
    "SOLVENT":          {"factor": 2.3122, "base_unit": "L",  "scope": 3, "defra_ref": "DEFRA2023-F-petrol"},
}

GRID_FACTORS: dict[str, float] = {
    "IN":  0.8200,
    "GB":  0.2053,
    "US":  0.3860,
    "DE":  0.3850,
    "SG":  0.4080,
    "AE":  0.4500,
    "DEFAULT": 0.4330,
}

FLIGHT_FACTORS: dict[str, float] = {
    "ECONOMY":       {"short": 0.15553, "long": 0.19085},
    "PREMIUMECONOMY":{"short": 0.15553, "long": 0.28627},
    "BUSINESS":      {"short": 0.22174, "long": 0.47019},
    "FIRST":         {"short": 0.22174, "long": 0.75078},
}
FLIGHT_UPLIFT = 1.08

HOTEL_FACTOR_PER_NIGHT = {
    "DEFAULT": 21.4,
    "IN":      18.0,
    "GB":      17.5,
    "US":      29.0,
}

GROUND_FACTORS: dict[str, float] = {
    "TAXI":      0.14931,
    "UBER/OLA":  0.14931,
    "COMPANYCAR":0.16844,
    "METRO":     0.02770,
    "RAIL":      0.03549,
    "TRAIN":     0.03549,
    "CARHIRE":   0.16844,
    "BUS":       0.10312,
    "DEFAULT":   0.14931,
}

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
    ("generator",    "DIESEL"),
]

def infer_fuel_type(material_description: str) -> str | None:
    if not material_description:
        return None
    desc = material_description.lower()
    for fragment, fuel_key in MATERIAL_TO_FUEL:
        if fragment in desc:
            return fuel_key
    return None

@dataclass
class ConversionResult:
    success: bool
    canonical_qty: float | None
    canonical_unit: str | None
    kgco2e: float | None
    emission_factor: float | None
    emission_factor_source: str | None
    scope: int | None
    flag: str | None

def normalize_fuel(
    raw_qty: float,
    raw_unit: str,
    material_description: str,
    fuel_type_override: str | None = None,
) -> ConversionResult:
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

    if base_unit == "L":
        conv = UNIT_TO_LITRES.get(unit_key)
        if conv is None:
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
    unit_key = raw_unit.strip().upper()

    conv = UNIT_TO_KWH.get(unit_key) or UNIT_TO_KWH.get(raw_unit)
    if conv is None:
        return ConversionResult(False, None, None, None, None, None, None,
            f"Unknown electricity unit '{raw_unit}'")
    if unit_key in ("KVA", "MVA"):
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
    airport_coords: dict,
) -> ConversionResult:
    import math

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

    uplifted_km = distance_km * FLIGHT_UPLIFT

    cabin_key = re.sub(r"[^a-zA-Z]", "", cabin_class).upper()
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
    if cabin_key in ("BUSINESS", "FIRST") and distance_km < 500:
        flag_parts.append(f"Business/First class on short route ({distance_km:.0f} km) — review required")

    return ConversionResult(
        True, uplifted_km, "passenger_km", round(kgco2e, 3),
        ef, f"DEFRA2023-air-{cabin_key.lower()}", 3,
        "; ".join(flag_parts) if flag_parts else None,
    )

def normalize_hotel(nights: int, country_code: str = "DEFAULT") -> ConversionResult:
    factor = HOTEL_FACTOR_PER_NIGHT.get(country_code.upper(), HOTEL_FACTOR_PER_NIGHT["DEFAULT"])
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
