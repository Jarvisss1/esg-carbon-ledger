"""
Corporate Travel Data Simulator — Concur/Navan Export Style
Simulates what a travel manager exports from Concur Expense or Navan
after a monthly expense cycle closes.

Three record types in one file (as Concur exports them — all rows mixed):
  - AIR    : flight segments
  - HOTEL  : hotel stays
  - GROUND : taxi, car hire, metro, rail

Key realism: distance_km is INTENTIONALLY OMITTED for all flight rows.
Your normalizer must derive it from IATA codes using haversine.

Realistic dirt injected:
  - No distance_km for flights (must be derived)
  - Airport codes that are not IATA (typos: "DEL1", "LHRx")
  - Multiple legs of same trip booked as separate rows (LHR→DXB→BOM)
  - Duplicate trip_id (amended booking rebilled in same export cycle)
  - Missing currency on 3 rows (analyst forgot to set before submitting)
  - Hotel with no check-in date (booked via third party, merged late)
  - Business class on a 45-minute hop (BOM→PNQ) — suspicious emission spike
  - Ground transport with distance=0 (flat rate taxi, distance unknown)
  - Mixed date formats: YYYY-MM-DD, MM/DD/YYYY, DD-Mon-YYYY
  - Amount in wrong currency (INR trip submitted in USD by mistake)
  - One row with departure == arrival (data entry error)
  - Per diem rows mixed in (not travel, should be filtered)
  - Negative amount (expense reversal / refund)
  - Long-haul flight with economy AND business in same trip (split billing)
"""

import csv
import random
import math
from datetime import date, timedelta
from itertools import count

random.seed(99)

# ── airport lookup ─────────────────────────────────────────────────────────────
# (IATA code → lat, lon, city, country)
# A subset of real airports. Your normalizer embeds the full ~500-airport table.

AIRPORTS = {
    # India
    "DEL": (28.5665, 77.1031, "Delhi", "IN"),
    "BOM": (19.0896, 72.8656, "Mumbai", "IN"),
    "BLR": (13.1986, 77.7066, "Bengaluru", "IN"),
    "MAA": (12.9941, 80.1709, "Chennai", "IN"),
    "HYD": (17.2403, 78.4294, "Hyderabad", "IN"),
    "PNQ": (18.5793, 73.9089, "Pune", "IN"),
    "CCU": (22.6547, 88.4467, "Kolkata", "IN"),
    "AMD": (23.0770, 72.6347, "Ahmedabad", "IN"),
    # UK / Europe
    "LHR": (51.4775, -0.4614, "London", "GB"),
    "LGW": (51.1537, -0.1821, "London Gatwick", "GB"),
    "MAN": (53.3537, -2.2750, "Manchester", "GB"),
    "CDG": (49.0097,  2.5479, "Paris", "FR"),
    "AMS": (52.3086,  4.7639, "Amsterdam", "NL"),
    "FRA": (50.0379,  8.5622, "Frankfurt", "DE"),
    "MUC": (48.3538, 11.7861, "Munich", "DE"),
    "ZRH": (47.4647,  8.5492, "Zurich", "CH"),
    # Middle East / Asia
    "DXB": (25.2532, 55.3657, "Dubai", "AE"),
    "DOH": (25.2609, 51.6138, "Doha", "QA"),
    "SIN": (1.3644,  103.9915, "Singapore", "SG"),
    "HKG": (22.3080, 113.9185, "Hong Kong", "HK"),
    "NRT": (35.7720, 140.3929, "Tokyo", "JP"),
    "BKK": (13.6811, 100.7472, "Bangkok", "TH"),
    # Americas
    "JFK": (40.6413, -73.7781, "New York", "US"),
    "LAX": (33.9425, -118.4081, "Los Angeles", "US"),
    "ORD": (41.9742, -87.9073, "Chicago", "US"),
    "SFO": (37.6213, -122.3790, "San Francisco", "US"),
    "YYZ": (43.6777, -79.6248, "Toronto", "CA"),
    "GRU": (-23.4356, -46.4731, "São Paulo", "BR"),
}

