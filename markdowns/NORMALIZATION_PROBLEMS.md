# Data Normalization Obstacles & Technical Fixes

This document details the major data engineering challenges we faced when normalizing fragmented enterprise telemetry for our carbon ledger, and how we solved them programmatically in our backend.

---

## 1. Schema Drift & Diverse Column Headers

### The Challenge
Different ERP models, regional factories, or utility portals export the exact same logical column using completely different heading names. A parser looking for `"Quantity"` will crash or skip records if a German plant exports `"MENGE"`, a legacy system uses `"QTY"`, or a utility portal shifts from `"consumption"` to `"usage_kwh"`.

* **Real-world Examples**: 
  * [sap_procurement.csv](file:///c:/PROJECTSSS/esg/sample_data/sap/sap_procurement.csv) uses `MENGE` (German header).
  * [utility_electricity_IN.csv](file:///c:/PROJECTSSS/esg/sample_data/utility/utility_electricity_IN.csv) uses `consumption`.
  * [utility_electricity_UK.csv](file:///c:/PROJECTSSS/esg/sample_data/utility/utility_electricity_UK.csv) uses `consumption_kwh`.

### The Solution (Lexical Translation Matrix)
We built a translation layer that runs during parsing. It trims, lowercases, and strips special characters from column headers, mapping them to standard internal keys.

```python
class ColumnNormalizer:
    ALIAS_MAP = {
        'quantity': ['menge', 'qty', 'quantity', 'consumption', 'consumption_kwh', 'entry_qnt', 'amount_value'],
        'unit': ['meins', 'meins_unit', 'unit', 'entry_uom', 'mengeneinheit', 'uom'],
        'posting_date': ['budat', 'postingdate', 'posting_date', 'travel_date', 'period_start', 'billing_start', 'buchungsdatum'],
        'location': ['werks', 'plant', 'site_name', 'hotel_city', 'departure_airport']
    }

    @classmethod
    def resolve_header(cls, header: str) -> str:
        cleaned = header.strip().lower().replace(".", "_").replace(" ", "_")
        for standard_name, aliases in cls.ALIAS_MAP.items():
            if cleaned == standard_name or cleaned in aliases:
                return standard_name
        return cleaned  # Fallback to the original header if no alias matches
```

---

## 2. Delimited Positional File Formats (Flat IDocs)

### The Challenge
Legacy mainframes and older SAP configurations export data as positional flat files rather than structured CSVs or JSON. These files contain zero headers. Instead, columns are delimited by hardcoded character indices (e.g. quantity starts at index 63 and spans 15 characters). Slicing the wrong index leads to corrupted string reads.

### The Solution (Index-Based Parsing)
Our parser reads positional files line-by-line, identifies the segment identifier (first 10 characters), and applies standard position mapping rules based on the SAP Data Dictionary schemas.

```python
def parse_positional_idoc_line(line: str):
    segment_type = line[0:10].strip()
    
    if segment_type == "E2EDP01005":
        # Positional mappings from standard ORDERS segment definition
        line_item_num = line[48:54].strip()
        raw_quantity = line[63:77].strip()
        raw_unit = line[77:81].strip()
        price_per_unit = line[87:102].strip()
        weight = line[154:172].strip()
        weight_unit = line[172:180].strip()
        
        return {
            "type": "ITEM",
            "item_number": line_item_num,
            "quantity": float(raw_quantity),
            "unit": raw_unit,
            "price": float(price_per_unit),
            "weight": float(weight),
            "weight_unit": weight_unit
        }
    elif segment_type == "E2EDP19001" and current_item:
        # Material description segment
        description = line[46:136].strip()
        return {
            "type": "ITEM_DESCRIPTION",
            "description": description
        }
    return None
```

---

## 3. Locale-Specific Number Formatting

### The Challenge
German and European SAP systems use different decimal and thousands separators compared to standard US systems. For example, a quantity of 1500 is formatted as `"1.500,00"` (Germany) instead of `"1,500.00"` (US). A naive `float("1.500,00")` parser will immediately crash with a `ValueError`.

### The Solution (Separator Coercion)
We clean and normalize raw strings before parsing, stripping thousands separators and mapping decimal commas to standard periods.

```python
def sanitize_decimal(val_str: str) -> float:
    cleaned = val_str.strip()
    if not cleaned:
        return 0.0
    # Swap separators if both are present
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:  # E.g., XX,YY (decimal comma)
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')  # E.g., X,YYY (thousands separator)
    return float(cleaned)
```

---

## 4. Billing Duration Differences & Monthly Proration

### The Challenge
Utility bills run on variable billing cycles (e.g., March 12 to April 10) instead of perfect calendar months. If we assign the entire consumption to a single month, we distort historical trends and report inaccurate carbon metrics for specific periods.

### The Solution (Daily Linear Splits)
We compute the duration of the bill in days, calculate a daily average consumption rate, and split the bill into prorated entries for each calendar month. This ensures our monthly ledger reports are perfectly aligned with calendar intervals.

---

## 5. Timezone Changes & Smart Meter Rollback Duplicates

### The Challenge
Electricity interval feeds are usually logged in local time. During autumn Daylight Savings (DST) transitions, the clock rolls back (e.g., from 2:00 AM to 1:00 AM). This results in the same hour appearing **twice** in the file. Simple database tables will reject this as a duplicate key error, losing valuable consumption data.

### The Solution (UTC Timezone Anchoring)
The ingestion parser immediately maps all timestamps to Coordinated Universal Time (UTC) using the localized facility metadata timezone. Rollbacks and shifts are grouped and resolved on absolute UTC boundaries before they are committed to the activity database.

```python
from datetime import datetime
import pytz

def localize_to_utc(dt_str: str, timezone_name: str) -> datetime:
    # E.g. dt_str = "2025-10-26 01:30:00", timezone_name = "Europe/London"
    naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    local_tz = pytz.timezone(timezone_name)
    # is_dst=None raises an error on ambiguous rollback times, forcing offset resolution
    local_dt = local_tz.localize(naive_dt, is_dst=None) 
    return local_dt.astimezone(pytz.utc)
```

---

## 6. Airport Coordinates Lookup & haversine Distance Calculations

### The Challenge
Corporate travel tools (like Concur or Navan) rarely export flight distances; they only provide 3-letter IATA airport codes (e.g., `LHR`, `JFK`). However, carbon databases calculate emissions strictly on passenger-kilometers.

### The Solution (Geospatial Lookup + Uplift)
We maintain a pre-seeded local airport database with lat/long coordinates. The backend resolves the IATA codes, calculates the great-circle distance using the **Haversine formula**, and applies a standard **8% detour uplift factor** to satisfy ESG auditing guidelines.

---

## 7. Travel Cancellations & Retroactive Auditing Conflicts

### The Challenge
Business travel bookings are highly volatile and frequently cancelled or amended. If an analyst has locked and audited the carbon ledger for January, and a trip is subsequently cancelled in March, changing January's locked data violates financial auditing standards.

### The Solution (Double-Entry Carbon Accounting)
Instead of editing historical, locked database rows, our ingestion engine uses a double-entry accounting approach. If a cancellation is received for an already locked/audited transaction ID, the parser writes a **compensating ledger entry** (a negative carbon quantity) in the *current, open month* to balance the books, maintaining perfect historical audit integrity.
