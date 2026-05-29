# **ESG Carbon Ledger & Data Normalization Platform**

An enterprise-grade environmental, social, and governance (ESG) data ingestion and carbon accounting platform. The system acquires, auto-detects, parses, and normalizes telemetry data representing Scope 1 (Direct Fuel), Scope 2 (Grid Electricity), and Scope 3 (Travel & Procurement) emissions into unified **kgCO2e** values strictly mapped to DEFRA 2023 guidelines.

---

## **1. Setup Guide**

### **A. Backend Setup (Django)**
```bash
# Navigate to project directory
cd esg_project

# Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Start the development server (runs on http://127.0.0.1:8000)
python manage.py runserver
```

### **B. Frontend Setup (React + Vite)**
```bash
# Navigate to frontend directory
cd esg_frontend

# Install dependencies
npm install

# Start the local development server (runs on http://localhost:5173)
npm run dev
```

---

## **2. How to Use the Platform**

### **Step 1: Dynamic Workspace Login**
Our system routes users dynamically to isolated organization sandboxes depending on their email domain suffix during registration:
* **Public Domains** (e.g., `user@gmail.com`, `user@yahoo.com`): Automatically logged into the shared seeded **`Tata Motors`** development workspace.
* **Corporate Domains** (e.g., `auditor@kpmg.com`): Automatically provisions and locks the user into a completely isolated, private tenant sandbox (e.g., **`KPMG`** workspace) to prevent any data exposure.

### **Step 2: Ingesting Telemetry Data**
1. Open the web UI at `http://localhost:5173`.
2. Navigate to the **Upload Data** tab.
3. Choose a data source category: **SAP ERP (Scope 1/3)**, **Utility Portals (Scope 2)**, or **Corporate Travel TMC (Scope 3)**.
4. Select a sample file from the `sample_data/` directory and upload it.
5. Ingestion happens asynchronously via our in-memory queue. The system auto-detects formats and returns standard calculation records immediately.

---

## **3. Using the Sample Data (`sample_data/`)**

We provide pre-validated raw telemetry files in the [sample_data/](file:///c:/PROJECTSSS/esg/sample_data/) directory to demonstrate the ingestion parser capabilities:

### **A. SAP ERP (`sample_data/sap/`)**
For direct combustion fuel logs and purchase records:
* `sap_fuel_consumption.xlsx` — Excel fuel sheet with transactional postings.
* `sap_material_document_odata.json` — Deep OData JSON payload representing material documents.
* `sap_mbgmcr03_idoc.xml` — Legacy XML IDoc containing goods receipt line items.
* `sap_procurement.csv` / `.idoc` — German-nomenclature spreadsheets utilizing traditional movement tags (`101`, `241`, `313`).

### **B. Utility Portals (`sample_data/utility/`)**
For Scope 2 electricity smart-meter files:
* `utility_electricity_IN.csv` — Time-series intervals mapped to the Indian grid carbon coefficients.
* `utility_electricity_UK.csv` — Smart-meter interval recordings utilizing the UK grid coefficients.

### **C. Corporate Travel TMC (`sample_data/travel/`)**
For Scope 3 air travel, flight hubs, and hotel logs:
* `travel_concur_itinerary_v4.json` — Concur REST JSON payload detailing flight itineraries.
* `travel_navan_tmc.json` — Deep TMC travel JSON detailing active trip segments.
* `travel_corporate.csv` — Flat spreadsheet tracking flight corridors via 3-letter IATA codes.