def haversine_km(code1, code2):
    """Great-circle distance between two airport codes."""
    if code1 not in AIRPORTS or code2 not in AIRPORTS:
        return None
    lat1, lon1 = math.radians(AIRPORTS[code1][0]), math.radians(AIRPORTS[code1][1])
    lat2, lon2 = math.radians(AIRPORTS[code2][0]), math.radians(AIRPORTS[code2][1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return round(6371 * 2 * math.asin(math.sqrt(a)), 1)

CABIN_CLASSES = ["Economy", "PremiumEconomy", "Business", "First"]
CABIN_MULTIPLIER = {"Economy": 1.0, "PremiumEconomy": 1.5, "Business": 2.0, "First": 3.0}

GROUND_TYPES = ["Taxi", "Uber/Ola", "Company Car", "Metro", "Rail", "Car Hire", "Bus"]

HOTEL_CHAINS = [
    "Marriott", "Hilton", "IHG", "Hyatt", "Taj Hotels",
    "Oberoi", "The Leela", "Novotel", "Ibis", "Premier Inn",
]

CURRENCIES = ["USD", "GBP", "EUR", "INR", "SGD", "AED"]

TRAVELLERS = [
    {"id": "EMP-001", "name": "Priya Sharma",    "dept": "Sales"},
    {"id": "EMP-002", "name": "James Whitfield",  "dept": "Engineering"},
    {"id": "EMP-003", "name": "Anjali Mehta",     "dept": "Finance"},
    {"id": "EMP-004", "name": "Carlos Reyes",     "dept": "Operations"},
    {"id": "EMP-005", "name": "Liu Wei",          "dept": "Product"},
    {"id": "EMP-006", "name": "Sarah O'Brien",    "dept": "Legal"},
]

# ── date formatting dirt ────────────────────────────────────────────────────────

MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def dirty_date(d):
    """Format date in one of three formats Concur exports use."""
    fmt = random.choice(["iso", "us", "named"])
    if fmt == "iso":
        return d.isoformat()                            # 2025-04-15
    elif fmt == "us":
        return d.strftime("%m/%d/%Y")                   # 04/15/2025
    else:
        return f"{d.day:02d}-{MONTH_ABBR[d.month-1]}-{d.year}"  # 15-Apr-2025

# ── trip builder ───────────────────────────────────────────────────────────────

trip_counter = count(1001)

FIELDNAMES = [
    "trip_id", "expense_type", "traveller_id", "traveller_name", "department",
    "booking_date", "travel_date", "departure_airport", "arrival_airport",
    "cabin_class", "airline", "flight_number",
    "distance_km",        # intentionally blank for flights
    "hotel_name", "hotel_city", "hotel_country", "checkin_date", "checkout_date", "nights",
    "ground_transport_type", "ground_distance_km",
    "amount", "currency", "notes", "status"
]

AIRLINES = ["IndiGo", "Air India", "British Airways", "Emirates", "Singapore Airlines",
            "Lufthansa", "United", "Delta", "Qatar Airways", "Vistara"]

def blank_row():
    return {f: "" for f in FIELDNAMES}

def make_flight_row(trip_id, traveller, dep, arr, travel_date, cabin, dirty_level):
    row = blank_row()
    row["trip_id"] = trip_id
    row["expense_type"] = "AIR"
    row["traveller_id"] = traveller["id"]
    row["traveller_name"] = traveller["name"]
    row["department"] = traveller["dept"]
    row["booking_date"] = dirty_date(travel_date - timedelta(days=random.randint(7, 45)))
    row["travel_date"] = dirty_date(travel_date)
    row["departure_airport"] = dep
    row["arrival_airport"] = arr
    row["cabin_class"] = cabin
    row["airline"] = random.choice(AIRLINES)
    row["flight_number"] = f"{random.choice(['AI','6E','BA','EK','SQ'])}{random.randint(100,999)}"
    row["distance_km"] = ""      # ← intentionally blank — normalizer must derive
    dist = haversine_km(dep, arr)
    base_fare = (dist or 1000) * random.uniform(0.08, 0.22) * CABIN_MULTIPLIER[cabin]
    row["amount"] = round(base_fare + random.uniform(-50, 100), 2)
    row["currency"] = "INR" if AIRPORTS.get(dep, ("","","","IN"))[3] == "IN" else \
                      random.choice(["USD", "GBP", "EUR"])
    row["status"] = "Approved"

    # inject dirt
    if dirty_level < 0.04:
        row["departure_airport"] = dep + str(random.randint(1,9))  # typo: "DEL1"
    elif dirty_level < 0.06:
        row["currency"] = ""                                         # missing currency
    elif dirty_level < 0.08:
        row["arrival_airport"] = dep                                 # dep == arr (error)
    elif dirty_level < 0.10:
        row["amount"] = -row["amount"]                               # refund/reversal
    elif dirty_level < 0.12:
        row["notes"] = "Per diem"                                    # should be filtered
        row["expense_type"] = "PERDIEM"

    return row

def make_hotel_row(trip_id, traveller, city_airport, checkin, nights, dirty_level):
    airport_info = AIRPORTS.get(city_airport, (0,0,"Unknown","??"))
    city = airport_info[2]
    country = airport_info[3]
    checkout = checkin + timedelta(days=nights)

    row = blank_row()
    row["trip_id"] = trip_id
    row["expense_type"] = "HOTEL"
    row["traveller_id"] = traveller["id"]
    row["traveller_name"] = traveller["name"]
    row["department"] = traveller["dept"]
    row["booking_date"] = dirty_date(checkin - timedelta(days=random.randint(3, 30)))
    row["hotel_name"] = random.choice(HOTEL_CHAINS)
    row["hotel_city"] = city
    row["hotel_country"] = country
    row["checkin_date"] = dirty_date(checkin)
    row["checkout_date"] = dirty_date(checkout)
    row["nights"] = nights
    nightly_rate = random.uniform(80, 350)
    row["amount"] = round(nightly_rate * nights, 2)
    row["currency"] = "INR" if country == "IN" else random.choice(["USD", "GBP", "EUR"])
    row["status"] = "Approved"

    if dirty_level < 0.05:
        row["checkin_date"] = ""           # booked via third party, missing date
    elif dirty_level < 0.08:
        row["nights"] = 0                  # one-night stay logged as 0 (check-in = checkout)
    elif dirty_level < 0.10:
        row["currency"] = "USD"            # INR trip submitted in USD by mistake
        row["notes"] = "Currency may be incorrect — submitted via personal card"

    return row

def make_ground_row(trip_id, traveller, city_airport, travel_date, dirty_level):
    g_type = random.choice(GROUND_TYPES)
    g_dist = round(random.uniform(5, 80), 1) if g_type != "Metro" else 0

    row = blank_row()
    row["trip_id"] = trip_id
    row["expense_type"] = "GROUND"
    row["traveller_id"] = traveller["id"]
    row["traveller_name"] = traveller["name"]
    row["department"] = traveller["dept"]
    row["booking_date"] = dirty_date(travel_date)
    row["travel_date"] = dirty_date(travel_date)
    row["ground_transport_type"] = g_type
    row["ground_distance_km"] = g_dist if g_type != "Taxi" else 0  # taxi = flat rate, no dist
    row["amount"] = round(random.uniform(8, 200), 2)
    row["currency"] = "INR" if AIRPORTS.get(city_airport, (0,0,"","IN"))[3] == "IN" else \
                      random.choice(["USD", "GBP", "EUR"])
    row["status"] = "Approved"

    if dirty_level < 0.06:
        row["currency"] = ""
    return row

# ── generate full export ───────────────────────────────────────────────────────

def generate_travel_csv(path, n_trips=60):
    all_rows = []
    airport_list = list(AIRPORTS.keys())

    for _ in range(n_trips):
        trip_id = f"TRIP-{next(trip_counter):04d}"
        traveller = random.choice(TRAVELLERS)
        travel_date = date(2024, 1, 1) + timedelta(days=random.randint(0, 365))

        # pick a route
        dep = random.choice(airport_list)
        arr = random.choice([a for a in airport_list if a != dep])
        cabin = random.choices(
            CABIN_CLASSES,
            weights=[55, 15, 25, 5]   # economy most common
        )[0]

        dirty = random.random()

        # outbound flight
        all_rows.append(make_flight_row(trip_id, traveller, dep, arr, travel_date, cabin, dirty))

        # multi-leg: 30% of trips have a connecting flight
        if random.random() < 0.30:
            mid = random.choice([a for a in airport_list if a not in (dep, arr)])
            # first leg
            all_rows[-1]["arrival_airport"] = mid
            all_rows[-1]["notes"] = "Leg 1 of 2"
            # second leg
            leg2 = make_flight_row(trip_id, traveller, mid, arr,
                                   travel_date + timedelta(hours=3), cabin, random.random())
            leg2["notes"] = "Leg 2 of 2"
            all_rows.append(leg2)

        # hotel (70% of trips)
        nights = random.randint(1, 7)
        if random.random() < 0.70:
            all_rows.append(make_hotel_row(trip_id, traveller, arr,
                                           travel_date, nights, random.random()))

        # ground transport (80% of trips — at least one)
        for _ in range(random.randint(1, 3)):
            all_rows.append(make_ground_row(trip_id, traveller, arr,
                                            travel_date + timedelta(days=random.randint(0, nights)),
                                            random.random()))

        # suspicious: business class on short hop BOM→PNQ
        if random.random() < 0.08:
            short_trip_id = f"TRIP-{next(trip_counter):04d}"
            all_rows.append(make_flight_row(
                short_trip_id, traveller, "BOM", "PNQ",
                travel_date, "Business", 0.99   # 0.99 = no additional dirt
            ))
            all_rows[-1]["notes"] = "45-min hop — business class flagged for review"

    # inject duplicate trip_id (amended booking — same id, different amount)
    dup_source = random.choice([r for r in all_rows if r["expense_type"] == "AIR"])
    dup = dict(dup_source)
    dup["amount"] = round(float(dup["amount"] or 0) * 1.08, 2)
    dup["notes"] = "Amended booking — fare difference"
    all_rows.append(dup)

    # inject per-diem rows (should be filtered during normalization)
    for emp in random.sample(TRAVELLERS, 3):
        row = blank_row()
        row["trip_id"] = f"TRIP-{next(trip_counter):04d}"
        row["expense_type"] = "PERDIEM"
        row["traveller_id"] = emp["id"]
        row["traveller_name"] = emp["name"]
        row["amount"] = round(random.uniform(40, 75), 2)
        row["currency"] = "USD"
        row["travel_date"] = dirty_date(date(2024, random.randint(1,12), random.randint(1,28)))
        row["notes"] = "Per diem allowance — not a travel emission"
        all_rows.append(row)

    random.shuffle(all_rows)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(all_rows)

    air_count = sum(1 for r in all_rows if r["expense_type"] == "AIR")
    hotel_count = sum(1 for r in all_rows if r["expense_type"] == "HOTEL")
    ground_count = sum(1 for r in all_rows if r["expense_type"] == "GROUND")
    other_count = len(all_rows) - air_count - hotel_count - ground_count
    print(f"[Travel] Concur-style CSV -> {path}")
    print(f"         {len(all_rows)} rows: {air_count} air | {hotel_count} hotel | {ground_count} ground | {other_count} other/dirty")


if __name__ == "__main__":
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(base_dir, "sample_data", "travel")
    os.makedirs(out, exist_ok=True)
    generate_travel_csv(os.path.join(out, "travel_corporate.csv"))
    print("\nTravel sample data generated.")
    print("\nAirport distance examples (derived by haversine — not in the file):")
    for dep, arr in [("DEL","LHR"), ("BOM","SIN"), ("BOM","PNQ"), ("LHR","JFK")]:
        print(f"  {dep}->{arr}: {haversine_km(dep,arr)} km")
