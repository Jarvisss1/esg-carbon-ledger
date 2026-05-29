# Database Architecture & Data Model

Welcome to the data engine of our ESG Carbon Ledger. This document walks you through how we designed our database schemas, our dual-layer provenance model, and the ways we enforce security and audit readiness directly in the database layer.

---

## 1. Our Dual-Layer Provenance Blueprint

To stand up to rigorous third-party ESG audits (such as KPMG or PwC frameworks), we can't just parse data and throw away the source. We must prove exactly where every single kilogram of CO2e came from. To achieve this, the platform implements a **dual-layer database design** that cleanly separates our raw, immutable evidence from our parsed, queryable ledger rows.

```
       +---------------------------------------------+
       |             Raw Payload Layer               |
       |  (Stores exact CSV, XLSX, JSON, XML text)   |
       |  - Immutable, SHA-256 hashed, tenant-scoped  |
       +----------------------+----------------------+
                              |
                              | parsed & registered
                              v
       +---------------------------------------------+
       |            Ingestion Batch Layer            |
       |  (Tracks file stats, row counts, uploaded)  |
       +----------------------+----------------------+
                              |
                              | normalized & mapped
                              v
       +---------------------------------------------+
       |          Normalized Activity Layer          |
       |  (Standardized Scope 1, 2, 3 database rows) |
       |  - Coerced units (L, kWh, passenger-km)      |
       |  - Workflow Status: PENDING -> APPROVED/LOCKED|
       +---------------------------------------------+
```

1. **Raw Payload Layer**:
   * **The Rule**: Absolute immutability. We store the exact original file uploads and API JSON blocks exactly as we received them.
   * **The Purpose**: This is our ultimate source of truth. If there's ever a bug in our calculation formulas or normalization scripts, we can patch the code and re-process the raw payloads. The historical records are never lost or corrupted.
   * **The Security**: We compute a SHA-256 hash of the payload on ingestion to guarantee that the database record has not been tampered with.

2. **Ingestion Batch Layer**:
   * **The Rule**: Tracks the lifecycle of every uploaded telemetry file.
   * **The Purpose**: Gives us great operational visibility (tracking success status, total rows parsed, and error counts). It also allows us to run clean, complete rollbacks/reversals if a batch is found to contain corrupt source data.

3. **Normalized Activity Layer**:
   * **The Rule**: Every entry here is mapped to a standardized relational schema, calculating `normalized_value` in `kgCO2e` strictly based on DEFRA 2023.
   * **The Purpose**: Provides our main ledger entries that analysts search, filter, flag, audit, and aggregate for reports.

---

## 2. Core Django Database Models

### Tenant
Ensures absolute data isolation between different corporate clients.
```python
class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, unique=True, default="tata-motors")
    created_at = models.DateTimeField(auto_now_add=True)
```

### Raw Payload
Stores the original, untampered files and incoming API blobs.
```python
class RawPayload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='raw_payloads')
    source_system = models.CharField(max_length=50)
    filename = models.CharField(max_length=255, null=True, blank=True)
    payload_content = models.TextField()  # Original raw upload text or JSON representation
    payload_hash = models.CharField(max_length=64)  # SHA-256 checksum to prevent tampering
    ingested_at = models.DateTimeField(auto_now_add=True)
    ingested_by = models.CharField(max_length=150)
```

### Ingestion Batch
Keeps track of stats and logs for each file we ingest.
```python
class IngestionBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_batches')
    source_type = models.CharField(max_length=50, help_text="SAP / UTILITY / TRAVEL")
    uploaded_by = models.CharField(max_length=150)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_name = models.CharField(max_length=255)
    row_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    status = models.CharField(max_length=50, default="SUCCESS")
    raw_file = models.FileField(upload_to='raw_batches/', null=True, blank=True)
    raw_payload = models.OneToOneField(RawPayload, on_delete=models.SET_NULL, null=True, blank=True)
```

### Airport
A fast lookup table housing geographic coordinates for airport routing and distance calculations.
```python
class Airport(models.Model):
    iata_code = models.CharField(max_length=3, primary_key=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    city = models.CharField(max_length=255)
    country = models.CharField(max_length=2)
```

