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