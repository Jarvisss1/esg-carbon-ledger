# ESG Ingestion Sources & Real-World Formats

This document describes the three main telemetry sources handled by the ESG normalization engine, including the core carbon accounting concepts, real-world data structures, and failure modes expected in production.

---

## 1. Core Concepts: What are Scope 1, 2, and 3 Emissions?
Before writing code to ingest carbon data, a software engineer must understand the basic accounting boundaries. Here is the breakdown in simple terms:

* **Scope 1: Direct Emissions ("Stuff we burn ourselves")**
  * **What it is**: Carbon dioxide and other greenhouse gases released directly into the air by machines or assets that our company owns or controls.
  * **Example**: Burning diesel fuel in an office generator to keep the servers running during a power cut, or burning petrol in a company-owned delivery truck.
  * **Data Source**: SAP Inventory issues (goods movement type `241`).

* **Scope 2: Purchased Energy ("Energy we buy, where someone else burned stuff to make it")**
  * **What it is**: Carbon emissions from electricity, steam, heating, or cooling that our company purchases from utility grids to run our facilities. The physical emissions occur at the utility's power plant (where they burn coal or gas), but because we bought and used that energy, we must account for it.
  * **Example**: Leaving the lights and AC running in the office.
  * **Data Source**: Smart meter or billing CSV portal exports from electrical utilities.

* **Scope 3: Indirect Supply Chain ("Everything else related to our business")**
  * **What it is**: Emissions from activities in our broader value chain that our company does not directly own or control, both upstream (suppliers) and downstream (customers).
  * **Example**: Employees flying on commercial airlines for client meetings (Scope 3 Category 6: Business Travel), booking hotel rooms, or buying raw materials like plastic and steel from suppliers (Scope 3 Category 1: Purchased Goods).
  * **Data Source**: Corporate travel platform APIs like Concur or Navan.

---

## 2. SAP ERP (Scope 1 Direct Fuel & Scope 3 Procurement)

### Real-World Formats Researched
* **OData Services**: SAP S/4HANA exposes standard synchronous REST-based OData endpoints such as `API_MATERIAL_DOCUMENT_SRV`. This service exposes a root entity `A_MaterialDocumentHeader` which nests item-level line records under `A_MaterialDocumentItem` in deep JSON trees.
* **Legacy XML IDocs**: Older SAP R/3 and ECC systems exchange documents asynchronously using IDocs (Intermediate Documents). Material movements typically rely on the `MBGMCR03` basic type (representing message type `MBGMCR`). These are XML payloads processed via inbound function modules like `BAPI_IDOC_INPUT1`.
* **Flat-File Dumps**: Operational plants frequently export CSV or Excel reports directly from SAP database tables such as `EKPO` (Purchase Order Items), `MKPF` (Material Document Headers), and `MSEG` (Material Document Segments).

### Takeaways & Key Anomalies
* **German Nomenclature**: SAP was built in Germany, and many database field names retain their original German abbreviations:
  * `BUKRS` (*Buchungskreis*) = Company Code
  * `WERKS` (*Werk*) = Plant Code (an opaque ID like `PL01` needing lookup)
  * `KOSTL` (*Kostenstelle*) = Cost Centre
  * `MATNR` (*Materialnummer*) = Material ID
  * `MENGE` (*Menge*) = Quantity
  * `MEINS` (*Basiseinheit*) = Base Unit of Measure (e.g., L, KG, TO)
  * `BUDAT` (*Buchungsdatum*) = Posting Date
  * `BWART` (*Bewegungsart*) = Goods Movement Type
* **Movement Types (Context is King)**: 
  * `101`: Goods Receipt for Purchase Order. Means raw material arrived. Used to compute **Scope 3 Category 1** (Purchased Goods).
  * `241`: Goods Issue to a Fixed Asset. Means fuel was actually pumped and burned in a company-controlled generator. Represents **Scope 1 Direct Combustion**.
  * `313 / 315`: Two-step internal transfers between warehouse locations. Logistical shuffling that does *not* burn fuel; **must be excluded** to prevent double-counting.
* **Data Typings**: Numbers are often sent as strings with trailing zeroes (e.g. `"140.000"`), dates appear in varying formats (e.g., `YYYYMMDD`, `DD.MM.YYYY`, or Microsoft Epoch `/Date(1498946400000)/`), and files may start with a Byte Order Mark (BOM) UTF-8 character that breaks standard CSV parsers.

---

## 3. Utility Portals (Scope 2 Electricity)

