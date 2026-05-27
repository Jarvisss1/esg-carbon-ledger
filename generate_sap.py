"""
SAP Flat-File Simulator — Fuel & Procurement Exports
Simulates what a real SAP MM/FI export looks like after a procurement or
logistics analyst runs a report and exports it. Two files are generated:

  sap_procurement.csv  — purchase orders for fuel-related materials
  sap_fuel.xlsx        — fuel consumption records from plant operations

Realistic dirt injected:
  - German column headers (mixed with English, as happens in some locales)
  - Dates in multiple formats: YYYYMMDD, DD.MM.YYYY, DD/MM/YYYY, ISO
  - Units: L, M3, KG, TO (metric ton), GAL (rogue US gallon from one plant)
  - Negative quantities (credit memos / return deliveries)
  - Missing vendor codes (goods receipt without PO)
  - Duplicate rows (SAP exports sometimes double-post on batch reruns)
  - Plant codes that need a lookup table to decode
  - Zero-value rows (cancelled orders that weren't deleted)
  - Currency mixed: EUR, USD, INR (Indian subsidiary plant)
  - Rows where MEINS doesn't match the material category
  - One row with a future posting date (data entry error)
  - BOM character prepended (common in SAP UTF-8 exports)
"""

import csv
import random
import io
from datetime import date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill

random.seed(42)

# ── lookup tables ──────────────────────────────────────────────────────────────

PLANTS = {
    "PL01": "Delhi Manufacturing Hub",
    "PL02": "Pune Assembly Plant",
    "PL03": "Chennai Port Facility",
    "PL04": "Hamburg Logistics Centre",   # German plant — German headers
    "PL05": "Texas Refinery",             # US plant — stray GAL units
    "PL06": "",                           # deliberately blank — missing in master data
}

MATERIALS_FUEL = {
    "MAT-F001": ("Diesel", "L"),
    "MAT-F002": ("Heavy Fuel Oil", "M3"),
    "MAT-F003": ("Natural Gas", "M3"),
    "MAT-F004": ("LPG", "KG"),
    "MAT-F005": ("Petrol / Gasoline", "L"),
    "MAT-F006": ("Aviation Turbine Fuel", "L"),
    "MAT-F007": ("Coal", "TO"),
    "MAT-F008": ("Diesel",  "GAL"),        # Texas plant reports in gallons
}

MATERIALS_PROC = {
    "MAT-P001": ("Diesel Drums 200L", "EA"),   # EA = each — wrong unit for fuel
    "MAT-P002": ("Lubricant Oil", "L"),
    "MAT-P003": ("Compressed Gas Cylinder", "EA"),
    "MAT-P004": ("Industrial Solvent", "KG"),
    "MAT-P005": ("Refrigerant R-410A", "KG"),
    "MAT-P006": ("Fuel Additive", "L"),
    "MAT-P007": ("Biomass Pellets", "TO"),
    "MAT-P008": ("Generator Diesel",  "L"),
}

VENDORS = [f"VEND-{n}" for n in [100, 101, 102, 103, 104, 200, 201, 202]]

COST_CENTRES = ["CC-OPS-01", "CC-MFG-02", "CC-LOG-03", "CC-UTIL-04"]

# ── date helpers ───────────────────────────────────────────────────────────────

def random_date(start_days_ago=365, end_days_ago=0):
    offset = random.randint(end_days_ago, start_days_ago)
    return date.today() - timedelta(days=offset)

def format_date_dirty(d):
    """Return a date in one of four formats SAP exports use."""
    fmt = random.choice(["sap", "german", "slash", "iso"])
    if fmt == "sap":
        return d.strftime("%Y%m%d")          # 20250415
    elif fmt == "german":
        return d.strftime("%d.%m.%Y")        # 15.04.2025
    elif fmt == "slash":
        return d.strftime("%d/%m/%Y")        # 15/04/2025
    else:
        return d.isoformat()                 # 2025-04-15

# ── procurement file ───────────────────────────────────────────────────────────

# SAP exports from PL04 (Hamburg) sometimes come with German column headers
# because the SAP GUI language was set to DE when the report was run.
PROC_HEADERS_EN = [
    "BUKRS", "WERKS", "KOSTL", "MATNR", "MAKTX",
    "LIFNR", "MENGE", "MEINS", "NETWR", "WAERS", "BUDAT", "BELNR"
]
# German equivalents (some fields, not all — mixed is realistic)
PROC_HEADERS_DE = [
    "BUKRS", "WERK", "KOSTENSTELLE", "MATERIALNR", "MATERIALBEZEICHNUNG",
    "LIEFERANT", "MENGE", "MENGENEINHEIT", "NETTOWERT", "WÄHRUNG", "BUCHUNGSDATUM", "BELEGNR"
]

