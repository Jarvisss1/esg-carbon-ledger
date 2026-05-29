# Architectural Decisions & Rationale

This document logs the critical design decisions made during the development of our ESG Normalization and Carbon Accounting platform. It details why we took specific technical paths, how we prioritized datasets, and maps out key questions for product strategy.

---

## 1. Utility Data Ingestion: Why Structured CSV Wins Over PDF OCR

* **The Ambiguity**: Facility utility consumption records are available in diverse formats: aggregate monthly PDF bills, direct CSV portal exports, or smart meter API endpoints.
* **The Decision**: We chose to enforce **structured CSV portal exports** (such as standard Green Button or smart meter interval formats) and deliberately deferred PDF invoice parsing for our initial versions.
* **The Rationale**:
  * **Fragility of PDF Parsers**: Reading PDF invoices requires optical character recognition (OCR) or positional parsing rules. PDF layouts from utility providers are highly volatile; a minor redesign, margin shift, or marketing banner will misalign coordinates and break extraction scripts.
  * **Low Margin of Error**: In financial-grade ESG auditing, error rates must be near zero. An OCR typo reading a decimal point incorrectly or confusing a dollar charge with kilowatt-hours can over- or under-report Scope 2 carbon footprints by a factor of 10 or 100, resulting in audit failures.
  * **Machine-Readable Cleanliness**: Formats like Green Button provide clean, comma-separated intervals with predictable headers, ensuring 100% data integrity and robust ingestion speeds.

---

## 2. SAP Integration Pathways: OData vs. Legacy XML IDocs

* **The Ambiguity**: SAP manages logistics and material logs in deep, relational database structures. We needed a clean way to ingest fuel and procurement tables.
* **The Decision**: We standardized on synchronous REST-based OData payloads (`API_MATERIAL_DOCUMENT_SRV`) for modern clouds, while building highly customizable fallback handlers for CSV/Excel report extracts (e.g. `MSEG/EKPO` layouts) for offline operational plants.
* **The Rationale**:
  * **OData Simplicity**: RESTful OData endpoints speak native JSON, integrating perfectly with a Django back-end. They natively support clean HTTP error codes, synchronous responses, and standard URI queries (like `$filter=PostingDate ge ...`).
  * **Bridging the Connectivity Gap**: Many regional factory floors or warehouses operate behind strict local firewalls with no direct network line to the core corporate SAP system. Providing a web upload page for standard SAP report spreadsheets bridges this gap seamlessly.
  * **Why XML IDocs Were Deferred**: Processing asynchronous XML IDocs (like the basic `MBGMCR03` segment) requires configuring complex SAP communications, message routes, and BAPI queues. To keep our RESTful services lightweight and highly responsive, we deferred direct XML listeners from the core synchronous pipeline.

---

## 3. Corporate Travel Ingestion: REST APIs & webhook Lifecycle

* **The Ambiguity**: Travel bookings are highly fluid and contain substantial transactional noise (taxes, airline fees, cancellation adjustments, per diems).
* **The Decision**: We integrate with Concur Itinerary (v4) and Navan TMC JSON payloads via scheduled polling and event webhooks, tracking bookings with a unique `trip_id` key.
* **The Rationale**:
  * **Handling Cancellations Gracefully**: Unlike static utility meters, travel itineraries are frequently updated or cancelled. If we treated travel records as static, one-time imports, we would end up over-reporting travel carbon. By tracking a persistent `trip_id`, we can perform dynamic upserts. If a cancellation is processed *after* an audit period is locked, the engine writes a compensating negative ledger entry in the current open month.
  * **Filtering out Financial Noise**: Booking fees, baggage claims, and travel taxes carry zero carbon weight. The parser isolates and discards these rows, focusing purely on active travel segments (flights, hotel stays, vehicle rentals).
  * **Guest Traveler Classification**: Non-employee travel is automatically flagged during ingestion. This allows analysts to manually route employee trips to Scope 3 Category 6 (Business Travel) and guest travel to Scope 3 Category 1 (Purchased Services), adhering to audit standards.

---

## 4. Goods Movement Type Mapping (SAP)

