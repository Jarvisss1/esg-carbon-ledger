# **Data Generation Guide: Enterprise ESG Analytics**

This document outlines the structural realities, data formats, and anomalies of three enterprise data sources. Use this schema and edge-case behavior to generate realistic mock data.

## **1\. SAP ERP (Procurement & Fuel Data)**

**Format:** JSON payloads via modern OData services (specifically API\_MATERIAL\_DOCUMENT\_SRV), legacy XML IDocs, or flat-file CSVs.  
**Structure:** Deeply nested JSON/XML or relational table dumps. A root A\_MaterialDocumentHeader entity contains a nested to\_MaterialDocumentItem object, which holds a results array of individual material movement line items.

### **Key Anomalies & Data Generation Rules**

* **Data Types:**  
  * Quantities are often passed as string representations of decimals (e.g., "1.000").  
  * Timestamps appear as ISO 8601 strings (2021-07-11T00:00:00) or legacy Microsoft Epoch strings (/Date(1498946400000)/).  
* **Legacy German Nomenclature & Table Exports:**  
  * Raw database dumps often feature tables like EKPO (Purchasing Document Item) and MSEG (Material Document Segment).  
  * EBELN (Purchasing Document Number) and EBELP (Item Number).  
  * MATNR (Material Number).  
  * WERKS (Plant Code \- an opaque ID like "2100" requiring external lookup).  
  * LGORT (Storage Location).  
  * MENGE (Quantity) and NETWR (Net Order Value).  
  * MEINS (Base Unit of Measure, e.g., "L", "KG").  
  * BUDAT (Posting Date).  
* **IDoc XML Structure (MBGMCR03):** Legacy system integrations often utilize the MBGMCR03 basic type. The XML payload typically contains a root MBGMCR03 element, an EDI\_DC40 control record, and data segments like E1MBGMCR (Header) and E1BP2017\_GM\_ITEM\_CREATE (Item details) containing fields for PLANT, MATERIAL, MOVE\_TYPE, and ENTRY\_QNT.1  
* **Real-World Export Examples:** As seen in standard Kaggle datasets like the *SAP Data Example Project*, analysts frequently work with massive flat-file extracts like SAP Extract Report.xlsx combining these fields for external processing.  
* **Movement Types (Critical Context):**  
  * 101: Standard goods receipt (triggers Scope 3 Category 1 emissions).  
  * 241 / 242: Goods issue to a fixed asset / reversal (triggers direct Scope 1 combustion).  
  * 313 / 315: Internal transfer between locations (logistical shuffling; must be excluded from emissions calculations).

## **2\. Utility Portals (Purchased Electricity)**

**Format:** CSV portal exports (e.g., Green Button XML/CSV format, Octopus Energy smart meter CSVs, or aggregate utility datasets).  
**Structure:** Time-series interval data, typically delivered in 15-minute, 30-minute, or daily increments, or macro-level provider reporting.

### **Key Anomalies & Data Generation Rules**

* **Temporal Misalignment:** Billing periods almost never align with calendar months (e.g., a bill runs March 12th to April 10th).  
* **Interval Data CSV Formats (Site-Level):**  
  * Format 1 (PG\&E Green Button): Missing timezones implying local time. Simple headers like DateTime,kWh (e.g., 2023-01-15 14:30,0.45).3  
  * Format 2 (Octopus Energy UK): Headers use Consumption (kWh), Start, End. Timestamps are ISO 8601 with Daylight Saving Time shifts within the dataset (e.g., alternating between UTC Z and BST \+01:00).4  
* **Aggregate Utility CSV Formats (Macro-Level):** High-level provider datasets (like EIA grid data) typically contain organizational columns such as Utility.Number, Utility.Name, Utility.State, Demand.Summer Peak, Sources.Generation, Uses.Retail, and Revenues.Retail.6  
* **Complex Tariffs:** Columns are often split by tariff rates rather than providing a single total (e.g., columns for Import T1 kWh and Import T2 kWh).  
* **Net Energy Metering (Solar):** Data must include negative float values (e.g., \-1123.0) indicating grid export, alongside positive values for consumption.

## **3\. Corporate Travel (Concur & Navan)**

**Format:** Nested JSON via REST APIs (e.g., Concur Itinerary v4 or Navan TMC API).  
**Structure:** Master booking arrays containing nested segments for flights (passengerInfo, segments).

### **Key Anomalies & Data Generation Rules**

* **No Explicit Distances:** Travel APIs do not calculate spatial distance. Flights only provide Origin and Destination as 3-letter IATA airport codes (e.g., Origin: SFO, Destination: JFK).  
* **Payload Schemas:**  
  * **Concur Itinerary v4:** Returns deeply nested JSON with a Bookings array. Inside, it uses objects like AirlineTickets, AirfareQuotes, and Segments. It relies on a ClientLocator to track the trip across external systems.7  
  * **Navan TMC API:** Focuses heavily on the lifecycle, requiring a bookingId. The payload includes service fees (serviceFee), the total amount, and passengerInfo arrays.8  
* **Cabin Classes:** Unstandardized string values for ticketing (e.g., "Y", "J", "Economy") that dictate emissions calculations.  
* **Data Mutability:** Travel bookings are highly mutable predictions. Ensure data reflects the lifecycle statuses (e.g., HOLD \-\> TICKETED \-\> CANCELED in Navan, or 0 \- Confirmed, 1 \- Ticketed, 2 \- Cancelled in Concur).7  
* **Traveler Identity Boundaries:** Payloads distinguish between corporate employees (containing an employeeId or corporate email) and guests (containing only firstName and lastName).8

#### **Works cited**

1. Mapping Required \- SAP Community, accessed May 25, 2026, [https://community.sap.com/t5/technology-q-a/mapping-required/qaq-p/7642582](https://community.sap.com/t5/technology-q-a/mapping-required/qaq-p/7642582)  
2. Receipt Confirmation Guidelines (IDoc) \- TraceLink, accessed May 25, 2026, [https://opus.tracelink.com/documentation/2026.1/en-US/api/prod-delivery-tracking/receipt\_confirmation/receipt\_confirmation\_idoc-guidelines.htm](https://opus.tracelink.com/documentation/2026.1/en-US/api/prod-delivery-tracking/receipt_confirmation/receipt_confirmation_idoc-guidelines.htm)  
3. Panel Capacity Calculator, accessed May 25, 2026, [https://panel.hea.com/](https://panel.hea.com/)  
4. mypi-home/Octopus-Bill-Parser: A Python tool to extract and analyze half-hourly energy ... \- GitHub, accessed May 25, 2026, [https://github.com/mypi-home/Octopus-Bill-Parser](https://github.com/mypi-home/Octopus-Bill-Parser)  
5. Download smart meter data from Octopus Energy (UK) \- GitHub, accessed May 25, 2026, [https://github.com/teeay-dev/octopus-energy](https://github.com/teeay-dev/octopus-energy)  
6. electricity.csv  
7. preview.developer.concur.com/src/api-reference/travel/itinerary-v4/v4.itinerary.md at main · SAP-docs/preview.developer.concur.com · GitHub, accessed May 25, 2026, [https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-reference/travel/itinerary-v4/v4.itinerary.md](https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-reference/travel/itinerary-v4/v4.itinerary.md)  
8. API Docs: How to set up the Navan TMC API Integration, accessed May 25, 2026, [https://app.navan.com/app/helpcenter/articles/travel/admin/other-integrations/navan-tmc-api-integration-documentation](https://app.navan.com/app/helpcenter/articles/travel/admin/other-integrations/navan-tmc-api-integration-documentation)