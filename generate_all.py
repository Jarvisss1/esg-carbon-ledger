#!/usr/bin/env python3
"""
ESG Ingestion Master Data Generator Orchestrator
This script orchestrates the generation of all sample datasets:
1. Standard CSV & Excel formats via generate_sap, generate_travel, generate_utility.
2. Legacy XML IDoc format representing SAP R/3 MBGMCR03 structure.
3. Synchronous OData REST JSON format representing SAP S/4HANA material document response.
4. Deeply nested Concur Itinerary v4 JSON response format.
5. Navan TMC JSON format demonstrating ticket lifecycles and guest flags.
"""

import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import random
from datetime import datetime, timedelta

# Import existing generators
import generate_sap
import generate_travel
import generate_utility

# Set random seed for reproducibility
random.seed(101)

def run_base_generators():
    """Runs the imported generator scripts to produce baseline CSVs and Excel files."""
    print("--- Running baseline CSV & Excel data generators ---")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    sap_out = os.path.join(base_dir, "sample_data", "sap")
    travel_out = os.path.join(base_dir, "sample_data", "travel")
    utility_out = os.path.join(base_dir, "sample_data", "utility")
    
    os.makedirs(sap_out, exist_ok=True)
    os.makedirs(travel_out, exist_ok=True)
    os.makedirs(utility_out, exist_ok=True)
    
    # Generate SAP
    generate_sap.generate_procurement_csv(os.path.join(sap_out, "sap_procurement.csv"))
    generate_sap.generate_fuel_xlsx(os.path.join(sap_out, "sap_fuel_consumption.xlsx"))
    generate_sap.generate_idoc_flatfile(os.path.join(sap_out, "sap_procurement.idoc"))
    
    # Generate Travel
    generate_travel.generate_travel_csv(os.path.join(travel_out, "travel_corporate.csv"))
    
    # Generate Utility
    generate_utility.generate_in_utility(os.path.join(utility_out, "utility_electricity_IN.csv"))
    generate_utility.generate_uk_utility(os.path.join(utility_out, "utility_electricity_UK.csv"))
    print("Baseline CSV & Excel files generated successfully.\n")

