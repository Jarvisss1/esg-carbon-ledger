from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, unique=True, default="tata-motors")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class RawPayload(models.Model):
    class SourceSystem(models.TextChoices):
        SAP_ODATA = 'SAP_ODATA', 'SAP OData API'
        SAP_IDOC = 'SAP_IDOC', 'SAP Legacy XML IDoc'
        SAP_CSV = 'SAP_CSV', 'SAP Procurement CSV'
        SAP_XLSX = 'SAP_XLSX', 'SAP Fuel Consumption Excel'
        UTILITY_IN_CSV = 'UTILITY_IN_CSV', 'Indian Utility Smart Meter CSV'
        UTILITY_UK_CSV = 'UTILITY_UK_CSV', 'UK Utility aggregate CSV'
        TRAVEL_CSV = 'TRAVEL_CSV', 'Concur-style Travel CSV'
        CONCUR_JSON = 'CONCUR_JSON', 'Concur Itinerary API JSON'
        NAVAN_JSON = 'NAVAN_JSON', 'Navan TMC API JSON'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='raw_payloads')
    source_system = models.CharField(max_length=50, choices=SourceSystem.choices)
    filename = models.CharField(max_length=255, null=True, blank=True)
    payload_content = models.TextField(help_text="Stores the exact raw upload text or JSON representation")
    payload_hash = models.CharField(max_length=64, help_text="SHA-256 integrity checksum to prevent tempering")
    ingested_at = models.DateTimeField(auto_now_add=True)
    ingested_by = models.CharField(max_length=150, help_text="Identity of the analyst or pipeline")

    def __str__(self):
        return f"{self.source_system} ({self.filename or 'API Blob'}) - {self.ingested_at.strftime('%Y-%m-%d')}"

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
    raw_payload = models.OneToOneField(RawPayload, on_delete=models.SET_NULL, null=True, blank=True, related_name='batch')

    def __str__(self):
        return f"{self.source_type} Batch: {self.file_name} by {self.uploaded_by} on {self.uploaded_at.strftime('%Y-%m-%d')}"

class Airport(models.Model):
    iata_code = models.CharField(max_length=3, primary_key=True, help_text="3-letter airport code e.g. SFO")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    city = models.CharField(max_length=255)
    country = models.CharField(max_length=2, help_text="2-letter country code")

    def __str__(self):
        return f"{self.iata_code} ({self.city}, {self.country})"

