# Enterprise ESG Data Normalization Problems & Technical Fixes

This document outlines the major data engineering obstacles encountered when normalizing fragmented enterprise telemetry for carbon accounting audits, detailing how the platform resolves them programmatically.

---

## Problem 1: Schema Drift & Diverse Column Headers
### The Issue
Different ERP modules, regional plants, or utility portals export the exact same logical column using entirely different heading names. A standard parser looking for `"Quantity"` will crash or skip records if a German plant exports `"MENGE"`, a legacy CSV uses `"QTY"`, or a utility portal shifts from `"consumption"` to `"usage_kwh"`.
* **Example in generated data**: 
  * [sap_procurement.csv](file:///c:/PROJECTSSS/esg/sample_data/sap/sap_procurement.csv) uses `MENGE` (German header).
  * [utility_electricity_IN.csv](file:///c:/PROJECTSSS/esg/sample_data/utility/utility_electricity_IN.csv) uses `consumption`.
  * [utility_electricity_UK.csv](file:///c:/PROJECTSSS/esg/sample_data/utility/utility_electricity_UK.csv) uses `consumption_kwh`.

### The Technical Fix (Implemented in Parser Backend)
We implement a **Lexical translation matrix** that performs header normalization during parsing. Column headers are trimmed, lowercased, stripped of special characters, and matched against an alias index.

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
        return cleaned  # Return original if no match
```

---

## Problem 2: Positional Flat-File Parsing (Flat IDocs)
### The Issue
Legacy mainframe integrations and older SAP configurations export data as positional flat files (such as [ORDERS.idoc](file:///c:/PROJECTSSS/esg/ORDERS.idoc)) rather than structured CSVs or XML. These files contain zero column headers. Instead, columns are delimited by hardcoded character indices (e.g. quantities start at character index 63 and span 15 characters, UoM starts at index 78). Slicing the wrong index leads to corrupted string reads.

### The Technical Fix (Implemented in IDoc Parser)
We implement segment-based **positional index parsing**. The parser reads the file line-by-line, identifies the segment identifier (first 10 characters), and applies standard position mapping rules based on the SAP Data Dictionary schemas.

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
    elif segment_type == "E2EDP19001":
        # Material description segment
        description = line[46:136].strip()
        return {
            "type": "ITEM_DESCRIPTION",
            "description": description
        }
    return None
```

---

## Problem 3: Locale-Specific Number Formatting
### The Issue
German and European SAP systems use different decimal and thousands separators compared to standard US systems. For example, a quantity of 1500 is formatted as `"1.500,00"` (Germany) instead of `"1,500.00"` (US). A naive `float("1.500,00")` parser will immediately crash with a `ValueError`. 

### The Technical Fix
We sanitize raw quantities before casting, stripping thousands separators and coercing the regional decimal comma into a standard decimal period.
```python
def sanitize_decimal(val_str: str) -> float:
    cleaned = val_str.strip()
    if not cleaned:
        return 0.0
    # If commas and periods are both present, or commas are at the end, swap
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # Check if comma represents decimal or thousand (e.g. 1,500 vs 1,50)
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:  # typical decimal representation: XX,YY
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')  # typical thousand separator: X,YYY
    return float(cleaned)
```

---

## Problem 4: Temporal Misalignment & Monthly Proration
### The Issue
Utility billing cycles span random durations (e.g., March 12 to April 10) instead of matching calendar reporting boundaries. Assigning the whole bill to one month distorts metrics.

### The Technical Fix
We calculate aggregate days, establish a daily linear consumption rate, and split the bill into prorated records spanning each respective month in the universal normalized layer (refer to [MODEL.md](file:///c:/PROJECTSSS/esg/markdowns/MODEL.md) Section 3 for equations).

---

## Problem 5: Timezone Shifts and DST Smart-Meter Duplicate Intervals
### The Issue
Smart meter interval files from the UK are exported in local time. During Daylight Savings Time (DST) changes in autumn, clocks roll back from 2:00 AM to 1:00 AM. This results in the 1:00 AM–2:00 AM hour appearing **twice** in the dataset. A standard time-series database will reject the duplicate timestamp, causing data loss.

### The Technical Fix
The ingestion engine immediately casts all incoming timestamps to absolute Coordinated Universal Time (UTC) using the localized facility metadata timezone. Gaps or duplicates are resolved by grouping and summing interval data on absolute UTC boundaries before inserting them into the activity ledger.

```python
from datetime import datetime
import pytz

def localize_to_utc(dt_str: str, timezone_name: str) -> datetime:
    # E.g. dt_str = "2025-10-26 01:30:00", timezone_name = "Europe/London"
    naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    local_tz = pytz.timezone(timezone_name)
    # is_dst=None raises an error on ambiguous rollback times, forcing timezone offset resolution
    local_dt = local_tz.localize(naive_dt, is_dst=None) 
    return local_dt.astimezone(pytz.utc)
```

---

## Problem 6: Spatial Coordinates Deficiency (No Flight Distances)
### The Issue
Corporate Travel APIs (Concur, Navan) omit flight distances, exporting only 3-letter IATA airport codes (e.g., `LHR`, `JFK`). Emission factor databases compute carbon strictly based on passenger-kilometers.

### The Technical Fix
We maintain an embedded coordinate lookup table in our database. We resolve airport codes to latitude/longitude coordinates, calculate the great-circle distance using the **Haversine formula**, and apply an **8% detour uplift factor** to satisfy ESG audit requirements.

---

## Problem 7: Trip Cancellations & Financial Adjustments in Locked Periods
### The Issue
Corporate trip bookings are highly volatile and frequently canceled or amended. If an analyst locks in and audits the carbon ledger for January, and a trip is subsequently canceled in March, editing January's locked data violates financial auditing standards.

### The Technical Fix
Instead of editing historical database rows, the ingestion engine uses a double-entry accounting approach. If a cancellation is received for an already locked/audited transaction ID, the parser writes a **compensating ledger entry** (a negative carbon quantity) in the *current, open month* to balance the books, maintaining perfect historical audit integrity.
