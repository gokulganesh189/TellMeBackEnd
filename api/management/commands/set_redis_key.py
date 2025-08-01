from django.core.management.base import BaseCommand
import redis
from django.db import connection
from phpserialize import serialize

from TellMe.settings import get_secret





class Command(BaseCommand):
    """
    This is a custom command created to set up the redis key from the table vendor_config
    cmd to use to set up  - python manage.py set_redis_key
    """
    help = 'Set multiple Redis keys'

    def handle(self, *args, **options):
        redis_host = get_secret('REDIS_HOST')  # Redis host address
        redis_port = get_secret('REDIS_PORT')  # Redis port number
        redis_db = get_secret('REDIS_DB_6')
        key_value_pairs = []

        # Execute raw SQL query to fetch data from the table
        query = "SELECT tag, config_detail FROM TellMe.external_vendor_config"
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        for row in rows:
            key = row[0]
            value =serialize(row[1])
            key_value_pairs.append((key, value))

        redis_con = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

        for key, value in key_value_pairs:
            key1=f"VENDOR_CONFIG_{key}"
            redis_con.set(key1, value)
            self.stdout.write(self.style.SUCCESS(f'Redis key "{key}" set successfully.'))

        self.stdout.write(self.style.SUCCESS('All Redis keys set successfully.'))