### Emission Record (NormalizedActivity)
This is where our final standardized ledger entries live, housing calculated carbon impact.
```python
class EmissionRecord(models.Model):
    class WorkflowStatus(models.TextChoices):
        PENDING_REVIEW = 'PENDING_REVIEW', 'Pending Analyst Review'
        APPROVED = 'APPROVED', 'Approved by Analyst'
        REJECTED = 'REJECTED', 'Rejected / Excluded'
        LOCKED_FOR_AUDIT = 'LOCKED_FOR_AUDIT', 'Locked for Final Audit'

    class ScopeCategory(models.TextChoices):
        SCOPE_1_STATIONARY = 'SCOPE_1_STATIONARY', 'Scope 1: Stationary Combustion (Fuel)'
        SCOPE_2_ELECTRICITY = 'SCOPE_2_ELECTRICITY', 'Scope 2: Purchased Electricity'
        SCOPE_3_TRAVEL = 'SCOPE_3_TRAVEL', 'Scope 3 Category 6: Employee Business Travel'
        SCOPE_3_PROCUREMENT = 'SCOPE_3_PROCUREMENT', 'Scope 3 Category 1: Purchased Goods'
        EXCLUDED_LOGISTICS = 'EXCLUDED_LOGISTICS', 'Excluded: Internal Logistical Transfer'
        EXCLUDED_AVOIDED = 'EXCLUDED_AVOIDED', 'Excluded: Solar Export / Avoided Emissions'

    class NormalizedUnit(models.TextChoices):
        LITERS = 'LITERS', 'Liters'
        KWH = 'KWH', 'Kilowatt-Hours'
        PASSENGER_KM = 'PASSENGER_KM', 'Passenger-Kilometers'
        METRIC_TONS = 'METRIC_TONS', 'Metric Tons'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='normalized_activities')
    raw_payload = models.ForeignKey(RawPayload, on_delete=models.SET_NULL, null=True, blank=True)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.SET_NULL, null=True, blank=True)

    # Core traceability
    source_row_index = models.IntegerField(null=True, blank=True)
    unique_transaction_id = models.CharField(max_length=100)
    scope_category = models.CharField(max_length=50, choices=ScopeCategory.choices)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    # Raw values
    raw_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    raw_unit = models.CharField(max_length=50)
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    normalized_unit = models.CharField(max_length=20, choices=NormalizedUnit.choices)

    # Carbon intensity output fields
    scope = models.CharField(max_length=50, null=True, blank=True)  # "1", "2", "3"
    category = models.CharField(max_length=100, null=True, blank=True)  # "fuel", "electricity", "flights"
    activity_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    activity_unit = models.CharField(max_length=50, null=True, blank=True)
    normalized_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)  # kgCO2e
    normalized_value_unit = models.CharField(max_length=50, default="kgCO2e")
    emission_factor = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    emission_factor_source = models.CharField(max_length=255, null=True, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    source_row_id = models.CharField(max_length=255, null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    # Facilities mapping
    resolved_facility_id = models.CharField(max_length=100, null=True, blank=True)
    resolved_facility_country = models.CharField(max_length=2)

    # Governance workflow
    status = models.CharField(max_length=50, default="PENDING_REVIEW")
    flag_reason = models.TextField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)
    workflow_status = models.CharField(max_length=30, choices=WorkflowStatus.choices, default=WorkflowStatus.PENDING_REVIEW)
    is_suspicious = models.BooleanField(default=False)
    validation_errors = models.JSONField(default=list, blank=True)
    analyst_notes = models.TextField(null=True, blank=True)
    approved_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.CharField(max_length=150, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    deduplication_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
```

---

## 3. Strict Audit-Lock Immutability

To satisfy financial auditors, any carbon transaction that has been approved or locked (`is_locked = True` or `workflow_status == LOCKED_FOR_AUDIT`) becomes **absolutely read-only**. No analyst, manager, or API request can alter the record's values.

We enforce this immutability rule at two robust levels:
1. **At the Model Level (`models.py`)**: The model's `.save()` method intercepts all database writes. If the record is already locked, it immediately throws a `ValidationError`, halting the database write before any changes can be committed.
2. **At the Serializer Level (`serializers.py`)**: DRF's `validate` checks the status of the record during `PUT` or `PATCH` updates and blocks editing, returning a clean `400 Bad Request` before database transactions even start.

---

## 4. Multi-Tenant Separation & Isolation Boundaries

Data leaks are unacceptable in corporate reporting. Here is how we enforce strict multi-tenant boundaries:

1. **Tenant-Scoped Deduplication Keys**:
   * To prevent duplicate rows from being double-uploaded, we use a unique composite deduplication key. We prefix this key with the tenant's UUID (`tenant_{uuid.hex}_`) during model `.save()` executions.
   * This prevents database constraint collisions: two separate organizations (e.g., KPMG and Tata Motors) can upload identical raw spreadsheets without throwing database integrity crashes.
2. **Seamless Email Domain Resolution**:
   * When an analyst logs in, our custom middleware/view parser reads their work email address domain. Corporate suffixes (like `karan@kpmg.com`) extract the slug `'kpmg'` and provision a dedicated, isolated sandbox.
   * To keep testing and development simple, public or personal domains (gmail, yahoo, outlook, protonmail, etc.) automatically fallback to the standard pre-seeded `'tata-motors'` workspace.
3. **Active Server-Side BOLA & IDOR Overrides**:
   * We don't rely on the client frontend to filter tenant data. Our endpoints ignore any client-supplied `tenant_id` query parameters and force searches to filter strictly by the user's logged-in session tenant.
   * All ledger read, write, and export endpoints are wrapped with Django Rest Framework `@permission_classes([IsAuthenticated])` filters to prevent raw public scraping.
