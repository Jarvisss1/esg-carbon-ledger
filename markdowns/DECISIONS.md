# Architectural Decisions & Rationale

This document details the critical design decisions made during the development of the ESG normalization prototype. It explains why specific technical paths were chosen, what subsets of data were prioritized, and outlines key questions for product management.

---

## 1. Utility Data Ingestion: Why Structured CSV over PDF OCR
* **The Ambiguity**: Facilities management teams can acquire electricity usage history as aggregate monthly PDF bills, direct CSV portal exports, or smart meter APIs.
* **The Decision**: The platform explicitly enforces **structured CSV portal exports** (such as PG&E Green Button CSVs or smart meter time-series CSVs) and deliberately excludes PDF bill ingestion for the initial MVP.
* **The Rationale**:
  * **Brittle PDF Extraction**: Reading PDF bills requires Optical Character Recognition (OCR) or visual segment scrapers. PDF layouts are highly volatile; a minor spacing update, font change, or seasonal marketing banner from the utility will shift the coordinate boundaries, breaking the extraction script.
  * **High Error Susceptibility**: For financial-grade ESG auditing, extraction errors are a catastrophic failure mode. A missed decimal place, an off-by-one OCR digit reading, or mixing up the standing billing fee with the active consumption will lead to a 10x or 100x error in Scope 2 carbon metrics, causing an audit failure.
  * **Machine-Readable Standardization**: Portals using Green Button or smart meter formats provide clean, comma-separated intervals with predictable headers. This approach ensures 100% data integrity, high parser execution speeds, and strict validation of time-series consumption.

---

## 2. SAP Integration Pathways: OData vs. Legacy IDocs
* **The Ambiguity**: SAP manages material movements in deep relational structures. We must determine how to ingest fuel and procurement data from complex configurations.
* **The Decision**: Standardized on synchronous OData payloads (`API_MATERIAL_DOCUMENT_SRV`) for modern clouds, while providing fallback parsing for flat-file CSV/Excel extracts (relying on `MSEG/EKPO` layouts) for offline operational plants.
* **The Rationale**:
  * **OData Modernity**: REST-based OData endpoints natively speak JSON, which integrates cleanly with a Django backend. It supports standard HTTP error codes, synchronous response payloads, and flexible URI filtering (e.g. `$filter=PostingDate ge ...`).
  * **Flat-file Fallback**: In the real world, individual manufacturing plants lack direct API connections to the corporate SAP core due to strict firewall rules. Providing an analyst-driven CSV/Excel upload page for SAP reports (handling traditional table dumps with `BUKRS`, `WERKS`, `KOSTL` headers) bridges this connectivity gap.
  * **Why XML IDocs Were Deferred**: Parsing inbound XML IDocs (`MBGMCR03` basic type) requires establishing BD64 distribution models, setting up port communications, and implementing BAPI processing queues. While we generated simulated XML IDoc files for validation, we excluded direct XML listener processes from the core synchronous MVP to focus on REST APIs.

---

## 3. Corporate Travel Ingestion: REST APIs & Webhook Lifecycle
* **The Ambiguity**: Corporate travel bookings are highly volatile and contain extensive transactional noise (tax fees, baggage claims, per diems).
* **The Decision**: Chose to integrate with Concur Itinerary v4 and Navan TMC JSON models via polling schedule and webhook events, tracking bookings by a unique `trip_id`.
* **The Rationale**:
  * **Lifecycle Mutability**: Unlike electricity smart meter feeds, travel bookings change. An employee may book a flight, modify the route, or cancel it entirely. If we treat travel records as static, immutable imports, we will over-report carbon. Our database uses a dynamic upsert matching on `trip_id` and `booking_status`. If a cancellation occurs *after* the billing cycle is audit-locked, the normalizer writes a compensating negative ledger entry.
  * **Noise Filtering**: Per diem rows, travel taxes, and service fees (which have zero carbon relevance) are explicitly ignored during parsing. We only extract the active travel segments (flights, hotel stays, ground transport).
  * **Traveler Boundaries**: We flag guest travelers (non-employees) in the ingestion queue. Employees fall under Scope 3 Category 6 (Business Travel), whereas guest travel is flagged for manual re-routing to Scope 3 Category 1 (Purchased Services) to satisfy auditor boundaries.

---

