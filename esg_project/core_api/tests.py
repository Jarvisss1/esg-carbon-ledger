import os
import json
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from .models import Tenant, RawPayload, Airport, NormalizedActivity, AuditLog

class ESGIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Default seeded Tenant created in migrations: 7aa7f899-25de-4db6-a3e6-932e12ec76e1
        cls.tenant = Tenant.objects.get(id='7aa7f899-25de-4db6-a3e6-932e12ec76e1')
        cls.sample_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "sample_data")

    def setUp(self):
        self.client = APIClient()

    def test_01_sap_procurement_csv_ingestion(self):
        csv_path = os.path.join(self.sample_data_dir, "sap", "sap_procurement.csv")
        self.assertTrue(os.path.exists(csv_path), "Mock sap_procurement.csv must exist.")
        
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.SAP_CSV,
            "filename": "sap_procurement.csv",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_01 ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["records_created"] > 0)
        
        # Check standard goods receipt vs internal transfer exclusions
        exclusions = NormalizedActivity.objects.filter(
            tenant=self.tenant, 
            scope_category=NormalizedActivity.ScopeCategory.EXCLUDED_LOGISTICS
        )
        for esc in exclusions:
            self.assertEqual(esc.normalized_quantity, Decimal('0.0000'))

    def test_02_sap_fuel_xlsx_ingestion(self):
        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.SAP_XLSX,
            "filename": "sap_fuel_consumption.xlsx",
            "payload_content": "excel-placeholder-trigger"
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_02 ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["records_created"] > 0)

        fuel_activity = NormalizedActivity.objects.filter(
            raw_payload__source_system=RawPayload.SourceSystem.SAP_XLSX
        ).first()
        self.assertEqual(fuel_activity.normalized_unit, NormalizedActivity.NormalizedUnit.LITERS)

    def test_03_sap_odata_json_ingestion(self):
        odata_path = os.path.join(self.sample_data_dir, "sap", "sap_material_document_odata.json")
        self.assertTrue(os.path.exists(odata_path))
        
        with open(odata_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.SAP_ODATA,
            "filename": "sap_material_document_odata.json",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_03 ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["records_created"] > 0)

        activities = NormalizedActivity.objects.filter(raw_payload__source_system=RawPayload.SourceSystem.SAP_ODATA)
        for act in activities:
            self.assertTrue(act.start_date is not None)

    def test_04_sap_idoc_xml_ingestion(self):
        idoc_path = os.path.join(self.sample_data_dir, "sap", "sap_mbgmcr03_idoc.xml")
        self.assertTrue(os.path.exists(idoc_path))
        
        with open(idoc_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.SAP_IDOC,
            "filename": "sap_mbgmcr03_idoc.xml",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_04 ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["records_created"] > 0)

        suspicious_idoc = NormalizedActivity.objects.filter(
            raw_payload__source_system=RawPayload.SourceSystem.SAP_IDOC,
            is_suspicious=True
        )
        for act in suspicious_idoc:
            if "TESTRUN" in str(act.validation_errors):
                self.assertTrue(act.is_suspicious)

    def test_04b_sap_idoc_flat_ingestion(self):
        idoc_path = os.path.join(self.sample_data_dir, "sap", "sap_procurement.idoc")
        self.assertTrue(os.path.exists(idoc_path))
        
        with open(idoc_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.SAP_IDOC,
            "filename": "sap_procurement.idoc",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_04B ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["records_created"], 2)

        activities = NormalizedActivity.objects.filter(
            raw_payload__source_system=RawPayload.SourceSystem.SAP_IDOC,
            unique_transaction_id="4500004341"
        )
        self.assertEqual(activities.count(), 2)
        
        diesel_item = activities.filter(raw_data__material__icontains="diesel").first()
        self.assertIsNotNone(diesel_item)
        self.assertEqual(float(diesel_item.raw_quantity), 1500.0)
        self.assertEqual(diesel_item.raw_unit, "L")
        self.assertTrue(diesel_item.normalized_value > 0)
        
        refrig_item = activities.filter(raw_data__material__icontains="refrigerant").first()
        self.assertIsNotNone(refrig_item)
        self.assertEqual(float(refrig_item.raw_quantity), 85.0)
        self.assertEqual(refrig_item.raw_unit, "KG")
        self.assertTrue(refrig_item.normalized_value > 0)

    def test_05_utility_in_proration(self):
        in_path = os.path.join(self.sample_data_dir, "utility", "utility_electricity_IN.csv")
        self.assertTrue(os.path.exists(in_path))
        
        with open(in_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.UTILITY_IN_CSV,
            "filename": "utility_electricity_IN.csv",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_05 ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        avoided_solar = NormalizedActivity.objects.filter(
            raw_payload__source_system=RawPayload.SourceSystem.UTILITY_IN_CSV,
            scope_category=NormalizedActivity.ScopeCategory.EXCLUDED_AVOIDED
        )
        self.assertTrue(avoided_solar.exists(), "Negative net energy should split as avoided solar emissions.")
        for r in avoided_solar:
            self.assertTrue(r.normalized_quantity > 0)

    def test_06_travel_coordinate_haversine(self):
        travel_path = os.path.join(self.sample_data_dir, "travel", "travel_corporate.csv")
        self.assertTrue(os.path.exists(travel_path))
        
        with open(travel_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.TRAVEL_CSV,
            "filename": "travel_corporate.csv",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_06 ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        activities = NormalizedActivity.objects.filter(
            raw_payload__source_system=RawPayload.SourceSystem.TRAVEL_CSV,
            unique_transaction_id__contains="T-"
        )
        for act in activities:
            if act.resolved_facility_id == "SFO" and "JFK" in str(act.validation_errors or ""):
                self.assertAlmostEqual(float(act.normalized_quantity), 4160 * 1.08, delta=100)

    def test_07_navan_mutable_booking_cancellations(self):
        navan_path = os.path.join(self.sample_data_dir, "travel", "travel_navan_tmc.json")
        self.assertTrue(os.path.exists(navan_path))
        
        with open(navan_path, "r", encoding="utf-8") as f:
            content = f.read()

        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.NAVAN_JSON,
            "filename": "travel_navan_tmc.json",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')

        if response.status_code != status.HTTP_201_CREATED:
            print("TEST_07 INGEST ERROR:", response.content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Simulate dynamic webhook cancellation processing inside double entry locked period
        # 1. Create a dummy record and mock its LOCK_FOR_AUDIT status
        locked_activity = NormalizedActivity.objects.create(
            tenant=self.tenant,
            raw_payload=RawPayload.objects.filter(source_system=RawPayload.SourceSystem.NAVAN_JSON).first(),
            source_row_index=0,
            unique_transaction_id="navan-cancel-test-id",
            scope_category=NormalizedActivity.ScopeCategory.SCOPE_3_TRAVEL,
            start_date=timezone.now() - timedelta(days=40),
            end_date=timezone.now() - timedelta(days=40),
            raw_quantity=Decimal('0.0000'),
            raw_unit='passenger-km',
            normalized_quantity=Decimal('5000.0000'),
            normalized_unit=NormalizedActivity.NormalizedUnit.PASSENGER_KM,
            resolved_facility_id='SFO',
            resolved_facility_country='US',
            workflow_status=NormalizedActivity.WorkflowStatus.LOCKED_FOR_AUDIT,
            deduplication_key="navan-cancel-test-key"
        )
        
        # 2. Mock Navan webhook cancellation request containing the exact bookingId
        cancel_payload = {
            "navanTmcResponse": {
                "totalCount": 1,
                "data": [
                    {
                        "bookingId": "navan-cancel-test-id",
                        "bookingStatus": "CANCELED",
                        "createdDate": "2025-10-10T00:00:00Z",
                        "passengerInfo": [{"passengerType": "EMPLOYEE", "employeeId": "EMP-001"}],
                        "flightDetails": {
                            "carrierCode": "SQ",
                            "cabinClassCode": "Y",
                            "originAirport": "SFO",
                            "destinationAirport": "JFK",
                            "departureDateTime": "2025-10-25T00:00:00Z"
                        },
                        "financials": {"totalCharge": 1000.00, "serviceFee": 10.00, "currency": "USD"}
                    }
                ]
            }
        }
        
        # 3. Post webhook update
        webhook_response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.NAVAN_JSON,
            "filename": "navan_webhook_cancel.json",
            "payload_content": json.dumps(cancel_payload)
        }, format='json', HTTP_X_USER='navan_webhook_pipeline')
        
        if webhook_response.status_code != status.HTTP_201_CREATED:
            print("TEST_07 WEBHOOK CANCEL ERROR:", webhook_response.content)
        self.assertEqual(webhook_response.status_code, status.HTTP_201_CREATED)
        
        # 4. Assert that a compensating NEGATIVE entry has been created in the main ledger
        compensating_record = NormalizedActivity.objects.get(
            unique_transaction_id="navan-cancel-test-id",
            normalized_quantity__lt=0
        )
        self.assertAlmostEqual(float(compensating_record.normalized_quantity), -4160 * 1.08, delta=100)
        self.assertEqual(compensating_record.workflow_status, NormalizedActivity.WorkflowStatus.PENDING_REVIEW)
        self.assertTrue("Cancellation received" in str(compensating_record.validation_errors))

    def test_08_manual_overrides_and_lock_rules(self):
        # 1. Create a raw payload first so NormalizedActivity has a valid raw payload
        dummy_raw = RawPayload.objects.create(
            tenant=self.tenant,
            source_system=RawPayload.SourceSystem.SAP_CSV,
            filename='dummy.csv',
            payload_content='dummy_csv_content',
            payload_hash='hash123',
            ingested_by='system'
        )

        # 2. Create a record to edit
        act = NormalizedActivity.objects.create(
            tenant=self.tenant,
            raw_payload=dummy_raw,
            source_row_index=1,
            unique_transaction_id="manual-override-test-id",
            scope_category=NormalizedActivity.ScopeCategory.SCOPE_1_STATIONARY,
            start_date=timezone.now(),
            end_date=timezone.now(),
            raw_quantity=Decimal('100.0000'),
            raw_unit='L',
            normalized_quantity=Decimal('100.0000'),
            normalized_unit=NormalizedActivity.NormalizedUnit.LITERS,
            resolved_facility_id='PL01',
            resolved_facility_country='IN',
            workflow_status=NormalizedActivity.WorkflowStatus.PENDING_REVIEW,
            deduplication_key="manual-override-test-key"
        )
        
        detail_url = reverse('activity_detail', kwargs={'pk': act.id})
        
        # 3. PUT edit attempt without mandatory override notes (should fail)
        response_no_notes = self.client.put(detail_url, {
            "normalized_quantity": 150.00,
        }, format='json', HTTP_X_USER='analyst@tata.com')
        if response_no_notes.status_code != status.HTTP_400_BAD_REQUEST:
            print("TEST_08_NO_NOTES ERROR DETAILS:", response_no_notes.status_code, response_no_notes.content)
        self.assertEqual(response_no_notes.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("note" in response_no_notes.data["error"])

        # 4. PUT edit attempt without authentication header (should fail)
        response_no_auth = self.client.put(detail_url, {
            "normalized_quantity": 150.00,
            "analyst_notes": "Updating diesel consumption to match physical log invoice."
        }, format='json')
        if response_no_auth.status_code != status.HTTP_400_BAD_REQUEST:
            print("TEST_08_NO_AUTH ERROR DETAILS:", response_no_auth.status_code, response_no_auth.content)
        self.assertEqual(response_no_auth.status_code, status.HTTP_400_BAD_REQUEST)

        # 5. Successful PUT manual edit with notes (including dynamic vendor and distance_km editing)
        response_success = self.client.put(detail_url, {
            "normalized_quantity": 150.00,
            "vendor": "EcoTransport Corp",
            "distance_km": 420.5,
            "analyst_notes": "Updating diesel consumption and vendor to match physical log invoice."
        }, format='json', HTTP_X_USER='analyst@tata.com')
        if response_success.status_code != status.HTTP_200_OK:
            print("TEST_08_SUCCESS ERROR DETAILS:", response_success.status_code, response_success.content)
        self.assertEqual(response_success.status_code, status.HTTP_200_OK)
        
        # Verify Audit Log recorded delta change (100 -> 150) plus dynamic fields
        logs = AuditLog.objects.filter(activity=act, action=AuditLog.AuditAction.EDIT)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(float(logs[0].previous_values["normalized_quantity"]), 100.0)
        self.assertEqual(float(logs[0].new_values["normalized_quantity"]), 150.0)
        self.assertEqual(logs[0].new_values["vendor"], "EcoTransport Corp")
        self.assertEqual(logs[0].new_values["distance_km"], "420.5")
        
        # Verify that activity raw_data reflects the edits
        act.refresh_from_db()
        self.assertEqual(act.raw_data["vendor"], "EcoTransport Corp")
        self.assertEqual(act.raw_data["distance_km"], 420.5)
        
        self.assertEqual(logs[0].changed_by, "analyst@tata.com")
        self.assertEqual(logs[0].reason, "Updating diesel consumption and vendor to match physical log invoice.")

        # 6. Transition to LOCKED_FOR_AUDIT
        bulk_url = reverse('bulk_action')
        # First approve the record
        self.client.post(bulk_url, {
            "ids": [str(act.id)],
            "action": "bulk-approve"
        }, format='json', HTTP_X_USER='lead_auditor@tata.com')
        
        # Lock the record
        self.client.post(bulk_url, {
            "ids": [str(act.id)],
            "action": "bulk-lock"
        }, format='json', HTTP_X_USER='lead_auditor@tata.com')
        
        act.refresh_from_db()
        self.assertEqual(act.workflow_status, NormalizedActivity.WorkflowStatus.LOCKED_FOR_AUDIT)

        # 7. Attempt PUT manual edit on LOCKED record (should fail)
        response_lock_fail = self.client.put(detail_url, {
            "normalized_quantity": 200.00,
            "analyst_notes": "Manual correction on audited year."
        }, format='json', HTTP_X_USER='analyst@tata.com')
        
        self.assertEqual(response_lock_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("LOCKED" in response_lock_fail.data["error"])

    def test_09_robust_token_authentication(self):
        # 1. Test registration endpoint
        reg_url = reverse('register_user')
        reg_resp = self.client.post(reg_url, {
            "username": "tata_analyst",
            "email": "tata_analyst@tata.com",
            "password": "securepassword123!"
        }, format='json')
        self.assertEqual(reg_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", reg_resp.data)
        token_key = reg_resp.data["token"]

        # 2. Test obtain token endpoint
        token_url = reverse('obtain_token')
        token_resp = self.client.post(token_url, {
            "username": "tata_analyst",
            "password": "securepassword123!"
        }, format='json')
        self.assertEqual(token_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(token_resp.data["token"], token_key)

        # 3. Test user profile using standard DRF Token Auth
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_key)
        me_url = reverse('user_profile')
        me_resp = self.client.get(me_url)
        self.assertEqual(me_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(me_resp.data["username"], "tata_analyst")
        self.client.credentials()

        # 4. Test production security hardening on dynamic headers (DEBUG = False)
        from django.test import override_settings
        with override_settings(DEBUG=False):
            list_url = reverse('list_activities')
            
            import sys
            original_argv = sys.argv
            try:
                # Temporarily strip 'test' from sys.argv to simulate a true production environment
                sys.argv = [a for a in sys.argv if a != 'test']
                
                # Case A: No internal bypass secret configured. Dynamic headers should be strictly forbidden.
                resp_no_secret = self.client.get(list_url, {"tenant_id": str(self.tenant.id)}, 
                                                 HTTP_X_USER='analyst@tata.com')
                self.assertEqual(resp_no_secret.status_code, status.HTTP_403_FORBIDDEN)
                
                # Case B: Secret configured in settings but missing from headers. Should fail.
                with override_settings(INTERNAL_BYPASS_SECRET="prod-secret-key"):
                    resp_missing_secret = self.client.get(list_url, {"tenant_id": str(self.tenant.id)}, 
                                                         HTTP_X_USER='analyst@tata.com')
                    self.assertEqual(resp_missing_secret.status_code, status.HTTP_403_FORBIDDEN)
                    
                    # Case C: Correct secret provided. Should succeed.
                    resp_success_secret = self.client.get(list_url, {"tenant_id": str(self.tenant.id)}, 
                                                         HTTP_X_USER='analyst@tata.com',
                                                         HTTP_X_INTERNAL_BYPASS_SECRET='prod-secret-key')
                    self.assertEqual(resp_success_secret.status_code, status.HTTP_200_OK)
            finally:
                sys.argv = original_argv


    def test_10_z_score_outlier_flagging(self):
        # Ingest 16 rows of utility data (15 normal rows + 1 extreme outlier)
        # This increases the sample size N to allow the z-score of the outlier to mathematically exceed 3.
        rows = ["Meter_ID,Quantity,Unit,Period_Start,Period_End"]
        for i in range(15):
            rows.append("METER-IN-01,100,kWh,2025-04-01,2025-04-30")
        rows.append("METER-IN-01,10000,kWh,2025-04-01,2025-04-30")  # Extreme outlier (>3 standard deviations)
        content = "\n".join(rows) + "\n"
        
        url = reverse('ingest_raw_payload')
        response = self.client.post(url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.UTILITY_IN_CSV,
            "filename": "utility_outliers.csv",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify that the outlier is flagged
        outlier = NormalizedActivity.objects.filter(
            raw_payload__filename="utility_outliers.csv",
            raw_quantity=Decimal('10000.0000')
        ).first()
        
        self.assertTrue(outlier.is_suspicious)
        self.assertEqual(outlier.status, "FLAGGED")
        self.assertTrue("Statistical outlier" in outlier.flag_reason)

    def test_11_export_governance_and_email(self):
        # 1. Ingest a clean SAP dataset and bulk-approve it
        content = (
            "PO_Number,Movement_Type,Quantity,Unit,Posting_Date,Plant,Material_Number,Material_Description\n"
            "PO-EXPORT-01,241,100,L,2025-04-10,PL01,MAT-001,Diesel Fuel Oil\n"
            "PO-EXPORT-02,241,120,L,2025-04-12,PL01,MAT-001,Diesel Fuel Oil\n"
        )
        
        ingest_url = reverse('ingest_raw_payload')
        ingest_resp = self.client.post(ingest_url, {
            "tenant_id": str(self.tenant.id),
            "source_system": RawPayload.SourceSystem.SAP_CSV,
            "filename": "sap_export_test.csv",
            "payload_content": content
        }, format='json', HTTP_X_USER='analyst@tata.com')
        
        self.assertEqual(ingest_resp.status_code, status.HTTP_201_CREATED)
        
        records = NormalizedActivity.objects.filter(raw_payload__filename="sap_export_test.csv")
        record_ids = [str(r.id) for r in records]
        
        # Bulk Approve the records to make them eligible for export!
        bulk_url = reverse('bulk_action')
        self.client.post(bulk_url, {
            "ids": record_ids,
            "action": "bulk-approve"
        }, format='json', HTTP_X_USER='analyst@tata.com')
        
        # 2. Trigger Email Export in XLSX format
        export_url = reverse('records_export')
        export_resp = self.client.post(export_url, {
            "format": "XLSX",
            "delivery": "email",
            "email": "lead_auditor@tatamotors.com"
        }, format='json', HTTP_X_USER='analyst@tata.com')
        
        self.assertEqual(export_resp.status_code, status.HTTP_200_OK)
        self.assertTrue("emailed to lead_auditor@tatamotors.com" in export_resp.data["message"])
        
        # 3. Assert ExportLog entry was successfully logged
        from .models import ExportLog
        export_log = ExportLog.objects.filter(user="analyst@tata.com").last()
        self.assertIsNotNone(export_log)
        self.assertEqual(export_log.export_type, "XLSX Email")
        self.assertTrue(export_log.row_count >= 2)
        self.assertEqual(export_log.source_filters["email"], "lead_auditor@tatamotors.com")
        
        # 4. Verify mock email in Django's test outbox (overridden to locmem by Django testing framework)
        from django.core import mail
        self.assertTrue(len(mail.outbox) > 0)
        self.assertEqual(mail.outbox[0].subject, 'Approved ESG Carbon Ledger Export')
        self.assertEqual(mail.outbox[0].to[0], 'lead_auditor@tatamotors.com')
