from rest_framework import serializers
from .models import Tenant, RawPayload, Airport, EmissionRecord, AuditLog, IngestionBatch, ExportLog

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'

class RawPayloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawPayload
        fields = '__all__'

class IngestionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionBatch
        fields = '__all__'

class AirportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Airport
        fields = '__all__'

class EmissionRecordSerializer(serializers.ModelSerializer):
    source_filename = serializers.CharField(source='raw_payload.filename', read_only=True)
    source_system = serializers.CharField(source='raw_payload.source_system', read_only=True)

    class Meta:
        model = EmissionRecord
        fields = '__all__'

    def validate(self, attrs):
        if self.instance and (self.instance.is_locked or self.instance.workflow_status == EmissionRecord.WorkflowStatus.LOCKED_FOR_AUDIT):
            raise serializers.ValidationError({"error": "Forbidden: This record is LOCKED FOR AUDIT and is completely immutable."})
        return attrs

# Alias for backwards compatibility
NormalizedActivitySerializer = EmissionRecordSerializer

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'

class ExportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportLog
        fields = '__all__'