class NormalizedActivity(models.Model):
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
    raw_payload = models.ForeignKey(RawPayload, on_delete=models.SET_NULL, null=True, blank=True, related_name='normalized_activities')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='normalized_activities')

    source_row_index = models.IntegerField(help_text="Line or element index inside the raw data source", null=True, blank=True)
    unique_transaction_id = models.CharField(max_length=100, help_text="Source system ID, e.g. booking ID, document number")

    scope_category = models.CharField(max_length=50, choices=ScopeCategory.choices)
    start_date = models.DateTimeField(help_text="Calculated activity start date in UTC")
    end_date = models.DateTimeField(help_text="Calculated activity end date in UTC")

    # Raw fields
    raw_quantity = models.DecimalField(max_digits=18, decimal_places=4, help_text="Quantity exactly as extracted")
    raw_unit = models.CharField(max_length=50, help_text="Original unit as extracted, e.g. GAL, MWh, TO")

    # Normalized fields (compat)
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4, help_text="Standardized baseline quantity")
    normalized_unit = models.CharField(max_length=20, choices=NormalizedUnit.choices)

    # ESG target fields (new)
    scope = models.CharField(max_length=50, help_text="Scope e.g. 1/2/3", null=True, blank=True)
    category = models.CharField(max_length=100, help_text="Category e.g. fuel, electricity, flights, hotels, ground", null=True, blank=True)
    activity_value = models.DecimalField(max_digits=18, decimal_places=4, help_text="Raw quantity value", null=True, blank=True)
    activity_unit = models.CharField(max_length=50, help_text="Raw quantity unit", null=True, blank=True)
    normalized_value = models.DecimalField(max_digits=18, decimal_places=4, help_text="Normalized emission in kgCO2e", null=True, blank=True)
    normalized_value_unit = models.CharField(max_length=50, default="kgCO2e", help_text="Emission unit, always kgCO2e")
    emission_factor = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    emission_factor_source = models.CharField(max_length=255, null=True, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    source_row_id = models.CharField(max_length=255, null=True, blank=True, help_text="Unique row hash")
    raw_data = models.JSONField(default=dict, blank=True, help_text="Source raw row JSON content")
    status = models.CharField(max_length=50, default="PENDING_REVIEW")
    flag_reason = models.TextField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)

    # Geospatial/Facilitative fields
    resolved_facility_id = models.CharField(max_length=100, null=True, blank=True, help_text="Opaque facility ID mapped during lookup")
    resolved_facility_country = models.CharField(max_length=2, help_text="Resolved 2-letter country code")

    # Workflow State (compat)
    workflow_status = models.CharField(max_length=30, choices=WorkflowStatus.choices, default=WorkflowStatus.PENDING_REVIEW)
    is_suspicious = models.BooleanField(default=False, help_text="True if parsing flagged anomalies or validation issues")
    validation_errors = models.JSONField(default=list, blank=True, help_text="Parser-level failure or suspicion details")
    analyst_notes = models.TextField(null=True, blank=True, help_text="Compulsory notes for editing or overrides")
    approved_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_records')
    approved_by = models.CharField(max_length=150, null=True, blank=True, help_text="Compat string for user email")
    approved_at = models.DateTimeField(null=True, blank=True)

    # Dynamic key to prevent loading duplicates on batch reruns
    deduplication_key = models.CharField(max_length=255, unique=True, help_text="Dynamic hashing of txn_id, date, and scope")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        # Secure tenant-scoping of deduplication keys to prevent cross-tenant key collisions
        if self.deduplication_key and self.tenant:
            tenant_prefix = f"tenant_{self.tenant.id.hex}_"
            if not self.deduplication_key.startswith(tenant_prefix):
                self.deduplication_key = f"{tenant_prefix}{self.deduplication_key}"

        # Enforce Audit-Lock Immutability
        if self.pk:
            try:
                orig = NormalizedActivity.objects.get(pk=self.pk)
                if orig.is_locked or orig.workflow_status == NormalizedActivity.WorkflowStatus.LOCKED_FOR_AUDIT:
                    if self.is_locked != orig.is_locked or self.workflow_status != orig.workflow_status:
                        pass
                    else:
                        from django.core.exceptions import ValidationError
                        raise ValidationError("LOCKED: This record is LOCKED FOR AUDIT and cannot be modified.")
            except NormalizedActivity.DoesNotExist:
                pass
        super().save(*args, **kwargs)

# Python alias for strategy and clean imports
EmissionRecord = NormalizedActivity

class AuditLog(models.Model):
    class AuditAction(models.TextChoices):
        CREATE = 'CREATE', 'Created via Ingestion'
        EDIT = 'EDIT', 'Modified by Analyst'
        APPROVE = 'APPROVE', 'Approved by Analyst'
        REJECT = 'REJECT', 'Rejected by Analyst'
        LOCK = 'LOCK', 'Locked for Audits'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(NormalizedActivity, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=AuditAction.choices)
    changed_by = models.CharField(max_length=150, help_text="Identity of the active user as string")
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_actions')
    changed_at = models.DateTimeField(auto_now_add=True)
    previous_values = models.JSONField(default=dict, blank=True, help_text="Snapshot of fields before modification")
    new_values = models.JSONField(default=dict, blank=True, help_text="Snapshot of fields after modification")
    reason = models.TextField(help_text="Mandatory analyst explanation for overrides")

    @property
    def record(self):
        return self.activity

    @property
    def performed_at(self):
        return self.changed_at

    @property
    def note(self):
        return self.reason

    @property
    def before_value(self):
        return self.previous_values

    @property
    def after_value(self):
        return self.new_values

    def __str__(self):
        return f"{self.action} on {self.activity.id} by {self.changed_by} at {self.changed_at.strftime('%Y-%m-%d %H:%M')}"

class ExportLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.CharField(max_length=150, help_text="User identity who exported the data")
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='export_logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    export_type = models.CharField(max_length=50, help_text="CSV or XLSX, Download or Email")
    row_count = models.IntegerField(default=0)
    source_filters = models.JSONField(default=dict, blank=True, help_text="Filters applied to the export")

    def __str__(self):
        return f"Export by {self.user} on {self.timestamp.strftime('%Y-%m-%d %H:%M')}: {self.export_type} ({self.row_count} rows)"