## 4. Goods Movement Type Mapping (SAP)
* **The Ambiguity**: SAP logs every internal physical movement of a material as a line item. Summing all movements leads to severe double-counting.
* **The Decision**: We handle standard goods receipts (`101`) for Scope 3 Purchased Goods, and goods issues to fixed assets (`241`) for Scope 1 Combustion. We explicitly map internal storage-to-storage transfer movements (`313 / 315`) to `EXCLUDED_LOGISTICS` with a quantity of `0` in the final carbon ledger.
* **The Rationale**: Storage transfers represent internal shuffling between facilities. For example, moving 500 liters of diesel from a central warehouse to a regional depot does not burn the fuel. The fuel is only burned when issued to an asset (movement `241`). Ignoring `313/315` prevents double-counting while preserving a clean audit trail.

---

## 5. In-Memory Sequential Ingestion Queue (`ESGIngestQueueWorker`)
* **The Ambiguity**: Heavy Excel, JSON, and XML files can take time to parse, check for anomalies, and calculate emissions. Processing them synchronously in HTTP threads triggers Gunicorn 30-second gateway timeouts and spikes RAM consumption.
* **The Decision**: Designed and implemented an **in-memory thread-safe sequential queue** daemon thread (`ESGIngestQueueWorker` using `queue.Queue`). Ingestion returns `202 Accepted` instantly to the browser, scheduling the parsing task to execute in the background.
* **The Rationale**:
  * **Memory Ceiling Protection**: Celery with Redis or RabbitMQ adds significant operational container memory footprints. A thread-safe, in-memory daemon worker runs inside the existing Python process with near-zero overhead, comfortably staying within Render's tight 512MB RAM free-tier budget.
  * **Race-Condition & DB Lock Avoidance**: Restricting queue processing to a single background worker sequentially eliminates concurrent row-locking disputes and unique deduplication key constraint collisions in the database.

---

## 6. Schema-Free Dynamic Metadata Storage (User Assignments)
* **The Ambiguity**: Analysts require the ability to assign records to specific team members and track custom parameters without breaking structural compatibility or running extensive database schema migrations.
* **The Decision**: Stored dynamic analyst assignments (`assigned_to`) and metadata changes natively within the existing database `raw_data` JSON column rather than executing a new SQL schema migration.
* **The Rationale**:
  * **Zero Downtime & Risk**: SQL table-altering migrations lock rows and tables in production, creating critical bottlenecks. Using a dynamic, schema-free JSON attribute permits infinite metadata growth with zero migration friction.
  * **Robust Database Integration**: SQLite and PostgreSQL natively support compiled JSON sub-attribute querying (`raw_data__assigned_to`), allowing the dashboard queue to isolate unassigned vs assigned records instantly.

---

## 7. Sub-Millisecond Read Performance via `LocMemCache`
* **The Ambiguity**: Ingested ESG ledger records are read-heavy but updated infrequently, yet rendering dynamic dashboards and timelines from deep tables creates recurring CPU database spikes.
* **The Decision**: Enabled and configured Django's native **local memory caching (`LocMemCache`)** across read-heavy details, modal views, and audit log histories, with automated full-cache invalidations (`cache.clear()`) triggered instantly on any database write.
* **The Rationale**:
  * **Zero Operational Cost**: Bypasses external Redis server dependencies and bills, achieving sub-millisecond response times natively within the server's footprint.
  * **100% Audit fresh consistency**: Invalidation on write guarantees that the carbon ledger and analyst audit trails are always perfectly up-to-date and consistent.

---

## 8. Strategic Questions for the Product Manager (PM)
In a real-world enterprise deployment, we would ask the PM to clarify the following business requirements:

1. **Emission Factor Recalculation**: If an international grid database (like DEFRA or IEA) updates its historical grid factors, do we retroactively recalculate and rewrite the carbon footprint of past, locked financial years, or do we apply the correction as an adjustment in the current reporting period?
2. **Boundary Allocation Rule**: When calculating facility emissions, do we apply operational control (100% of emissions of any facility we run) or financial control (emissions prorated by our equity ownership percentage, e.g., 60% of plant emissions)?
3. **Analyst Coordinates Override**: When an unknown airport code appears (causing the Haversine formula to fail), should the UI expose a master coordinate management screen where an ESG analyst can manually add and save new IATA coordinates to the lookup table?
4. **Currency Revaluation**: For mixed-currency files (EUR, USD, INR), do we lock in the exchange rate at the transaction's posting date or apply a single, fixed annual conversion index defined by corporate treasury?