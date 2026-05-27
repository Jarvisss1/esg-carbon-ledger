from __future__ import annotations
from thefuzz import fuzz
import pandas as pd
import re

ALIAS_MAP: dict[str, list[str]] = {
    "company_code": [
        "BUKRS", "Buchungskreis", "company_code", "company code",
        "CompanyCode", "co_code", "entity_code", "legal_entity",
    ],
    "plant": [
        "WERKS", "Werk", "plant", "plant_code", "facility_code",
        "facility", "site_code", "site", "location_code",
        "PlantCode", "plant_id",
    ],
    "storage_location": [
        "LGORT", "Lagerort", "storage_location", "storage_loc",
        "StorageLocation", "store_loc", "warehouse_loc",
    ],
    "cost_centre": [
        "KOSTL", "Kostenstelle", "cost_centre", "cost_center",
        "CostCenter", "CostCentre", "cc_code", "cost_code",
    ],
    "quantity": [
        "MENGE", "Menge", "quantity", "qty", "volume",
        "consumption", "usage", "amount_qty", "Quantity",
        "consumption_kwh", "kwh", "kwh_consumed",
        "QuantityInEntryUnit",
    ],
    "unit": [
        "MEINS", "Basiseinheit", "Mengeneinheit", "unit", "UOM",
        "unit_of_measure", "BaseUnit", "EntryUnit", "EntryUnitISOCode",
        "measurement_unit", "measure_unit", "uom_code",
    ],
    "posting_date": [
        "BUDAT", "Buchungsdatum", "posting_date", "PostingDate",
        "post_date", "transaction_date", "date", "Date",
        "PSTNG_DATE", "recorded_date",
    ],
    "document_number": [
        "BELNR", "Belegnummer", "document_number", "doc_number",
        "doc_no", "document_no", "MaterialDocument", "PO_number",
        "BELNR_doc",
    ],
    "material_number": [
        "MATNR", "Materialnummer", "material_number", "material_no",
        "material_id", "MaterialNumber", "item_code", "product_code",
        "SKU",
    ],
    "material_description": [
        "MAKTX", "material_description", "material_name", "item_name",
        "product_name", "MaterialDescription", "description",
    ],
    "vendor": [
        "LIFNR", "Lieferant", "vendor", "vendor_code", "vendor_id",
        "supplier", "supplier_code", "VendorCode",
    ],
    "net_value": [
        "NETWR", "Nettowert", "net_value", "net_amount", "amount",
        "net_price", "NetValue", "value",
    ],
    "currency": [
        "WAERS", "Währung", "currency", "CurrencyCode", "currency_code",
        "curr", "CCY",
    ],
    "movement_type": [
        "BWART", "Bewegungsart", "movement_type", "GoodsMovementType",
        "move_type", "mvt_type", "MOVE_TYPE",
    ],
    "fixed_asset": [
        "masterfixedasset", "asset", "anln1", "MasterFixedAsset", "fixed_asset", "fixed_asset_id"
    ],
    "fiscal_year": [
        "GJAHR", "Geschäftsjahr", "fiscal_year", "FiscalYear",
        "year", "reporting_year",
    ],
    "fiscal_period": [
        "MONAT", "Monat", "fiscal_period", "period", "month",
        "reporting_month", "billing_month",
    ],
    "meter_id": [
        "meter_id", "MeterId", "meter_number", "meter_no", "mpan",
        "MPAN", "meter_serial", "meter_identifier", "meter",
    ],
    "meter_name": [
        "meter_name", "meter_description", "MeterName", "site_name",
        "meter_label", "meter_desc",
    ],
    "billing_start": [
        "billing_start", "billing_period_start", "period_start",
        "bill_start", "start_date", "StartDate", "from_date",
        "read_start", "interval_start",
    ],
    "billing_end": [
        "billing_end", "billing_period_end", "period_end",
        "bill_end", "end_date", "EndDate", "to_date",
        "read_end", "interval_end",
    ],
    "tariff_code": [
        "tariff_code", "tariff", "TariffCode", "rate_code",
        "tariff_name", "tariff_band", "tariff_type",
        "rate_schedule", "rate_plan",
    ],
    "reading_from": [
        "reading_from", "meter_read_start", "start_read",
        "opening_read", "from_reading", "prev_reading",
    ],
    "reading_to": [
        "reading_to", "meter_read_end", "end_read",
        "closing_read", "to_reading", "curr_reading",
    ],
    "reading_type": [
        "reading_type", "ReadingType", "read_type", "is_estimated",
        "estimated", "read_status", "meter_read_type",
    ],
    "supplier": [
        "supplier", "utility_supplier", "energy_supplier",
        "utility_company", "provider", "UtilityName",
    ],
    "account_id": [
        "account_id", "AccountId", "account_number", "acc_no",
        "utility_account", "customer_account",
    ],
    "trip_id": [
        "trip_id", "TripId", "tour_id", "itinerary_id", "ItinLocator",
        "booking_id", "BookingId", "reservation_id", "journey_id",
        "trip_reference", "trip_ref", "travel_id", "ClientLocator",
    ],
    "expense_type": [
        "expense_type", "ExpenseType", "segment_type", "booking_type",
        "travel_type", "record_type", "type", "category",
        "expense_category", "trip_type",
    ],
    "expense_type_code": [
        "expense_type_code", "ExpenseTypeCode", "type_code",
        "expense_code", "category_code",
    ],
    "traveller_id": [
        "traveller_id", "traveler_id", "TravellerId", "TravelerId",
        "employee_id", "employeeId", "emp_id", "user_id",
        "staff_id", "LoginID",
    ],
    "traveller_name": [
        "traveller_name", "traveler_name", "passenger_name",
        "employee_name", "full_name", "name", "TravelerName",
    ],
    "departure_airport": [
        "departure_airport", "origin", "Origin", "dep_airport",
        "from_airport", "from_iata", "origin_iata", "dep_iata",
        "StartAirportCode", "from_code",
    ],
    "arrival_airport": [
        "arrival_airport", "destination", "Destination", "arr_airport",
        "to_airport", "to_iata", "dest_iata", "arr_iata",
        "EndAirportCode", "to_code",
    ],
    "cabin_class": [
        "cabin_class", "CabinClass", "ClassOfService", "fare_class",
        "class", "travel_class", "FlightClass", "BookingClass",
        "service_class",
    ],
    "airline": [
        "airline", "Airline", "carrier", "Carrier", "airline_name",
        "AirlineVendorCode", "operating_carrier",
    ],
    "flight_number": [
        "flight_number", "FlightNumber", "flight_no", "flt_number",
        "flight", "FlightNum",
    ],
    "distance_km": [
        "distance_km", "distance", "Distance", "DistanceKm",
        "flight_distance", "route_distance", "km", "miles",
        "segment_distance",
    ],
    "hotel_name": [
        "hotel_name", "HotelName", "property_name", "hotel",
        "accommodation", "lodging_name", "VendorName",
    ],
    "hotel_city": [
        "hotel_city", "city", "City", "destination_city",
        "hotel_location", "PropertyCity",
    ],
    "hotel_country": [
        "hotel_country", "country", "Country", "PropertyCountry",
        "destination_country",
    ],
    "checkin_date": [
        "checkin_date", "check_in_date", "CheckInDate",
        "StartDateLocal", "arrival_date", "hotel_start",
    ],
    "checkout_date": [
        "checkout_date", "check_out_date", "CheckOutDate",
        "EndDateLocal", "departure_date", "hotel_end",
    ],
    "hotel_nights": [
        "nights", "hotel_nights", "NumberOfNights", "num_nights",
        "stay_nights", "duration_nights",
    ],
    "ground_transport_type": [
        "ground_transport_type", "ground_type", "transport_type",
        "ground_mode", "TransportMode", "vehicle_type",
        "car_type", "GroundType",
    ],
    "ground_distance_km": [
        "ground_distance_km", "ground_distance", "road_distance",
        "drive_distance", "GroundDistanceKm",
    ],
    "approval_status": [
        "approval_status_code", "ApprovalStatusCode", "approval_status",
        "ApprovalStatus", "status", "Status", "report_status",
    ],
    "booking_date": [
        "booking_date", "BookingDate", "booked_date", "DateBookedLocal",
        "purchase_date", "order_date",
    ],
    "travel_date": [
        "travel_date", "TravelDate", "departure_date",
        "StartDateLocal", "journey_date", "flight_date",
    ],
}

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in ALIAS_MAP.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical

def _normalize_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())

def fuzzy_resolve(col_name: str, threshold: int = 82) -> str | None:
    col_norm = _normalize_col(col_name)
    best_score, best_canonical = 0, None
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        score = fuzz.token_set_ratio(col_norm, _normalize_col(alias))
        if score > best_score:
            best_score = score
            best_canonical = canonical
    return best_canonical if best_score >= threshold else None

def resolve_columns(
    df: pd.DataFrame,
    fuzzy_threshold: int = 82,
) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    unresolved: list[str] = []

    for col in df.columns:
        canonical = _ALIAS_TO_CANONICAL.get(col.lower())
        if canonical is None:
            canonical = fuzzy_resolve(col, fuzzy_threshold)

        if canonical:
            if canonical not in mapping:
                mapping[canonical] = col
        else:
            unresolved.append(col)

    return mapping, unresolved

def remap_df(df: pd.DataFrame, fuzzy_threshold: int = 82) -> tuple[pd.DataFrame, dict, list]:
    mapping, unresolved = resolve_columns(df, fuzzy_threshold)
    rename_dict = {v: k for k, v in mapping.items()}
    df_remapped = df.rename(columns=rename_dict)
    return df_remapped, mapping, unresolved