def generate_sap_odata_json(path):
    """Generates simulated OData REST responses representing API_MATERIAL_DOCUMENT_SRV query."""
    print("[SAP] Generating OData JSON response...")
    
    materials = [
        {"id": "MAT-F001", "desc": "Diesel fuel oil", "unit": "L"},
        {"id": "MAT-F003", "desc": "Natural Gas", "unit": "M3"},
        {"id": "MAT-F005", "desc": "Premium Gasoline", "unit": "L"},
        {"id": "MAT-F007", "desc": "Sub-bituminous Coal", "unit": "TO"}
    ]
    
    plants = ["PL01", "PL02", "PL04", "PL05"]
    movements = ["241", "242", "101", "313", "315"]
    
    results = []
    
    # We will generate 30 records
    for i in range(30):
        mat = random.choice(materials)
        plant = random.choice(plants)
        mvt = random.choice(movements)
        
        qty = round(random.uniform(500, 25000), 3)
        # 10% chance of negative quantity (reversal / credit)
        if random.random() < 0.10:
            qty = -qty
            
        # Mix date styles (ISO 8601 vs Microsoft JSON epoch dates)
        d = datetime.now() - timedelta(days=random.randint(1, 360))
        if random.random() < 0.5:
            posting_date = d.strftime("%Y-%m-%dT00:00:00")
        else:
            epoch_ms = int(d.timestamp() * 1000)
            posting_date = f"/Date({epoch_ms})/"
            
        item = {
            "__metadata": {
                "id": f"https://s4hana.enterprise.com/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentItem(MaterialDocument='100000{i:04d}',MaterialDocumentYear='2025',MaterialDocumentItem='1')",
                "uri": f"https://s4hana.enterprise.com/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentItem(MaterialDocument='100000{i:04d}',MaterialDocumentYear='2025',MaterialDocumentItem='1')",
                "type": "API_MATERIAL_DOCUMENT_SRV.A_MaterialDocumentItemType"
            },
            "MaterialDocument": f"100000{i:04d}",
            "MaterialDocumentYear": "2025",
            "MaterialDocumentItem": "1",
            "Material": mat["id"],
            "Plant": plant,
            "StorageLocation": f"SL{random.randint(1,5):02d}",
            "GoodsMovementType": mvt,
            "QuantityInEntryUnit": f"{qty:.3f}",  # Stringified decimal with trailing zeroes
            "EntryUnit": mat["unit"],
            "EntryUnitISOCode": mat["unit"],
            "PostingDate": posting_date,
            "MasterFixedAsset": f"FA-GEN-{random.randint(10,99)}" if mvt == "241" else "",
            "CostCenter": f"CC-OPS-{random.randint(1,4):02d}"
        }
        results.append(item)
        
    payload = {
        "d": {
            "results": results
        }
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[SAP] OData JSON response written to {path}\n")

def generate_sap_idoc_xml(path):
    """Generates an XML file mimicking the legacy SAP MBGMCR03 IDoc basic type."""
    print("[SAP] Generating legacy XML IDoc...")
    
    root = ET.Element("MBGMCR03")
    
    # EDI_DC40 Control Record segment
    edi_dc = ET.SubElement(root, "EDI_DC40", SEGMENT="1")
    ET.SubElement(edi_dc, "TABNAM").text = "EDI_DC40"
    ET.SubElement(edi_dc, "MANDT").text = "100"
    ET.SubElement(edi_dc, "DOCNUM").text = f"{random.randint(1000000000000000, 9999999999999999)}"
    ET.SubElement(edi_dc, "IDOCTYP").text = "MBGMCR03"
    ET.SubElement(edi_dc, "MESTYP").text = "MBGMCR"
    ET.SubElement(edi_dc, "SNDPRN").text = "SAP_ECC_PRD"
    ET.SubElement(edi_dc, "RCVPRN").text = "ESG_INGEST_GW"
    
    # E1MBGMCR Main Document Header Segment
    e1mbgmcr = ET.SubElement(root, "E1MBGMCR", SEGMENT="1")
    
    # Injected dirt: TESTRUN field is filled which simulates transaction without saving
    ET.SubElement(e1mbgmcr, "TESTRUN").text = "X" if random.random() < 0.15 else ""
    
    # E1BP2017_GM_HEAD_01 Header parameters
    head = ET.SubElement(e1mbgmcr, "E1BP2017_GM_HEAD_01", SEGMENT="1")
    ET.SubElement(head, "PSTNG_DATE").text = datetime.now().strftime("%Y%m%d")
    ET.SubElement(head, "DOC_DATE").text = datetime.now().strftime("%Y%m%d")
    ET.SubElement(head, "PR_UNAME").text = "ESG_ANALYST"
    
    # Create several item detail loops representing material documents
    for idx in range(1, 6):
        item = ET.SubElement(e1mbgmcr, "E1BP2017_GM_ITEM_CREATE", SEGMENT="1")
        ET.SubElement(item, "MATERIAL").text = f"MAT-F00{idx}"
        ET.SubElement(item, "PLANT").text = f"PL0{idx}"
        ET.SubElement(item, "STGE_LOC").text = "0001"
        ET.SubElement(item, "MOVE_TYPE").text = random.choice(["101", "241", "313"])
        ET.SubElement(item, "ENTRY_QNT").text = f"{round(random.uniform(100, 5000), 2)}"
        ET.SubElement(item, "ENTRY_UOM").text = "L" if idx != 4 else "KG"
        
        # Opaque reference segments for custom mappings
        parex = ET.SubElement(e1mbgmcr, "E1BPPAREX", SEGMENT="1")
        ET.SubElement(parex, "STRUCTURE").text = "BAPI_TE_MARA"
        ET.SubElement(parex, "VALUEPART1").text = f"Custom equipment flag: EQ-{random.randint(9000, 9999)}"
        
    xml_str = ET.tostring(root, encoding="utf-8")
    
    # Pretty print XML string
    reparsed = minidom.parseString(xml_str)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    print(f"[SAP] Legacy XML IDoc written to {path}\n")

def generate_concur_itinerary_json(path):
    """Generates deeply nested JSON file representing Concur's Itinerary v4 REST endpoint response."""
    print("[Travel] Generating Concur Itinerary JSON...")
    
    cities = [
        {"iata": "DEL", "city": "Delhi", "country": "IN"},
        {"iata": "BOM", "city": "Mumbai", "country": "IN"},
        {"iata": "LHR", "city": "London", "country": "GB"},
        {"iata": "SFO", "city": "San Francisco", "country": "US"},
        {"iata": "JFK", "city": "New York", "country": "US"},
        {"iata": "SIN", "city": "Singapore", "country": "SG"}
    ]
    
    bookings = []
    
    for i in range(12):
        origin = random.choice(cities)
        dest = random.choice([c for c in cities if c["iata"] != origin["iata"]])
        
        booking_date = datetime.now() - timedelta(days=random.randint(15, 60))
        travel_date = datetime.now() - timedelta(days=random.randint(1, 14))
        
        # Deep Concur nesting
        booking = {
            "Id": f"b-{random.randint(100000, 999999)}",
            "ClientLocator": f"LOC{random.randint(1000, 9999)}X",
            "BookingSource": "CONCUR_TRAVEL",
            "Traveller": {
                "EmployeeId": f"EMP-00{random.randint(1, 6)}",
                "EmailAddress": f"employee{random.randint(1,6)}@enterprise.com",
                "ProfileStatus": "ACTIVE"
            },
            "PaymentBreakdown": {
                "BaseFare": round(random.uniform(300, 2500), 2),
                "TaxAmount": round(random.uniform(40, 250), 2),
                "ServiceFees": 15.00,
                "CurrencyCode": random.choice(["USD", "GBP", "EUR", "INR"])
            },
            "Segments": [
                {
                    "SegmentType": "AIR",
                    "AirlineCode": random.choice(["AI", "BA", "EK", "SQ"]),
                    "FlightNumber": f"{random.randint(100, 999)}",
                    "CabinClass": random.choice(["Economy", "Business", "First"]),
                    "Departure": {
                        "AirportCode": origin["iata"],
                        "City": origin["city"],
                        "DateTime": travel_date.strftime("%Y-%m-%dT%H:%M:%S")
                    },
                    "Arrival": {
                        "AirportCode": dest["iata"],
                        "City": dest["city"],
                        "DateTime": (travel_date + timedelta(hours=random.randint(1, 14))).strftime("%Y-%m-%dT%H:%M:%S")
                    },
                    "DistanceKilometers": None  # ← OMITTED in Concur raw response, forces Haversine resolution
                }
            ]
        }
        
        # 40% of trips have a nested hotel segment
        if random.random() < 0.4:
            hotel_checkin = travel_date
            nights = random.randint(1, 5)
            hotel_checkout = hotel_checkin + timedelta(days=nights)
            
            booking["Segments"].append({
                "SegmentType": "HOTEL",
                "HotelChain": random.choice(["Marriott", "Hilton", "Taj Hotels", "Hyatt"]),
                "Location": {
                    "City": dest["city"],
                    "CountryCode": dest["country"]
                },
                "CheckInDate": hotel_checkin.strftime("%Y-%m-%d"),
                "CheckOutDate": hotel_checkout.strftime("%Y-%m-%d"),
                "NumberOfNights": nights,
                "NightlyRate": round(random.uniform(120, 450), 2),
                "LocalCurrency": "USD" if dest["country"] != "IN" else "INR"
            })
            
        bookings.append(booking)
        
    payload = {
        "ItineraryList": {
            "Count": len(bookings),
            "Bookings": bookings
        }
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[Travel] Concur JSON written to {path}\n")

def generate_navan_tmc_json(path):
    """Generates JSON representing Navan's TMC API tracking flight statuses and traveler types."""
    print("[Travel] Generating Navan TMC JSON...")
    
    cities = ["DEL", "BOM", "LHR", "SFO", "JFK", "SIN"]
    bookings = []
    
    for i in range(10):
        origin = random.choice(cities)
        dest = random.choice([c for c in cities if c != origin])
        
        # State machine mutability (HOLD -> TICKETED -> CANCELED)
        status = random.choices(["TICKETED", "HOLD", "CANCELED"], weights=[75, 15, 10])[0]
        
        # Traveler boundaries (Employee vs. Guest)
        is_guest = random.random() < 0.20
        if is_guest:
            passenger = {
                "firstName": f"GuestFirstName{i}",
                "lastName": f"GuestLastName{i}",
                "employeeId": None,
                "email": f"guest_{i}@external-partner.com",
                "passengerType": "GUEST"
            }
        else:
            emp_num = random.randint(1, 6)
            passenger = {
                "firstName": f"EmpFirstName{emp_num}",
                "lastName": f"EmpLastName{emp_num}",
                "employeeId": f"EMP-00{emp_num}",
                "email": f"employee{emp_num}@enterprise.com",
                "passengerType": "EMPLOYEE"
            }
            
        travel_date = datetime.now() - timedelta(days=random.randint(1, 180))
        
        booking = {
            "bookingId": f"navan-{random.randint(500000, 999999)}",
            "bookingStatus": status,
            "createdDate": (travel_date - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "passengerInfo": [passenger],
            "flightDetails": {
                "carrierCode": random.choice(["AI", "BA", "EK", "SQ"]),
                "cabinClassCode": random.choice(["Y", "W", "J", "F"]),  # Y=Eco, W=PremEco, J=Biz, F=First
                "originAirport": origin,
                "destinationAirport": dest,
                "departureDateTime": travel_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "arrivalDateTime": (travel_date + timedelta(hours=random.randint(2, 12))).strftime("%Y-%m-%dT%H:%M:%SZ")
            },
            "financials": {
                "totalCharge": round(random.uniform(250, 1800), 2),
                "serviceFee": 10.00,
                "currency": "USD" if origin != "DEL" else "INR"
            }
        }
        bookings.append(booking)
        
    payload = {
        "navanTmcResponse": {
            "totalCount": len(bookings),
            "data": bookings
        }
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[Travel] Navan TMC JSON written to {path}\n")

def main():
    """Main runner."""
    print("====================================================")
    print("ESG Ingestion Suite: Master Mock Data Generator")
    print("====================================================\n")
    
    # 1. Run the imported base generators (will output to local directories)
    run_base_generators()
    
    # 2. Paths for new multi-format files
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sap_out = os.path.join(base_dir, "sample_data", "sap")
    travel_out = os.path.join(base_dir, "sample_data", "travel")
    
    # 3. Generate SAP OData JSON & XML IDoc
    generate_sap_odata_json(os.path.join(sap_out, "sap_material_document_odata.json"))
    generate_sap_idoc_xml(os.path.join(sap_out, "sap_mbgmcr03_idoc.xml"))
    
    # 4. Generate Travel Concur JSON & Navan JSON
    generate_concur_itinerary_json(os.path.join(travel_out, "travel_concur_itinerary_v4.json"))
    generate_navan_tmc_json(os.path.join(travel_out, "travel_navan_tmc.json"))
    
    print("====================================================")
    print("All mock files successfully written to relative paths:")
    print(f"  SAP:    {sap_out}")
    print(f"  Travel: {travel_out}")
    print(f"  Utility: {os.path.join(base_dir, 'sample_data', 'utility')}")
    print("====================================================")

if __name__ == "__main__":
    main()