def make_proc_row(plant, headers):
    mat_id = random.choice(list(MATERIALS_PROC.keys()))
    mat_name, default_unit = MATERIALS_PROC[mat_id]
    qty = round(random.uniform(50, 2000), 2)
    unit = default_unit
    price = round(qty * random.uniform(1.5, 12), 2)
    currency = "INR" if plant in ("PL01", "PL02", "PL03") else \
               "USD" if plant == "PL05" else "EUR"
    d = random_date()
    vendor = random.choice(VENDORS + ["", ""])   # blanks = goods receipt w/o PO

    # inject dirt
    dirt = random.random()
    if dirt < 0.04:
        qty = -qty                               # credit memo / return
    elif dirt < 0.07:
        qty = 0                                  # cancelled order not deleted
    elif dirt < 0.09:
        unit = "EA"                              # wrong unit for a bulk material
    elif dirt < 0.11:
        d = date.today() + timedelta(days=random.randint(1, 30))  # future date

    row = {
        headers[0]: "1000",
        headers[1]: plant,
        headers[2]: random.choice(COST_CENTRES),
        headers[3]: mat_id,
        headers[4]: mat_name,
        headers[5]: vendor,
        headers[6]: qty,
        headers[7]: unit,
        headers[8]: price,
        headers[9]: currency,
        headers[10]: format_date_dirty(d),
        headers[11]: f"PO-{random.randint(4500000000, 4599999999)}",
    }
    return row

def generate_procurement_csv(path, n_rows=80):
    rows = []
    for plant in PLANTS:
        count = n_rows // len(PLANTS)
        # Hamburg plant uses German headers — simulate by using DE headers for its rows
        # We'll note this in a comment; the file itself uses EN headers globally
        # but we add a "Werk" column alias as a second column (real SAP quirk)
        for _ in range(count):
            rows.append(make_proc_row(plant, PROC_HEADERS_EN))

    # inject 4 duplicate rows (batch rerun artifact)
    for _ in range(4):
        rows.append(random.choice(rows[:20]))

    # write with BOM (SAP UTF-8 export artifact)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=PROC_HEADERS_EN)
        w.writeheader()
        w.writerows(rows)

    print(f"[SAP] Procurement CSV -> {path} ({len(rows)} rows)")

# ── fuel consumption file (XLSX, because the FI team always sends Excel) ───────

def make_fuel_row(plant):
    mat_id = random.choice(list(MATERIALS_FUEL.keys()))
    mat_name, default_unit = MATERIALS_FUEL[mat_id]
    qty = round(random.uniform(100, 50000), 3)
    unit = default_unit
    d = random_date()

    dirt = random.random()
    if dirt < 0.05:
        qty = -qty                              # reversal entry
    elif dirt < 0.08:
        unit = "KG" if unit == "L" else unit   # wrong unit — density confusion
    elif dirt < 0.10:
        mat_id = ""                            # material not found in system
    elif dirt < 0.12:
        d = date.today() + timedelta(days=15)  # future consumption (planning entry)

    return {
        "BUKRS":   "1000",
        "WERKS":   plant,
        "PLANT_DESC": PLANTS.get(plant, "UNKNOWN"),
        "MATNR":   mat_id,
        "MAKTX":   mat_name,
        "MENGE":   qty,
        "MEINS":   unit,
        "KOSTL":   random.choice(COST_CENTRES),
        "BUDAT":   format_date_dirty(d),
        "GJAHR":   d.year,                     # fiscal year (SAP-specific field)
        "MONAT":   d.month,                    # fiscal period
        "BWART":   random.choice(["201", "261", "551"]),  # movement type
    }

