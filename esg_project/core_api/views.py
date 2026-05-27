import hashlib
import io
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.db import transaction
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
import pandas as pd
from django.core.cache import cache

def get_cache_key(prefix, request):
    # Unique cache key for each request parameters list
    params = sorted(request.query_params.items())
    params_str = "&".join(f"{k}={v}" for k, v in params)
    return f"esg_{prefix}_{params_str}"

def invalidate_esg_cache():
    # Invalidate all local caches when updates happen
    cache.clear()


from .models import Tenant, RawPayload, Airport, EmissionRecord, AuditLog, IngestionBatch, ExportLog
from .serializers import TenantSerializer, RawPayloadSerializer, EmissionRecordSerializer, AuditLogSerializer, IngestionBatchSerializer, ExportLogSerializer
from .parsers import parse_payload

@api_view(['POST'])
def ingest_raw_payload(request):
    """
    Ingests a raw payload, calculates its SHA-256 hash, stores it,
    and runs the dynamic parser immediately.
    """
    tenant_id = request.data.get('tenant_id')
    source_system = request.data.get('source_system')
    filename = request.data.get('filename', 'API Blob')
    payload_content = request.data.get('payload_content')
    
    # Custom ingested_by header fallback for mock user tracking
    user_identity = request.headers.get('X-User', 'ESG Ingestion Pipeline')
    if request.user.is_authenticated:
        user_identity = request.user.email or request.user.username

    if not tenant_id or not source_system or not payload_content:
        return Response(
            {"error": "Missing mandatory fields: tenant_id, source_system, and payload_content are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except (Tenant.DoesNotExist, ValidationError):
        return Response(
            {"error": f"Invalid Tenant UUID: '{tenant_id}' does not exist."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Compute SHA-256 integrity hash
    hasher = hashlib.sha256()
    hasher.update(payload_content.encode('utf-8'))
    payload_hash = hasher.hexdigest()

    try:
        with transaction.atomic():
            raw_payload = RawPayload.objects.create(
                tenant=tenant,
                source_system=source_system,
                filename=filename,
                payload_content=payload_content,
                payload_hash=payload_hash,
                ingested_by=user_identity
            )
            
            # Enqueue dynamic parser background task
            from .ingest_queue import enqueue_ingestion
            enqueue_ingestion(raw_payload.id)
            
        return Response({
            "message": "Raw payload ingested successfully. Ingestion processing has been scheduled in the background.",
            "raw_payload_id": raw_payload.id,
            "integrity_hash": payload_hash,
            "status": "PROCESSING"
        }, status=status.HTTP_202_ACCEPTED)

    except ValidationError as ve:
        return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Ingestion failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 1000

def _list_activities_impl(request):
    cache_key = get_cache_key("activities", request)
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return Response(cached_data, status=status.HTTP_200_OK)

    activities = EmissionRecord.objects.select_related('raw_payload').defer('raw_payload__payload_content').order_by('-start_date')
    
    tenant_id = request.query_params.get('tenant_id')
    if not tenant_id:
        first_tenant = Tenant.objects.first()
        tenant_id = first_tenant.id if first_tenant else None
        
    status_filter = request.query_params.get('workflow_status')
    scope_filter = request.query_params.get('scope_category')
    suspicious_filter = request.query_params.get('is_suspicious')

    if tenant_id:
        activities = activities.filter(tenant_id=tenant_id)
    if status_filter:
        activities = activities.filter(workflow_status=status_filter)
    if scope_filter:
        activities = activities.filter(scope_category=scope_filter)
    if suspicious_filter:
        activities = activities.filter(is_suspicious=(suspicious_filter.lower() == 'true'))

    # Support frontend-specific query parameters
    approved_filter = request.query_params.get('approved')
    if approved_filter is not None:
        if approved_filter.lower() == 'true':
            activities = activities.filter(workflow_status__in=['APPROVED', 'LOCKED_FOR_AUDIT'])
        elif approved_filter.lower() == 'false':
            activities = activities.exclude(workflow_status__in=['APPROVED', 'LOCKED_FOR_AUDIT'])

    excluded_filter = request.query_params.get('excluded')
    if excluded_filter is not None:
        if excluded_filter.lower() == 'true':
            activities = activities.filter(workflow_status='REJECTED')
        elif excluded_filter.lower() == 'false':
            activities = activities.exclude(workflow_status='REJECTED')

    is_outlier_filter = request.query_params.get('is_outlier')
    if is_outlier_filter is not None:
        activities = activities.filter(is_suspicious=(is_outlier_filter.lower() == 'true'))

    search_query = request.query_params.get('search')
    if search_query and search_query.strip():
        q = search_query.strip()
        from django.db.models import Q
        activities = activities.filter(
            Q(unique_transaction_id__icontains=q) |
            Q(resolved_facility_id__icontains=q) |
            Q(resolved_facility_country__icontains=q) |
            Q(analyst_notes__icontains=q) |
            Q(scope_category__icontains=q)
        )

    # Check if page is requested or if pagination is preferred
    page_param = request.query_params.get('page')
    if page_param is not None or request.query_params.get('page_size') is not None:
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(activities, request)
        if page is not None:
            serializer = EmissionRecordSerializer(page, many=True)
            res = paginator.get_paginated_response(serializer.data)
            cache.set(cache_key, res.data, 300)
            return res

    serializer = EmissionRecordSerializer(activities, many=True)
    cache.set(cache_key, serializer.data, 300)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
def list_activities(request):
    """
    Returns filterable, tenant-scoped emission records.
    Filters: tenant_id, workflow_status, scope_category, is_suspicious
    """
    return _list_activities_impl(request)

@api_view(['GET', 'PUT'])
def activity_detail(request, pk):
    """
    GET: Returns details of a specific normalized record.
    PUT: Allows editing fields. Requires X-User header or Authenticated User and mandatory override notes.
    """
    try:
        activity = EmissionRecord.objects.select_related('raw_payload').defer('raw_payload__payload_content').get(pk=pk)
    except (EmissionRecord.DoesNotExist, ValidationError):
        return Response({"error": "EmissionRecord not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = EmissionRecordSerializer(activity)
        return Response(serializer.data)

    elif request.method == 'PUT':
        # Enforce Audit-Lock Immutability
        if activity.is_locked or activity.workflow_status == EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT:
            return Response(
                {"error": "LOCKED: This record is LOCKED FOR AUDIT and is completely immutable."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_identity = request.headers.get('X-User')
        if request.user.is_authenticated:
            user_identity = request.user.email or request.user.username

        if not user_identity:
            return Response(
                {"error": "Authentication Error: Authenticated User or X-User header is required for audit logs."},
                status=status.HTTP_400_BAD_REQUEST
            )

        notes = request.data.get('analyst_notes') or request.data.get('note')
        if not notes or len(str(notes).strip()) < 5:
            return Response(
                {"error": {"note": ["Validation Error: A detailed analyst override note (minimum 5 chars) is mandatory for overrides."]}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Track delta changes
        updatable_fields = [
            'scope_category', 'start_date', 'end_date',
            'normalized_quantity', 'normalized_unit',
            'normalized_value', 'normalized_value_unit',
            'resolved_facility_id', 'resolved_facility_country',
            'is_suspicious', 'analyst_notes', 'status', 'is_locked'
        ]

        previous_values = {}
        new_values = {}
        has_changed = False

        for field in updatable_fields:
            if field in request.data:
                old_val = getattr(activity, field)
                new_val = request.data[field]
                
                # Coerce values for exact type comparisons
                if isinstance(old_val, Decimal):
                    new_val_coerced = Decimal(str(new_val)) if new_val is not None else None
                elif isinstance(old_val, bool):
                    new_val_coerced = bool(new_val) if new_val is not None else None
                elif isinstance(old_val, datetime):
                    new_val_coerced = timezone.make_aware(datetime.strptime(str(new_val).replace('Z', ''), "%Y-%m-%dT%H:%M:%S"), timezone.utc) if new_val else None
                else:
                    new_val_coerced = new_val

                if old_val != new_val_coerced:
                    previous_values[field] = str(old_val) if old_val is not None else '—'
                    new_values[field] = str(new_val_coerced) if new_val_coerced is not None else '—'
                    setattr(activity, field, new_val_coerced)
                    has_changed = True

        # Handle dynamic fields in raw_data (vendor, distance_km)
        dynamic_fields = ['vendor', 'distance_km']
        for field in dynamic_fields:
            if field in request.data:
                if not isinstance(activity.raw_data, dict):
                    activity.raw_data = {}
                old_val = activity.raw_data.get(field) or activity.raw_data.get(field.capitalize())
                new_val = request.data[field]
                
                if str(old_val) != str(new_val):
                    previous_values[field] = str(old_val) if old_val is not None else '—'
                    new_values[field] = str(new_val) if new_val is not None else '—'
                    
                    # Update both lowercase and capitalized keys to ensure mapRecord/parsers pick it up
                    activity.raw_data[field] = new_val
                    activity.raw_data[field.capitalize()] = new_val
                    has_changed = True

        if has_changed:
            with transaction.atomic():
                # Editing a record resets status to pending review
                activity.workflow_status = EmissionRecord.WorkflowStatus.PENDING_REVIEW
                activity.status = "PENDING_REVIEW"
                activity.save()
                
                user_obj = request.user if request.user.is_authenticated else None
                
                # Save manual change delta in strict AuditLog
                AuditLog.objects.create(
                    activity=activity,
                    action=AuditLog.AuditAction.EDIT,
                    changed_by=user_identity,
                    performed_by=user_obj,
                    previous_values=previous_values,
                    new_values=new_values,
                    reason=notes
                )
            invalidate_esg_cache()

        serializer = EmissionRecordSerializer(activity)
        return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['POST'])
def bulk_action(request):
    """
    Performs bulk workflow transitions: bulk-approve, bulk-lock, bulk-reject.
    Payload: {"ids": [UUID1, UUID2], "action": "bulk-approve"}
    """
    ids = request.data.get('ids', [])
    action = request.data.get('action')
    user_identity = request.headers.get('X-User', 'ESG Lead Auditor')
    if request.user.is_authenticated:
        user_identity = request.user.email or request.user.username

    if not ids or not action:
        return Response(
            {"error": "Missing mandatory body fields: 'ids' (array) and 'action' (string) are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    action_enum_map = {
        'bulk-approve': (EmissionRecord.WorkflowStatus.APPROVED, "APPROVED", AuditLog.AuditAction.APPROVE, "Bulk approved by analyst.", False),
        'bulk-lock': (EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT, "APPROVED", AuditLog.AuditAction.LOCK, "Bulk locked for final audit.", True),
        'bulk-reject': (EmissionRecord.WorkflowStatus.REJECTED, "REJECTED", AuditLog.AuditAction.REJECT, "Bulk rejected / excluded from ledger.", False)
    }

    if action not in action_enum_map:
        return Response(
            {"error": f"Invalid action '{action}'. Options are: bulk-approve, bulk-lock, bulk-reject."},
            status=status.HTTP_400_BAD_REQUEST
        )

    target_workflow, target_status, audit_action, default_reason, target_lock = action_enum_map[action]
    updated_records = []
    skipped_records = []

    with transaction.atomic():
        for record_id in ids:
            try:
                activity = EmissionRecord.objects.get(id=record_id)
                
                # Check Lock transitions: locked records cannot be altered or re-approved
                if activity.is_locked or activity.workflow_status == EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT:
                    skipped_records.append({"id": record_id, "reason": "Already LOCKED FOR AUDIT"})
                    continue
                
                # Check lock constraints: only APPROVED rows can transition to LOCKED_FOR_AUDIT
                if action == 'bulk-lock' and activity.workflow_status != EmissionRecord.WorkflowStatus.APPROVED:
                    skipped_records.append({"id": record_id, "reason": "Only APPROVED records can transition to LOCKED."})
                    continue

                previous_status = activity.workflow_status
                activity.workflow_status = target_workflow
                activity.status = target_status
                activity.is_locked = target_lock
                
                if action == 'bulk-approve':
                    activity.approved_by = user_identity
                    if request.user.is_authenticated:
                        activity.approved_by_user = request.user
                    activity.approved_at = timezone.now()
                activity.save()

                user_obj = request.user if request.user.is_authenticated else None

                AuditLog.objects.create(
                    activity=activity,
                    action=audit_action,
                    changed_by=user_identity,
                    performed_by=user_obj,
                    previous_values={"workflow_status": previous_status},
                    new_values={"workflow_status": target_workflow},
                    reason=default_reason
                )
                updated_records.append(record_id)

            except (EmissionRecord.DoesNotExist, ValidationError):
                skipped_records.append({"id": record_id, "reason": "Invalid UUID or Not Found"})

        invalidate_esg_cache()

    return Response({
        "message": f"Bulk action '{action}' completed.",
        "processed_count": len(updated_records),
        "updated_ids": updated_records,
        "skipped_records": skipped_records
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
def activity_audit_logs(request, pk):
    """
    Returns all historical AuditLog rows linked to a specific EmissionRecord / NormalizedActivity.
    """
    try:
        activity = EmissionRecord.objects.get(pk=pk)
    except (EmissionRecord.DoesNotExist, ValidationError):
        return Response({"error": "EmissionRecord not found."}, status=status.HTTP_404_NOT_FOUND)

    logs = activity.audit_logs.all().order_by('-changed_at')
    serializer = AuditLogSerializer(logs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
def list_tenants(request):
    """
    Lists all active Tenant entities.
    """
    tenants = Tenant.objects.all()
    serializer = TenantSerializer(tenants, many=True)
    return Response(serializer.data)

# --- BATCHES MANAGEMENT API ENDPOINTS ---

@api_view(['GET'])
def list_batches(request):
    """
    Returns a list of all IngestionBatch runs.
    """
    cache_key = get_cache_key("batches", request)
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return Response(cached_data, status=status.HTTP_200_OK)

    tenant_id = request.query_params.get('tenant_id')
    if not tenant_id:
        first_tenant = Tenant.objects.first()
        tenant_id = first_tenant.id if first_tenant else None
        
    batches = IngestionBatch.objects.all().order_by('-uploaded_at')
    if tenant_id:
        batches = batches.filter(tenant_id=tenant_id)
    serializer = IngestionBatchSerializer(batches, many=True)
    cache.set(cache_key, serializer.data, 300)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
def batch_records(request, pk):
    """
    Returns paginated/filtered list of EmissionRecord rows created in a specific batch.
    """
    cache_key = f"esg_batch_records_{pk}_{get_cache_key('', request)}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return Response(cached_data, status=status.HTTP_200_OK)

    try:
        batch = IngestionBatch.objects.get(id=pk)
    except (IngestionBatch.DoesNotExist, ValidationError):
        return Response({"error": "IngestionBatch not found."}, status=status.HTTP_404_NOT_FOUND)
        
    records = batch.normalized_activities.select_related('raw_payload').defer('raw_payload__payload_content').order_by('-start_date')
    
    # Support standard filters
    status_filter = request.query_params.get('workflow_status')
    if status_filter:
        records = records.filter(workflow_status=status_filter)

    approved_filter = request.query_params.get('approved')
    if approved_filter is not None:
        if approved_filter.lower() == 'true':
            records = records.filter(workflow_status__in=['APPROVED', 'LOCKED_FOR_AUDIT'])
        elif approved_filter.lower() == 'false':
            records = records.exclude(workflow_status__in=['APPROVED', 'LOCKED_FOR_AUDIT'])

    excluded_filter = request.query_params.get('excluded')
    if excluded_filter is not None:
        if excluded_filter.lower() == 'true':
            records = records.filter(workflow_status='REJECTED')
        elif excluded_filter.lower() == 'false':
            records = records.exclude(workflow_status='REJECTED')

    is_outlier_filter = request.query_params.get('is_outlier')
    if is_outlier_filter is not None:
        records = records.filter(is_suspicious=(is_outlier_filter.lower() == 'true'))

    search_query = request.query_params.get('search')
    if search_query and search_query.strip():
        q = search_query.strip()
        from django.db.models import Q
        records = records.filter(
            Q(unique_transaction_id__icontains=q) |
            Q(resolved_facility_id__icontains=q) |
            Q(resolved_facility_country__icontains=q) |
            Q(analyst_notes__icontains=q) |
            Q(scope_category__icontains=q)
        )

    # Check if page is requested or if pagination is preferred
    page_param = request.query_params.get('page')
    if page_param is not None or request.query_params.get('page_size') is not None:
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(records, request)
        if page is not None:
            serializer = EmissionRecordSerializer(page, many=True)
            res = paginator.get_paginated_response(serializer.data)
            cache.set(cache_key, res.data, 300)
            return res
            
    serializer = EmissionRecordSerializer(records, many=True)
    cache.set(cache_key, serializer.data, 300)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['POST'])
def batch_upload(request):
    """
    POST multipart file upload to ingest file in an IngestionBatch link.
    """
    tenant_id = request.data.get('tenant_id')
    source_type = request.data.get('source_type')
    uploaded_file = request.FILES.get('file')
    
    user_identity = request.headers.get('X-User', 'lead_analyst@tata.com')
    if request.user.is_authenticated:
        user_identity = request.user.email or request.user.username

    if not tenant_id or not source_type or not uploaded_file:
        return Response({"error": "Missing parameters: 'tenant_id', 'source_type' (SAP/UTILITY/TRAVEL) and 'file' are required."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except (Tenant.DoesNotExist, ValidationError):
        return Response({"error": f"Tenant '{tenant_id}' does not exist."}, status=status.HTTP_404_NOT_FOUND)

    # Convert source_type to standard options mapping
    source_type = source_type.upper()
    filename_lower = uploaded_file.name.lower()
    
    if source_type == "SAP":
        if filename_lower.endswith(('.xlsx', '.xls')):
            source_sys = RawPayload.SourceSystem.SAP_XLSX
        elif filename_lower.endswith('.xml') or 'idoc' in filename_lower:
            source_sys = RawPayload.SourceSystem.SAP_IDOC
        else:
            source_sys = RawPayload.SourceSystem.SAP_CSV
    elif source_type == "UTILITY":
        if "uk" in filename_lower:
            source_sys = RawPayload.SourceSystem.UTILITY_UK_CSV
        else:
            source_sys = RawPayload.SourceSystem.UTILITY_IN_CSV
    elif source_type == "TRAVEL":
        if filename_lower.endswith('.json'):
            source_sys = RawPayload.SourceSystem.CONCUR_JSON
        else:
            source_sys = RawPayload.SourceSystem.TRAVEL_CSV
    else:
        source_system_mapping = {
            "SAP_CSV": RawPayload.SourceSystem.SAP_CSV,
            "SAP_XLSX": RawPayload.SourceSystem.SAP_XLSX,
            "SAP_IDOC": RawPayload.SourceSystem.SAP_IDOC,
            "UTILITY_IN": RawPayload.SourceSystem.UTILITY_IN_CSV,
            "UTILITY_UK": RawPayload.SourceSystem.UTILITY_UK_CSV,
            "TRAVEL_CSV": RawPayload.SourceSystem.TRAVEL_CSV,
            "CONCUR_JSON": RawPayload.SourceSystem.CONCUR_JSON,
        }
        source_sys = source_system_mapping.get(source_type, RawPayload.SourceSystem.SAP_CSV)

    file_content = uploaded_file.read()
    uploaded_file.seek(0)  # Reset pointer so Django saves the full file!
    
    payload_str = file_content.decode('utf-8', errors='ignore')

    hasher = hashlib.sha256()
    hasher.update(payload_str.encode('utf-8'))
    payload_hash = hasher.hexdigest()

    try:
        with transaction.atomic():
            raw_payload = RawPayload.objects.create(
                tenant=tenant,
                source_system=source_sys,
                filename=uploaded_file.name,
                payload_content=payload_str,
                payload_hash=payload_hash,
                ingested_by=user_identity
            )
            
            # Setup batch in PROCESSING status initially
            batch = IngestionBatch.objects.create(
                tenant=tenant,
                source_type=source_type,
                uploaded_by=user_identity,
                file_name=uploaded_file.name,
                raw_file=uploaded_file,
                raw_payload=raw_payload,
                status="PROCESSING"
            )
            
            # Enqueue to background ingestion queue
            from .ingest_queue import enqueue_ingestion
            enqueue_ingestion(raw_payload.id, batch.id)
            
        return Response({
            "message": "File batch uploaded successfully. Processing has been scheduled in the background.",
            "batch_id": batch.id,
            "raw_payload_id": raw_payload.id,
            "status": "PROCESSING"
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        return Response({"error": f"Batch Ingestion failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- REQUISITE STRATEGY API ENDPOINTS ---

@api_view(['GET'])
def records_list(request):
    """
    Returns all records, filterable by status/scope/date.
    """
    return _list_activities_impl(request)

@api_view(['PATCH'])
def record_approve(request, pk):
    """
    PATCH /api/records/{id}/approve/ -> set status=approved, lock EmissionRecord
    """
    try:
        activity = EmissionRecord.objects.select_related('raw_payload').defer('raw_payload__payload_content').get(pk=pk)
    except (EmissionRecord.DoesNotExist, ValidationError):
        return Response({"error": "EmissionRecord not found."}, status=status.HTTP_404_NOT_FOUND)
        
    user_identity = request.headers.get('X-User', 'lead_analyst@tata.com')
    if request.user.is_authenticated:
        user_identity = request.user.email or request.user.username

    user_obj = request.user if request.user.is_authenticated else None
    
    with transaction.atomic():
        previous_status = activity.workflow_status
        activity.workflow_status = EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT
        activity.status = "APPROVED"
        activity.is_locked = True
        activity.approved_by = user_identity
        activity.approved_by_user = user_obj
        activity.approved_at = timezone.now()
        activity.save()
        
        AuditLog.objects.create(
            activity=activity,
            action=AuditLog.AuditAction.LOCK,
            changed_by=user_identity,
            performed_by=user_obj,
            previous_values={"workflow_status": previous_status},
            new_values={"workflow_status": EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT},
            reason="Analyst signed off and audit-locked the emission record."
        )
        
    invalidate_esg_cache()
    serializer = EmissionRecordSerializer(activity)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['PATCH'])
def record_reject(request, pk):
    """
    PATCH /api/records/{id}/reject/ -> set status=rejected + flag_reason
    """
    try:
        activity = EmissionRecord.objects.select_related('raw_payload').defer('raw_payload__payload_content').get(pk=pk)
    except (EmissionRecord.DoesNotExist, ValidationError):
        return Response({"error": "EmissionRecord not found."}, status=status.HTTP_404_NOT_FOUND)
        
    user_identity = request.headers.get('X-User', 'lead_analyst@tata.com')
    if request.user.is_authenticated:
        user_identity = request.user.email or request.user.username

    user_obj = request.user if request.user.is_authenticated else None
    
    reason = request.data.get('flag_reason') or request.data.get('reason') or "Rejected / Excluded from Ledger"
    
    with transaction.atomic():
        previous_status = activity.workflow_status
        activity.workflow_status = EmissionRecord.WorkflowStatus.REJECTED
        activity.status = "REJECTED"
        activity.flag_reason = reason
        activity.save()
        
        AuditLog.objects.create(
            activity=activity,
            action=AuditLog.AuditAction.REJECT,
            changed_by=user_identity,
            performed_by=user_obj,
            previous_values={"workflow_status": previous_status},
            new_values={"workflow_status": EmissionRecord.WorkflowStatus.REJECTED},
            reason=reason
        )
        
    invalidate_esg_cache()
    serializer = EmissionRecordSerializer(activity)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
def dashboard_summary(request):
    """
    Returns aggregated emissions (kgCO2e) grouped by Scope (1/2/3) and Category.
    Also returns unified database-level record statistics for optimal dashboard load speeds.
    """
    cache_key = "esg_dashboard_summary"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return Response(cached_data, status=status.HTTP_200_OK)

    scope_aggregation = {}
    categories_aggregation = {}
    
    records = EmissionRecord.objects.all()
    
    # Calculate database-level statistics using lightning-fast .count()
    total = records.count()
    approved = records.filter(workflow_status__in=['APPROVED', 'LOCKED_FOR_AUDIT']).count()
    flagged = records.filter(is_suspicious=True).count()
    pending = records.exclude(workflow_status__in=['APPROVED', 'LOCKED_FOR_AUDIT', 'REJECTED']).count()

    approved_records = records.filter(
        workflow_status__in=[EmissionRecord.WorkflowStatus.APPROVED, EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT]
    )
    
    for r in approved_records:
        sc = r.scope or "unknown"
        val = float(r.normalized_value or r.normalized_quantity or 0)
        
        scope_aggregation[sc] = scope_aggregation.get(sc, 0.0) + val
        
        cat = r.category or "unknown"
        categories_aggregation[cat] = categories_aggregation.get(cat, 0.0) + val
        
    res_data = {
        "total": total,
        "approved": approved,
        "flagged": flagged,
        "pending": pending,
        "total_emissions_kgco2e": sum(scope_aggregation.values()),
        "by_scope": scope_aggregation,
        "by_category": categories_aggregation
    }
    cache.set(cache_key, res_data, 300)
    return Response(res_data, status=status.HTTP_200_OK)

@api_view(['POST'])
def records_export(request):
    """
    Exports approved records to CSV or XLSX format, either as direct download or via email.
    Saves the physical file directly inside Supabase Object Storage (S3) under exports/ prefix,
    and logs the event to ExportLog with its secure expiring download URL.
    """
    export_format = request.data.get('format', 'CSV').upper()
    delivery = request.data.get('delivery', 'download').lower()
    recipient_email = request.data.get('email', '')
    
    if export_format not in ('CSV', 'XLSX'):
        return Response({"error": "Invalid format. Options are: CSV, XLSX"}, status=status.HTTP_400_BAD_REQUEST)
        
    if delivery == 'email' and not recipient_email:
        return Response({"error": "Email address is required for email delivery format."}, status=status.HTTP_400_BAD_REQUEST)
        
    # Get only approved / locked records for strict ESG compliance governance!
    records = EmissionRecord.objects.filter(
        workflow_status__in=[EmissionRecord.WorkflowStatus.APPROVED, EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT]
    ).order_by('-start_date')
    
    batch_id = request.data.get('batch_id')
    if batch_id:
        records = records.filter(batch_id=batch_id)
        
    row_count = records.count()
    
    # Prepare Pandas DataFrame
    data_list = []
    for r in records:
        data_list.append({
            "ID": str(r.id),
            "Tenant": r.tenant.name,
            "Scope": r.scope or r.scope_category,
            "Category": r.category,
            "Activity Value": float(r.activity_value or r.raw_quantity or 0),
            "Activity Unit": r.activity_unit or r.raw_unit or "",
            "Emissions (kgCO2e)": float(r.normalized_value or r.normalized_quantity or 0),
            "Emission Factor": float(r.emission_factor or 0),
            "Emission Factor Source": r.emission_factor_source or "",
            "Period Start": r.period_start.strftime('%Y-%m-%d %H:%M:%S') if r.period_start else "",
            "Period End": r.period_end.strftime('%Y-%m-%d %H:%M:%S') if r.period_end else "",
            "Facility": r.resolved_facility_id,
            "Country": r.resolved_facility_country,
            "Status": r.workflow_status
        })
        
    df = pd.DataFrame(data_list)
    
    # Generate file contents and settings
    if export_format == 'CSV':
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        file_data = csv_buffer.getvalue().encode('utf-8')
        content_type = 'text/csv'
        file_ext = 'csv'
    else:  # XLSX
        xlsx_buffer = io.BytesIO()
        with pd.ExcelWriter(xlsx_buffer, engine='openpyxl') as writer:
            # 1. Summary sheet
            summary_data = []
            if not df.empty:
                summary_data.append({"Metric": "Total Approved Records", "Value": int(row_count)})
                summary_data.append({"Metric": "Total Emissions (kgCO2e)", "Value": float(df["Emissions (kgCO2e)"].sum())})
                by_scope = df.groupby("Scope")["Emissions (kgCO2e)"].sum().to_dict()
                for sc, val in by_scope.items():
                    summary_data.append({"Metric": f"Scope {sc} Emissions (kgCO2e)", "Value": float(val)})
            else:
                summary_data.append({"Metric": "No approved records found.", "Value": 0})
            
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="Summary Dashboard", index=False)
            
            # 2. Detailed sheet
            df.to_excel(writer, sheet_name="Emission Records", index=False)
            
        file_data = xlsx_buffer.getvalue()
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        file_ext = 'xlsx'

    # Save to Supabase Storage S3
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import uuid

    file_url = ""
    try:
        file_name = f"exports/export_{uuid.uuid4().hex}.{file_ext}"
        stored_path = default_storage.save(file_name, ContentFile(file_data))
        file_url = default_storage.url(stored_path)
    except Exception as se:
        # Fallback if storage backend is not fully activated (e.g. offline testing)
        print(f"Supabase Storage S3 upload failed, returning fallback stream: {se}")

    # Logging the export
    user_identity = request.headers.get('X-User', 'lead_analyst@tata.com')
    if request.user.is_authenticated:
        user_identity = request.user.email or request.user.username
        
    user_obj = request.user if request.user.is_authenticated else None
    
    ExportLog.objects.create(
        user=user_identity,
        performed_by=user_obj,
        export_type=f"{export_format} {delivery.capitalize()}",
        row_count=row_count,
        source_filters={"format": export_format, "delivery": delivery, "email": recipient_email, "file_url": file_url}
    )
    invalidate_esg_cache()
    
    if export_format == 'CSV':
        if delivery == 'download':
            response = HttpResponse(file_data, content_type=content_type)
            response['Content-Disposition'] = 'attachment; filename="esg_emissions_ledger.csv"'
            return response
        else:
            email = EmailMessage(
                subject='Approved ESG Carbon Ledger Export',
                body=f'Hello,\n\nPlease find attached the approved ESG carbon ledger CSV export containing {row_count} records.\n\nBest Regards,\nESG Analytics Platform',
                from_email='no-reply@esgplatform.com',
                to=[recipient_email]
            )
            email.attach('esg_emissions_ledger.csv', file_data, content_type)
            email.send()
            return Response({"message": f"Approved ledger CSV exported and emailed to {recipient_email} successfully.", "row_count": row_count}, status=status.HTTP_200_OK)
            
    elif export_format == 'XLSX':
        if delivery == 'download':
            response = HttpResponse(file_data, content_type=content_type)
            response['Content-Disposition'] = 'attachment; filename="esg_emissions_ledger.xlsx"'
            return response
        else:
            email = EmailMessage(
                subject='Approved ESG Carbon Ledger Export',
                body=f'Hello,\n\nPlease find attached the approved ESG carbon ledger XLSX export containing {row_count} records and summary dashboard.\n\nBest Regards,\nESG Analytics Platform',
                from_email='no-reply@esgplatform.com',
                to=[recipient_email]
            )
            email.attach('esg_emissions_ledger.xlsx', file_data, content_type)
            email.send()
            return Response({"message": f"Approved ledger XLSX exported and emailed to {recipient_email} successfully.", "row_count": row_count}, status=status.HTTP_200_OK)

@api_view(['GET'])
def list_export_logs(request):
    """
    GET /api/records/exports/
    Returns list of all historical exports.
    """
    logs = ExportLog.objects.all().order_by('-timestamp')
    data = []
    for log in logs:
        data.append({
            "id": str(log.id),
            "user": log.user,
            "format": log.source_filters.get('format', 'CSV'),
            "delivery_method": log.source_filters.get('delivery', 'download'),
            "email_recipient": log.source_filters.get('email', ''),
            "rows_exported": log.row_count,
            "exported_at": log.timestamp.isoformat(),
            "success": True,
            "file_url": log.source_filters.get('file_url', '')
        })
    return Response(data, status=status.HTTP_200_OK)

from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny

class CustomObtainAuthToken(ObtainAuthToken):
    """
    POST /api/auth/token/
    Accepts: {"username": "...", "password": "..."}
    Returns: {"token": "...", "user_id": 1, "email": "..."}
    """
    permission_classes = [AllowAny]

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    POST /api/auth/register/
    Accepts: {"username": "...", "email": "...", "password": "..."}
    Returns: {"token": "...", "username": "...", "email": "..."}
    """
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')

    if not username or not email or not password:
        return Response(
            {"error": "Missing mandatory body fields: 'username', 'email', and 'password' are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {"error": "Email already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )
    token, _ = Token.objects.get_or_create(user=user)

    return Response({
        "token": token.key,
        "username": user.username,
        "email": user.email,
        "message": "User registered successfully."
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """
    GET /api/auth/me/
    Requires: Token Authentication
    Returns: {"username": "...", "email": "...", "is_staff": ...}
    """
    return Response({
        "username": request.user.username,
        "email": request.user.email,
        "is_staff": request.user.is_staff,
        "is_active": request.user.is_active
    }, status=status.HTTP_200_OK)

@api_view(['DELETE'])
def batch_delete(request, pk):
    """
    DELETE /api/batches/{id}/ -> deletes the IngestionBatch and all of its associated records.
    """
    import os
    try:
        batch = IngestionBatch.objects.get(id=pk)
    except (IngestionBatch.DoesNotExist, ValidationError):
        return Response({"error": "IngestionBatch not found."}, status=status.HTTP_404_NOT_FOUND)
        
    with transaction.atomic():
        # Deleting a batch deletes all activities created in it
        batch.normalized_activities.all().delete()
        
        # Deleting raw payload
        if batch.raw_payload:
            batch.raw_payload.delete()
            
        # Delete raw file on disk if exists
        if batch.raw_file:
            try:
                if os.path.exists(batch.raw_file.path):
                    os.remove(batch.raw_file.path)
            except Exception:
                pass
                
        batch.delete()
        
    invalidate_esg_cache()
    return Response({"message": "Batch and all associated records deleted successfully."}, status=status.HTTP_200_OK)

