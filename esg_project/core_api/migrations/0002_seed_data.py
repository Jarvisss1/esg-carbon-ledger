from django.db import migrations

def seed_data(apps, schema_editor):
    Tenant = apps.get_model('core_api', 'Tenant')
    Airport = apps.get_model('core_api', 'Airport')

    # Seed default Tenant (Tata Motors)
    tenant, _ = Tenant.objects.get_or_create(
        id='7aa7f899-25de-4db6-a3e6-932e12ec76e1',
        defaults={'name': 'Tata Motors'}
    )

    # Seed Airport standard mock lookups
    airports = [
        {'iata_code': 'DEL', 'latitude': 28.556200, 'longitude': 77.100000, 'city': 'Delhi', 'country': 'IN'},
        {'iata_code': 'BOM', 'latitude': 19.089600, 'longitude': 72.865600, 'city': 'Mumbai', 'country': 'IN'},
        {'iata_code': 'LHR', 'latitude': 51.470000, 'longitude': -0.454300, 'city': 'London', 'country': 'GB'},
        {'iata_code': 'SFO', 'latitude': 37.621300, 'longitude': -122.379000, 'city': 'San Francisco', 'country': 'US'},
        {'iata_code': 'JFK', 'latitude': 40.641300, 'longitude': -73.778100, 'city': 'New York', 'country': 'US'},
        {'iata_code': 'SIN', 'latitude': 1.364400, 'longitude': 103.991500, 'city': 'Singapore', 'country': 'SG'},
    ]

    for ap in airports:
        Airport.objects.get_or_create(
            iata_code=ap['iata_code'],
            defaults={
                'latitude': ap['latitude'],
                'longitude': ap['longitude'],
                'city': ap['city'],
                'country': ap['country']
            }
        )

def rollback_data(apps, schema_editor):
    Tenant = apps.get_model('core_api', 'Tenant')
    Airport = apps.get_model('core_api', 'Airport')

    Tenant.objects.filter(id='7aa7f899-25de-4db6-a3e6-932e12ec76e1').delete()
    Airport.objects.filter(iata_code__in=['DEL', 'BOM', 'LHR', 'SFO', 'JFK', 'SIN']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('core_api', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_data, rollback_data),
    ]
