# ESG Ingestion Sources & Real-World Formats

This document describes the three main telemetry sources handled by our ESG normalization engine. It covers the core carbon accounting concepts, real-world data structures, and the common anomalies we handle in production.

---

## 1. Core Concepts: Scope 1, 2, and 3 Emissions

Before writing code to ingest carbon data, it helps to understand the basic accounting boundaries. Here is a simple, practical breakdown of how we classify emissions:

* **Scope 1: Direct Emissions ("Stuff we burn ourselves")**
  * *What it is*: Greenhouse gases released directly into the air by assets that our company owns or controls.
  * *Example*: Burning diesel in an office generator to keep servers online during an outage, or fuel consumed by company delivery trucks.
  * *Data Source*: SAP Inventory issues (goods movement type `241`).
* **Scope 2: Purchased Energy ("Energy we buy, where someone else burned stuff to make it")**
  * *What it is*: Carbon emissions from electricity, steam, or cooling that our company purchases from utility grids. The physical emissions occur at the utility's power plant, but because we bought and used that energy, we must account for it.
  * *Example*: Leaving the lights and air conditioning running in our offices.
  * *Data Source*: Smart meter or billing CSV portal exports from electrical utilities.
* **Scope 3: Indirect Supply Chain ("Everything else related to our business")**
  * *What it is*: Emissions from activities in our broader value chain that our company does not directly own or control, both upstream (suppliers) and downstream (customers).
  * *Example*: Employees flying on commercial airlines for client meetings (Scope 3 Category 6: Business Travel), booking hotel rooms, or buying raw materials like plastic and steel from suppliers (Scope 3 Category 1: Purchased Goods).
  * *Data Source*: Corporate travel platform APIs like Concur or Navan.

---

## 2. Dynamic Domain-Based Workspace Resolution

To satisfy the modern multi-tenant enterprise environment, our architecture handles user registrations and organization assignments dynamically:

* **Corporate Email Domains (e.g., `karan@kpmg.com`)**:
  * The system dynamically parses their email domain, extracts the corporate slug (`'kpmg'`), and provisions a fully isolated, secure `KPMG` tenant sandbox in real-time.
  * Their data remains 100% segregated, and BOLA/IDOR protection overrides prevent them from ever accessing other tenants' data.
* **Public/Development Email Domains (e.g., `yshivhare413@gmail.com` or `yath3.14@gmail.com`)**:
  * Recognized public domains (including `gmail`, `yahoo`, `hotmail`, `outlook`, `icloud`, `aol`, `proton`, `protonmail`, `zoho`, `gmx`, `yandex`) are automatically mapped to the default seeded **`Tata Motors`** (`tata-motors` slug) workspace.
  * This guarantees standard testing and development logins get instant, backward-compatible access to the seeded baseline telemetry, dashboard charts, and ledgers without requiring manual database mapping.

---

## 3. SAP ERP (Scope 1 Direct Fuel & Scope 3 Procurement)

### Formats We Handle
* **OData Services**: SAP S/4HANA exposes standard synchronous REST-based OData endpoints such as `API_MATERIAL_DOCUMENT_SRV`. This service exposes a root entity `A_MaterialDocumentHeader` which nests item-level line records under `A_MaterialDocumentItem` in deep JSON trees.
* **Legacy XML IDocs**: Older SAP R/3 and ECC systems exchange documents asynchronously using IDocs (Intermediate Documents). Material movements typically rely on the `MBGMCR03` message type, which are XML payloads processed via inbound function modules like `BAPI_IDOC_INPUT1`.
* **Flat-File Dumps**: Operational plants frequently export CSV or Excel reports directly from SAP database tables such as `EKPO` (Purchase Order Items), `MKPF` (Material Document Headers), and `MSEG` (Material Document Segments).

### Core SAP Anomalies
* **German Nomenclature**: SAP database field names retain their original German abbreviations:
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
* **Data Typings**: Numbers are often sent as strings with trailing zeroes (e.g., `"140.000"`), dates appear in varying formats (e.g., `YYYYMMDD`, `DD.MM.YYYY`, or Microsoft Epoch `/Date(1498946400000)/`), and files may start with a Byte Order Mark (BOM) UTF-8 character that breaks standard CSV parsers.

---

## 4. Utility Portals (Scope 2 Electricity)

