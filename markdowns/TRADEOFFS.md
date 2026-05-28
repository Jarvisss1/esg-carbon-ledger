# Engineering Trade-offs & Scope Omissions

To construct a high-integrity, production-ready ESG normalization MVP within the timeline, we made three deliberate architectural compromises. These trade-offs prioritize data accuracy, audit reproducibility, and system reliability over superficial automation.

---

## 1. Omission: Unstructured PDF Bill Parsing & OCR Scrapers
* **What We Omitted**: An automated Optical Character Recognition (OCR) pipeline to scrape scanned PDF utility invoices.
* **Why We Omitted It**: 
  * **Brittle & Volatile**: PDF scrapers require coordinate-based templates or deep-learning layout models. Utility providers modify document layouts frequently, immediately breaking static coordinates and requiring continuous developer maintenance.
  * **Audit-Failing Error Margins**: A minor character misreading by an OCR engine (such as converting a period into a comma, or misreading `108.3` kWh as `1083` or `10B.3`) can skew carbon reports by orders of magnitude.
  * **The Trade-off**: We traded visual scraping automation for **data integrity** by enforcing structured, machine-readable CSV portal exports (e.g., Green Button, smart meters) which provide robust format standards and zero-error parsing.

---

## 2. Omission: Live External Aviation & IATA Distance API Integration
* **What We Omitted**: Dynamic, real-time API integrations with third-party aviation tracking databases (such as FlightAware or OpenSky) to fetch flight distances.
* **Why We Omitted It**:
  * **Network Dependency**: Live API calls introduce external latency, dependency risks, and financial subscription costs. If the aviation API goes offline, our core travel ingestion pipeline stalls.
  * **Audit Reproducibility**: Different aviation APIs use different routing assumptions, which could result in inconsistent distance calculations over time for the same city pairs.
  * **The Trade-off**: We embedded a **static local database lookup** mapping thousands of global IATA airport codes to exact coordinates and computed distances using the mathematical Haversine formula (adding a standard 8% GHG routing uplift). This ensures the calculation executes in milliseconds, operates 100% offline, and remains perfectly reproducible during external audits.

---

## 3. Omission: Real-time Live Forex Currency Exchange Microservice
* **What We Omitted**: Integration with live foreign-exchange API feeds (e.g., ExchangeRatesAPI) to dynamically convert transaction costs into corporate baseline currencies.
* **Why We Omitted It**:
  * **Calculation Volatility**: Foreign exchange rates fluctuate multiple times per hour. If a transaction is re-parsed or a script is rerun, a live API might return a slightly different conversion rate, making the carbon-to-cost audit trail unreproducible.
  * **Audit Inconsistency**: Auditors require that financial exchange indices match the static figures utilized in the company's annual financial ledger.
  * **The Trade-off**: We hardcoded **static corporate exchange rate indices** within the tenant master data. This ensures that a transaction processed in January will yield the exact same currency conversion when audited in December, eliminating calculation drift.

---

## 4. In-Memory Queue Volatility vs. Zero Dependency Footprint
* **The Trade-off**: Using a light, thread-safe background queue running as a daemon inside the Django web process instead of establishing a standard Celery + Redis worker cluster.
* **Why We Chose It**:
  * **Render Free Tier Limits**: Celery and Redis consume substantial RAM. Restricting background processing to an in-memory queue thread allowed us to fit under Render's tight 512MB limits, avoiding high infrastructure costs.
  * **Sequential Database Consistency**: SQLite and Postgres do not suffer duplicate key insertion or row-locking conflicts because our single-threaded background worker processes one upload file strictly at a time.
  * **The Scope Omission**: In-memory queues are volatile. If the container restarts or goes to sleep, any pending queued items are lost. We accepted this risk because the raw uploaded file payloads are already saved in the database, allowing analysts to simply click "Reprocess" from the UI if a transient failure occurs.

---

## 5. Schema-Free Dynamic JSON Storage vs. SQL Schema Alterations
* **The Trade-off**: Storing dynamic properties (like `assigned_to` and cancellation trail logs) directly inside the JSON-typed `raw_data` column instead of creating new relational tables or run migrations.
* **Why We Chose It**:
  * **Zero Production Downtime**: Running database schema alterations (`ALTER TABLE`) locks rows and creates massive bottlenecks in highly transactional systems. Storing dynamic attributes schema-free inside JSON permits infinite model updates with zero migration friction.
  * **Database Portability Constraints**: Querying nested JSON keys depends on the specific SQL parser in the database engine. Since PostgreSQL and SQLite natively support JSON query syntax (`raw_data__assigned_to`), we traded strict SQL column typing for speed and migration safety.

---

## 6. Local Memory Caching Speed vs. Multi-Node Cache Sync
* **The Trade-off**: Standardizing on in-process local memory caching (`LocMemCache`) for read-heavy API actions (such as records detail and activity audit trails) rather than a centralized Redis caching microservice.
* **Why We Chose It**:
  * **Sub-Millisecond Rendering**: Fetching cache entries from local process memory requires zero network roundtrips, completing loads in less than 1ms.
  * **The Scope Omission**: If this system is scaled horizontally across multiple servers (multi-node setup), the local caches will fall out of sync because one container's cache invalidation won't affect the other. For our single-container MVP deployment, this is not a concern, and we traded multi-node sync support for 0 infrastructure overhead and sub-millisecond retrieval speeds.

---

## 7. Sniffing Auto-Detection Format Overhead vs. Strict Upload constraints
* **The Trade-off**: Sniffing the first few bytes of uploaded files to automatically override the ingestion target systems vs. raising strict parsing errors on dropdown mismatches.
* **Why We Chose It**:
  * **Dynamic Self-Healing**: Upload dropdown selections are highly prone to human error. Sniffing the text structure (`{`, `[`, `<`) to automatically route to `NAVAN_JSON` or `SAP_IDOC` guarantees that corrupt line-by-line parsing errors are avoided.
  * **Calculation Overhead**: Sniffing requires loading the first few characters of the payload in memory. Since string-prefix matching in Python is exceptionally fast (less than 0.1ms), we traded this negligible computation overhead for robust, crash-free uploads.

---

## 8. Omission: Live Production SMTP Mail Relay (Gmail/SendGrid)
* **What We Omitted**: Standard SMTP configuration mapping to a live external email provider (such as Gmail, AWS SES, or SendGrid API) for sending carbon report exports.
* **Why We Omitted It**:
  * **Volatile Network Dependency & External Latency**: Relying on external mail relays in a prototype introduces network latency and the risk of network request timeouts during synchronous file exports.
  * **Credential Management Overhead**: Production-level Gmail SMTP requires configuring app-specific passwords or OAuth credentials. These settings are fragile, prone to expiring, and represent a security risk if not managed in a dedicated secrets manager.
  * **Operational Maintenance Costs**: A live mail service requires maintaining a domain, configuring SPF/DKIM/DMARC records to prevent spam filtering, and tracking monthly delivery usage quotas.
  * **The Trade-off**: We traded live email dispatch for **reliable local mock logging** via Django's file-based email backend. The system writes all generated emails and attachments (CSV/XLSX ledgers) straight to the `sent_emails/` folder. This provides full audit verification of content and file attachments in a development environment, while allowing developers to switch to a production-ready SMTP setup by changing a single line in `settings.py`.