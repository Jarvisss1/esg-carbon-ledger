from django.db import migrations

def populate_airports(apps, schema_editor):
    Airport = apps.get_model('core_api', 'Airport')
    
    airports = [
        # India
        {'iata_code': 'DEL', 'latitude': 28.5665, 'longitude': 77.1031, 'city': 'Delhi', 'country': 'IN'},
        {'iata_code': 'BOM', 'latitude': 19.0896, 'longitude': 72.8656, 'city': 'Mumbai', 'country': 'IN'},
        {'iata_code': 'BLR', 'latitude': 13.1986, 'longitude': 77.7066, 'city': 'Bengaluru', 'country': 'IN'},
        {'iata_code': 'MAA', 'latitude': 12.9941, 'longitude': 80.1709, 'city': 'Chennai', 'country': 'IN'},
        {'iata_code': 'HYD', 'latitude': 17.2403, 'longitude': 78.4294, 'city': 'Hyderabad', 'country': 'IN'},
        {'iata_code': 'PNQ', 'latitude': 18.5793, 'longitude': 73.9089, 'city': 'Pune', 'country': 'IN'},
        {'iata_code': 'CCU', 'latitude': 22.6547, 'longitude': 88.4467, 'city': 'Kolkata', 'country': 'IN'},
        {'iata_code': 'AMD', 'latitude': 23.0770, 'longitude': 72.6347, 'city': 'Ahmedabad', 'country': 'IN'},
        
        # UK / Europe
        {'iata_code': 'LHR', 'latitude': 51.4775, 'longitude': -0.4614, 'city': 'London', 'country': 'GB'},
        {'iata_code': 'LGW', 'latitude': 51.1537, 'longitude': -0.1821, 'city': 'London Gatwick', 'country': 'GB'},
        {'iata_code': 'MAN', 'latitude': 53.3537, 'longitude': -2.2750, 'city': 'Manchester', 'country': 'GB'},
        {'iata_code': 'CDG', 'latitude': 49.0097, 'longitude': 2.5479, 'city': 'Paris', 'country': 'FR'},
        {'iata_code': 'AMS', 'latitude': 52.3086, 'longitude': 4.7639, 'city': 'Amsterdam', 'country': 'NL'},
        {'iata_code': 'FRA', 'latitude': 50.0379, 'longitude': 8.5622, 'city': 'Frankfurt', 'country': 'DE'},
        {'iata_code': 'MUC', 'latitude': 48.3538, 'longitude': 11.7861, 'city': 'Munich', 'country': 'DE'},
        {'iata_code': 'ZRH', 'latitude': 47.4647, 'longitude': 8.5492, 'city': 'Zurich', 'country': 'CH'},
        {'iata_code': 'MAD', 'latitude': 40.4839, 'longitude': -3.5680, 'city': 'Madrid', 'country': 'ES'},
        {'iata_code': 'FCO', 'latitude': 41.8003, 'longitude': 12.2389, 'city': 'Rome', 'country': 'IT'},
        
        # Middle East / Asia
        {'iata_code': 'DXB', 'latitude': 25.2532, 'longitude': 55.3657, 'city': 'Dubai', 'country': 'AE'},
        {'iata_code': 'DOH', 'latitude': 25.2609, 'longitude': 51.6138, 'city': 'Doha', 'country': 'QA'},
        {'iata_code': 'SIN', 'latitude': 1.3644, 'longitude': 103.9915, 'city': 'Singapore', 'country': 'SG'},
        {'iata_code': 'HKG', 'latitude': 22.3080, 'longitude': 113.9185, 'city': 'Hong Kong', 'country': 'HK'},
        {'iata_code': 'NRT', 'latitude': 35.7720, 'longitude': 140.3929, 'city': 'Tokyo Narita', 'country': 'JP'},
        {'iata_code': 'HND', 'latitude': 35.5494, 'longitude': 139.7798, 'city': 'Tokyo Haneda', 'country': 'JP'},
        {'iata_code': 'BKK', 'latitude': 13.6811, 'longitude': 100.7472, 'city': 'Bangkok', 'country': 'TH'},
        {'iata_code': 'ICN', 'latitude': 37.4602, 'longitude': 126.4407, 'city': 'Seoul', 'country': 'KR'},
        {'iata_code': 'KIX', 'latitude': 34.4347, 'longitude': 135.2442, 'city': 'Osaka', 'country': 'JP'},
        {'iata_code': 'KUL', 'latitude': 2.7456, 'longitude': 101.7099, 'city': 'Kuala Lumpur', 'country': 'MY'},
        {'iata_code': 'CGK', 'latitude': -6.1256, 'longitude': 106.6559, 'city': 'Jakarta', 'country': 'ID'},
        {'iata_code': 'TPE', 'latitude': 25.0797, 'longitude': 121.2342, 'city': 'Taipei', 'country': 'TW'},
        
        # Americas
        {'iata_code': 'JFK', 'latitude': 40.6413, 'longitude': -73.7781, 'city': 'New York', 'country': 'US'},
        {'iata_code': 'LAX', 'latitude': 33.9425, 'longitude': -118.4081, 'city': 'Los Angeles', 'country': 'US'},
        {'iata_code': 'ORD', 'latitude': 41.9742, 'longitude': -87.9073, 'city': 'Chicago', 'country': 'US'},
        {'iata_code': 'SFO', 'latitude': 37.6213, 'longitude': -122.3790, 'city': 'San Francisco', 'country': 'US'},
        {'iata_code': 'BOS', 'latitude': 42.3656, 'longitude': -71.0096, 'city': 'Boston', 'country': 'US'},
        {'iata_code': 'MIA', 'latitude': 25.7959, 'longitude': -80.2870, 'city': 'Miami', 'country': 'US'},
        {'iata_code': 'ATL', 'latitude': 33.6407, 'longitude': -84.4277, 'city': 'Atlanta', 'country': 'US'},
        {'iata_code': 'DFW', 'latitude': 32.8998, 'longitude': -97.0403, 'city': 'Dallas', 'country': 'US'},
        {'iata_code': 'DEN', 'latitude': 39.8561, 'longitude': -104.6737, 'city': 'Denver', 'country': 'US'},
        {'iata_code': 'YYZ', 'latitude': 43.6777, 'longitude': -79.6248, 'city': 'Toronto', 'country': 'CA'},
        {'iata_code': 'GRU', 'latitude': -23.4356, 'longitude': -46.4731, 'city': 'Sao Paulo', 'country': 'BR'},
        
        # Oceania / Africa
        {'iata_code': 'SYD', 'latitude': -33.9461, 'longitude': 151.1772, 'city': 'Sydney', 'country': 'AU'},
        {'iata_code': 'MEL', 'latitude': -37.6690, 'longitude': 144.8410, 'city': 'Melbourne', 'country': 'AU'},
        {'iata_code': 'AKL', 'latitude': -37.0081, 'longitude': 174.7917, 'city': 'Auckland', 'country': 'NZ'},
        {'iata_code': 'CPT', 'latitude': -33.9715, 'longitude': 18.6021, 'city': 'Cape Town', 'country': 'ZA'},
        {'iata_code': 'JNB', 'latitude': -26.1367, 'longitude': 28.2460, 'city': 'Johannesburg', 'country': 'ZA'},
    ]
    
    for ap in airports:
        Airport.objects.update_or_create(
            iata_code=ap['iata_code'],
            defaults={
                'latitude': ap['latitude'],
                'longitude': ap['longitude'],
                'city': ap['city'],
                'country': ap['country']
            }
        )

def rollback_airports(apps, schema_editor):
    Airport = apps.get_model('core_api', 'Airport')
    codes = [
        'BLR', 'MAA', 'HYD', 'PNQ', 'CCU', 'AMD', 'LGW', 'MAN', 'CDG', 'AMS', 'FRA', 'MUC', 
        'ZRH', 'MAD', 'FCO', 'DXB', 'DOH', 'HKG', 'NRT', 'HND', 'BKK', 'ICN', 'KIX', 'KUL', 
        'CGK', 'TPE', 'LAX', 'ORD', 'BOS', 'MIA', 'ATL', 'DFW', 'DEN', 'YYZ', 'GRU', 'SYD', 
        'MEL', 'AKL', 'CPT', 'JNB'
    ]
    Airport.objects.filter(iata_code__in=codes).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('core_api', '0003_auditlog_performed_by_and_more'),
    ]
    operations = [
        migrations.RunPython(populate_airports, rollback_airports),
    ]
