from django.db import connection


def check_database():
    """Check connectivity without requiring any application tables."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)