* **The Ambiguity**: SAP logs every physical material transfer as a distinct movement item. A naive total sum of these rows will cause severe double-counting.
* **The Decision**: We process standard goods receipts (`101`) for Scope 3 Purchased Goods, and goods issues to fixed assets (`241`) for Scope 1 Combustion. We explicitly map internal storage-to-storage transfer movements (`313 / 315`) to `EXCLUDED_LOGISTICS` with a quantity of `0` in our ledger.
* **The Rationale**: Storage transfers represent internal shuffling between facilities. For example, moving 500 liters of diesel from a central warehouse to a regional depot does not burn the fuel. The fuel is only burned when issued to an asset (movement `241`). Ignoring `313/315` prevents double-counting while preserving a clean audit trail.

---

## 5. In-Memory Background Ingestion Queue

* **The Ambiguity**: Parsing dense spreadsheets, calculating carbon factors, and running checks synchronously inside HTTP request threads triggers gateway timeouts and can trigger memory crashes under concurrent loads.
* **The Decision**: We implemented a lightweight, thread-safe, in-memory sequential queue (`ESGIngestQueueWorker` using standard Python `queue.Queue`). HTTP uploads return `202 Accepted` instantly to the user's browser, offloading parsing tasks to our background worker thread.
* **The Rationale**:
  * **Protecting Memory Footprints**: Distributed systems like Celery + Redis introduce notable container memory footprints. A thread-safe, in-memory queue worker runs in the same process space with near-zero overhead, staying well within Render's 512MB RAM free budget.
  * **Lock & Race Condition Immunity**: By limiting ingestion processing to a single sequential background worker, we completely eliminate concurrent database lock collisions and double-ingestion key conflicts.

---

## 6. Secure Multi-Tenant Boundaries & BOLA Protection

* **The Ambiguity**: While dynamic tenant lookup successfully isolated data at the query manager level, endpoints accepting raw query parameters (like `?tenant_id=...`) or resource IDs were vulnerable to Insecure Direct Object Reference (IDOR / BOLA) attacks where corporate users could query other tenants' carbon logs.
* **The Decision**: We implemented strict, active server-side overrides. Any user-supplied query-parameter filter for `tenant_id` is completely discarded for authenticated users. The backend view strictly forces the filter to match their session's dynamic tenant UUID.
* **The Rationale**:
  * Active server-side scoping guarantees that a KPMG auditor can **never** query, edit, or delete Tata Motors data.
  * Extensively decorated all ledger read, write, and export endpoints with standard REST framework `@permission_classes([IsAuthenticated])` filters to block anonymous traffic.

---

## 7. Registration Profiles & First/Last Name Alignment

* **The Ambiguity**: Although our React registration form collects the analyst's full name and splits it cleanly into `first_name` and `last_name` parameters, the backend was previously ignoring these fields, causing columns to remain empty (`EMPTY`) in the database.
* **The Decision**: Hardened the registration `/api/auth/register/` and me profile `/api/auth/me/` views to process, save, and return `first_name` and `last_name` fields.
* **The Rationale**: Guarantees complete alignment between frontend user profile views and the core Django User table. Makes the platform audit-ready for individual auditor profile tracking.

---

## 8. Strategic Questions for the Product Manager (PM)

In enterprise deployments, we would ask the product team to weigh in on these key workflow design decisions:

1. **Emission Factor Recalculation**: When a public carbon intensity database (like DEFRA) issues retroactive corrections for past years' grid factors, do we recalculate historical, locked accounting years, or do we apply the correction as an adjustment entry in the current open period?
2. **Boundary Allocation Rule**: When logging facility emissions, do we adopt operational control (reporting 100% of emissions for any facility we run) or financial control (prorating emissions by equity ownership, e.g., 60% of plant emissions)?
3. **Analyst Airport Registry Management**: If an unknown airport code is ingested (causing distance calculations to fail), should the UI expose a master coordinate management dashboard where analysts can manually register coordinates into the lookup table?
4. **Currency Conversions**: For transactions reported in mixed foreign currencies (EUR, USD, INR), do we lock the exchange rate at the transaction's posting date or apply a single, fixed annual conversion index defined by corporate treasury?