### Real-World Formats Researched
* **Green Button Standard**: Standardized XML and CSV formats used across North America (e.g., PG&E) to export smart meter interval history.
* **Smart Meter CSVs**: Time-series logs from smart meters (e.g., UK's Octopus Energy) that register electricity consumption at 15-minute, 30-minute, or daily intervals.
* **Macro-level Provider Reports**: Monthly aggregate billing spreadsheets including standing charges, VAT, demand peaks, and multi-tier energy pricing.

### Takeaways & Key Anomalies
* **Temporal Misalignment**: Utility bills represent billing periods that rarely align with calendar months (e.g., March 12 to April 10). To report monthly carbon, the system must prorate these numbers across months rather than assigning them to the billing end-date.
* **Timezone & Daylight Savings (DST) Shifts**: UK smart meter data alternates between Coordinated Universal Time (denoted by `Z`) and British Summer Time (`BST +01:00`). When clocks fall back, the data files duplicate the 01:00–02:00 timestamp range; when they spring forward, an entire hour is absent. Standard parsers crash or drop these intervals.
* **Split Tariff Rates**: Smart meters split active imports by tariff bands (e.g., `Import T1 kWh` off-peak and `Import T2 kWh` peak) rather than giving a single sum. 
* **Solar Net-Metering (NEM)**: Facilities with solar arrays export power back to the grid. Exports are logged as negative numbers (e.g., `-342.5` kWh). A naive parser would blindly sum these numbers, offsetting gross Scope 2 emissions, which violates the greenhouse gas protocol's dual-accounting rules (Market-based vs. Location-based methods).
* **Demand Charge Metrics (kVA)**: Utility bills mix consumption energy (`kWh`) with demand charges (`kVA` - apparent power limit). `kVA` values represent circuit limits, not energy consumed, and must never be summed with `kWh` for emissions.

---

## 4. Corporate Travel (Scope 3 Category 6 Business Travel)

### Real-World Formats Researched
* **Concur Itinerary v4 API**: REST API returning deeply nested JSON arrays that document multi-segment travel itineraries. Flight legs are nested inside `Bookings -> Segments -> AirlineTickets`.
* **Navan TMC API**: Modern travel management API delivering real-time lifecycle tracking for corporate travel bookings. Contains booking statuses, `passengerInfo`, and payment breakdowns.

### Takeaways & Key Anomalies
* **The Spatial Data Deficiency**: Travel booking platforms do not calculate great-circle distances. The JSON payloads only provide the Origin and Destination as 3-letter IATA airport codes (e.g., `SFO` to `LHR`). The normalizer must look up these codes, fetch their latitude/longitude coordinates, and run the Haversine formula to compute distance in kilometers.
* **Pre-populated Airport Registry**: To avoid dynamic network lookups or empty calculations, the database is pre-populated with **46 major aviation hubs** (including DEL, BOM, BLR, LHR, CDG, DXB, SIN, JFK, SFO, LAX, ORD, etc.) through a dedicated data migration (`0004_populate_airports.py`).
* **Daylight & Routing Uplifts**: Real flight paths are not perfect lines. The greenhouse gas protocol dictates adding a standard **8% distance uplift factor** to all calculated flight distances to account for holding patterns and air traffic detours.
* **Cabin Class Weighting**: Standard emissions databases apply different multipliers to flights depending on the cabin class (e.g., Business class has a much higher carbon footprint per passenger-kilometer than Economy because business seats occupy more physical space on the aircraft).
* **Employee vs. Guest Boundary**: Segments with guest indicators (missing employee IDs or marked as guest) are flagged during ingestion and placed in the analyst review queue for manual classification.

---

## 5. Security & Authentication Architecture

To ensure enterprise-grade accountability, the platform moved beyond simple mock headers to a production-hardened design:

### Robust Token Authentication Endpoints
* **`POST /api/auth/register/`**: Allows secure registration of analysts or auditors, hashing passwords dynamically and issuing secure tokens.
* **`POST /api/auth/token/`**: Standard credentials-to-token trade login view using Django REST Framework's `ObtainAuthToken`.
* **`GET /api/auth/me/`**: Profile query view requiring a secure token header to retrieve user metadata.

### Production Hardening on Dynamic Headers
* Our custom authentication backend (`RobustDRFAuthentication`) safely handles backwards-compatible, dynamic header mapping (`X-User`) in local development (`DEBUG = True`) and automated test execution.
* In production deployments (`DEBUG = False` and not in test execution), dynamic dynamic headers are **strictly disabled** by default.
* To allow pipeline automation, dynamic header auth can be securely enabled in production by configuring a strong bypass secret key (`INTERNAL_BYPASS_SECRET` in settings) and passing it inside the secure `X-Internal-Bypass-Secret` request header. All unauthorized header requests are rejected with `HTTP 403 Forbidden`.