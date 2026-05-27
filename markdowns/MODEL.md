# ESG Ingestion Data Model

This document defines the database architecture and technical data model for the ESG normalization platform. The architecture is designed to support financial-grade auditing, multi-tenancy, and strict tracking of raw sources.

---

## 1. Dual-Layer Provenance Architecture
To satisfy rigorous external ESG audits, the system implements a **dual-layer database design** to separate raw, immutable evidence from the transformed, queryable data.

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
   * **Rule**: Absolute immutability. The original file upload or API response text is stored in its entirety.
   * **Purpose**: Serves as the ultimate source of truth. If a normalization script has a bug, we fix the code and re-process the raw payloads. The historical records are never lost.
   * **Security**: SHA-256 cryptographically verified to prevent silent database tampering.

2. **Ingestion Batch Layer**:
   * **Rule**: Tracks the lifecycle of every uploaded telemetry file.
   * **Purpose**: Allows operational tracking (row/error counts, parsed success status) and enables bulk reversals or rollbacks if a batch is found to contain corrupt source data.

3. **Normalized Activity Layer**:
   * **Rule**: All columns are coerced into a standard relational schema, calculating `normalized_value` in `kgCO2e` strictly based on DEFRA 2023.
   * **Purpose**: Allows analysts to search, flag anomalies, prorate values, and export clean aggregations.

---

## 2. Relational Database Schema (Django Style)

### Tenant Model
Ensures absolute data isolation between different corporate clients.
```python
class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, unique=True, default="tata-motors")
    created_at = models.DateTimeField(auto_now_add=True)
```

### Raw Payload Model
Stores the immutable files and API blobs.
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

### Ingestion Batch Model
Tracks statistics and metadata for each ingestion execution.
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

### Airport Model
Pre-populated table housing coordinates for flight haversine calculations.
```python
class Airport(models.Model):
    iata_code = models.CharField(max_length=3, primary_key=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    city = models.CharField(max_length=255)
    country = models.CharField(max_length=2)
```

### Emission Record Model (aliased to NormalizedActivity)
Houses the final carbon ledger entries. Mapped dynamically to `core_api_normalizedactivity` to maintain backward-compatibility.
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

    # Values (backward compat)
    raw_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    raw_unit = models.CharField(max_length=50)
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    normalized_unit = models.CharField(max_length=20, choices=NormalizedUnit.choices)

    # ESG Upgraded Target Fields
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

    # Geospatial 
    resolved_facility_id = models.CharField(max_length=100, null=True, blank=True)
    resolved_facility_country = models.CharField(max_length=2)

    # Workflow Governance
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

### Audit Log Model
Tracks every single override and workflow transition with pre/post-delta snaps.
```python
class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=20)
    changed_by = models.CharField(max_length=150)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    previous_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    reason = models.TextField()  # Compulsory override notes
```

### Export Log Model
Ensures complete compliance and accountability for carbon data sharing.
```python
class ExportLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.CharField(max_length=150)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    export_type = models.CharField(max_length=50)
    row_count = models.IntegerField(default=0)
    source_filters = models.JSONField(default=dict, blank=True)
```

---

## 3. Strict Audit-Lock Constraint

To satisfy financial auditor guidelines, any `EmissionRecord` that is approved or locked (`is_locked = True` or `workflow_status == LOCKED_FOR_AUDIT`) becomes **strictly read-only**. 

This immutability rule is cryptographically and logically enforced at two separate levels in our backend:
1. **Model Layer (`models.py`)**: The `.save()` method intercepts edits on existing database objects and raises a `ValidationError` if the record is locked, blocking direct Django ORM or Admin overrides.
2. **REST Layer (`serializers.py`)**: The `validate` method on the `EmissionRecordSerializer` raises a validation error during any `PUT` or `PATCH` request, returning an appropriate `400 Bad Request` payload back to the calling application.