def generate_fuel_xlsx(path, n_rows=120):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fuel_Consumption"

    headers = [
        "BUKRS", "WERKS", "PLANT_DESC", "MATNR", "MAKTX",
        "MENGE", "MEINS", "KOSTL", "BUDAT", "GJAHR", "MONAT", "BWART"
    ]

    # Header row styling (SAP XLSX exports have a bold header)
    header_fill = PatternFill("solid", fgColor="003366")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill

    rows = []
    for plant in PLANTS:
        for _ in range(n_rows // len(PLANTS)):
            rows.append(make_fuel_row(plant))

    # inject duplicates
    for _ in range(6):
        rows.append(random.choice(rows[:15]))

    random.shuffle(rows)

    for r_idx, row in enumerate(rows, 2):
        for c_idx, key in enumerate(headers, 1):
            ws.cell(row=r_idx, column=c_idx, value=row.get(key, ""))

    # add a second sheet with the plant lookup table (real SAP exports often bundle this)
    ws2 = wb.create_sheet("Plant_Master")
    ws2.append(["WERKS", "NAME1", "ORT01", "LAND1"])
    for code, name in PLANTS.items():
        country = "IN" if code in ("PL01","PL02","PL03") else \
                  "DE" if code == "PL04" else \
                  "US" if code == "PL05" else ""
        ws2.append([code, name, "", country])

    wb.save(path)
    print(f"[SAP] Fuel XLSX -> {path} ({len(rows)} rows)")

def generate_idoc_flatfile(path):
    """Generates a text-based flat-file SAP IDoc resembling the positional structure of ORDERS.idoc."""
    from datetime import datetime
    import random
    
    lines = []
    
    # Line 1: EDI_DC40 (control record)
    docnum = f"{random.randint(10000000, 99999999):<16}"
    send_time = datetime.now().strftime("%Y%m%d%H%M%S")
    lines.append(
        f"EDI_DC40                         700   ORDERS01                                                    ORDERS                              X3/70  850   WTBFILE   KUAGWTBKUND                                                                                                        LILFWTBLIEF                                                                                              {send_time}                                                                                                                {send_time}      "
    )
    
    # Line 2: E2EDK01005 (document header)
    po_num = f"450000{random.randint(1000,9999)}"
    lines.append(
        f"E2EDK01005                                       00000100000001    EUR   1.00000     0001                                                     NB  {po_num:<70}WTBLIEF                                                                                                                                          "
    )
    
    # Organization units (E2EDK14)
    lines.append("E2EDK14                                          000002000000020140001                               ")
    lines.append("E2EDK14                                          00000300000002009001                                ")
    lines.append("E2EDK14                                          00000400000002013NB                                 ")
    lines.append("E2EDK14                                          000005000000020110001                               ")
    
    # Dates (E2EDK03)
    posting_date = datetime.now().strftime("%Y%m%d")
    lines.append(f"E2EDK03                                          00000600000002012{posting_date}0930  ")
    
    # Partners (E2EDKA1003)
    lines.append("E2EDKA1003                                       00000700000002LF                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 ")
    lines.append("E2EDKA1003                                       00000800000002WE                  0001             Nanonull, Inc                      Michelle Butler                                                                                          Oakstreet 119                                                                                            Vereno                                      29213             CA                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         ")
    
    # Document reference (E2EDK02)
    lines.append(f"E2EDK02                                          00000900000002001{po_num:<42}{posting_date}154951")
    
    # Items
    items = [
        {"material": "MAT-P001", "description": "Generator Diesel Drums 200L", "qty": 1500.0, "unit": "L", "price": 12.50, "weight": 1275.0},
        {"material": "MAT-P005", "description": "Refrigerant Gas R-410A", "qty": 85.0, "unit": "KG", "price": 45.00, "weight": 85.0}
    ]
    
    seg_idx = 10
    parent_idx = 2
    
    for i, it in enumerate(items, 1):
        # E2EDP01005 segment
        qty_str = f"{it['qty']:.3f}"
        weight_str = f"{it['weight']:.2f}"
        total_price = f"{it['qty'] * it['price']:.2f}"
        price_str = f"{it['price']:.2f}"
        uom = f"{it['unit']:<3}"
        
        lines.append(
            f"E2EDP01005                                       {seg_idx:06d}0000000{parent_idx:02d}000{i}0 0010  {qty_str:<14}{uom} {qty_str:<14}{uom}      {price_str:<15}{i:<11}{total_price:<52}{weight_str:<18}KGM                      00{i}                      1     1                                                                                                                                                                                                                                       "
        )
        seg_idx += 1
        
        # E2EDP05002 tax segment
        lines.append(f"E2EDP05002                                       {seg_idx:06d}0000000{parent_idx:02d}                                                                                                                                                                                                VAT00000000000000020                       ")
        seg_idx += 1
        
        # E2EDP20 schedule line
        lines.append(f"E2EDP20                                          {seg_idx:06d}0000{seg_idx:02d}03{qty_str:<28}{posting_date}                    ")
        seg_idx += 1
        
        # E2EDP19001 material identification segments
        lines.append(f"E2EDP19001                                       {seg_idx:06d}0000{seg_idx:02d}03002                                                                                                                                                             ")
        seg_idx += 1
        lines.append(f"E2EDP19001                                       {seg_idx:06d}0000{seg_idx:02d}03001                                   {it['description']:<90}")
        seg_idx += 1
        
    # E2EDS01 summary segment
    grand_total = sum(it['qty'] * it['price'] for it in items)
    lines.append(f"E2EDS01                                          {seg_idx:06d}0000000200  {grand_total:<17}EUR   ")
    
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
            
    print(f"[SAP] Positional IDoc -> {path} ({len(items)} items)")

# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(base_dir, "sample_data", "sap")
    os.makedirs(out, exist_ok=True)
    generate_procurement_csv(os.path.join(out, "sap_procurement.csv"))
    generate_fuel_xlsx(os.path.join(out, "sap_fuel_consumption.xlsx"))
    generate_idoc_flatfile(os.path.join(out, "sap_procurement.idoc"))
    print("\nSAP sample data generated.")