### Formats We Handle
* **Green Button Standard**: Standardized XML and CSV formats used across North America to export smart meter interval history.
* **Smart Meter CSVs**: Time-series logs from smart meters (e.g., UK's Octopus Energy) that register electricity consumption at 15-minute, 30-minute, or daily intervals.
* **Macro-level Provider Reports**: Monthly aggregate billing spreadsheets including standing charges, VAT, demand peaks, and multi-tier energy pricing.

### Core Utility Anomalies
* **Temporal Misalignment**: Utility bills represent billing periods that rarely align with calendar months (e.g., March 12 to April 10). To report monthly carbon, the system must prorate these numbers across months rather than assigning them to the billing end-date.
* **Timezone & Daylight Savings (DST) Shifts**: UK smart meter data alternates between Coordinated Universal Time (denoted by `Z`) and British Summer Time (`BST +01:00`). When clocks fall back, the data files duplicate the 01:00–02:00 timestamp range; when they spring forward, an entire hour is absent. Standard parsers crash or drop these intervals.
* **Split Tariff Rates**: Smart meters split active imports by tariff bands (e.g., `Import T1 kWh` off-peak and `Import T2 kWh` peak) rather than giving a single sum. 
* **Solar Net-Metering (NEM)**: Facilities with solar arrays export power back to the grid. Exports are logged as negative numbers (e.g., `-342.5` kWh). A naive parser would blindly sum these numbers, offsetting gross Scope 2 emissions, which violates the greenhouse gas protocol's dual-accounting rules (Market-based vs. Location-based methods).
* **Demand Charge Metrics (kVA)**: Utility bills mix consumption energy (`kWh`) with demand charges (`kVA` - apparent power limit). `kVA` values represent circuit limits, not energy consumed, and must never be summed with `kWh` for emissions.

---

## 5. Corporate Travel (Scope 3 Category 6 Business Travel)

### Formats We Handle
* **Concur Itinerary v4 API**: REST API returning deeply nested JSON arrays that document multi-segment travel itineraries. Flight legs are nested inside `Bookings -> Segments -> AirlineTickets`.
* **Navan TMC API**: Modern travel management API delivering real-time lifecycle tracking for corporate travel bookings. Contains booking statuses, `passengerInfo`, and payment breakdowns.

### Core Travel Anomalies
* **The Spatial Data Deficiency**: Travel booking platforms do not calculate great-circle distances. The JSON payloads only provide the Origin and Destination as 3-letter IATA airport codes (e.g., `SFO` to `LHR`). The normalizer must look up these codes, fetch their latitude/longitude coordinates, and run the Haversine formula to compute distance in kilometers.
* **Pre-populated Airport Registry**: To avoid dynamic network lookups or empty calculations, the database is pre-populated with **46 major aviation hubs** (including DEL, BOM, BLR, LHR, CDG, DXB, SIN, JFK, SFO, LAX, ORD, etc.) through a dedicated data migration (`0004_populate_airports.py`).
* **Daylight & Routing Uplifts**: Real flight paths are not perfect lines. The greenhouse gas protocol dictates adding a standard **8% distance uplift factor** to all calculated flight distances to account for holding patterns and air traffic detours.
* **Cabin Class Weighting**: Standard emissions databases apply different multipliers to flights depending on the cabin class (e.g., Business class has a much higher carbon footprint per passenger-kilometer than Economy because business seats occupy more physical space on the aircraft).
* **Employee vs. Guest Boundary**: Segments with guest indicators (missing employee IDs or marked as guest) are flagged during ingestion and placed in the analyst review queue for manual classification.

---

## 6. Reference Sources & Compliance Standards

To establish complete compliance and audit defense, the platform's parsing models and emission metrics map directly to recognized international standards and public repositories:

### A. SAP & Direct Combustion Standards
* **SAP Fields Reference**: Field schemas, material definitions, and transaction parameters align with [SAP Help Portal MM Purchase Order Reference](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE) (search keyword: `"MM purchase order fields"`).
* **Fuel Emission Factors**: Derived from the [DEFRA 2023 Greenhouse Gas Reporting Conversion Factors](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023) (specifically under the "Fuels" sheet).
* **Nomenclature Reference**: Real-world field matching is derived from SAP IDoc flat file layouts (such as `MSEG` segments and `EDI_DC40` control blocks).

### B. Utility Grid Intensity Standards
* **Green Button Alliance Spec**: Interval and smart meter schemas are structured to comply with the standard XML/CSV definitions available at [Green Button Alliance Schema Definitions](https://www.greenbuttonalliance.org).
* **Purchased Electricity Factors**: Grid intensities and carbon proration models utilize the localized grid electricity conversion factors from [DEFRA 2023 Conversion Factors](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023) (under the "Purchased electricity" tab).
* **Billing Reference**: Custom timezone offsets and billing structures match standard UK/EU and US time-series billing CSV headers (such as PG&E Green Button formats).

### C. Travel Aviation & Hotel Standards
* **Aviation Calculations**: Great-circle routing and cabin-class multipliers (First, Business, Economy) follow the [International Civil Aviation Organization (ICAO) Carbon Emissions Calculator Methodology](https://www.icao.int/environmental-protection/CarbonOffset).
* **Air Travel Factors**: Passenger-kilometer emissions are mapped directly to [DEFRA 2023 Air Travel Conversion Factors](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023) (under the "Business travel - air" sheet).
* **Airport IATA Codes Registry**: Geographic coordinates and 3-letter IATA codes are pre-seeded using the public flight hub directory available at [OurAirports Database](https://ourairports.com/data/airports.csv).
* **Hotel Stays Factors**: Room-night emission factors are fetched from the standard DEFRA global hotel factors (under the "Hotels" sheet).