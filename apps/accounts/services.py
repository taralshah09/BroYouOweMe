from django.db import connection


def check_database():
    """Check connectivity without requiring any application tables."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)



def register_user(form):
    """Keep password hashing and account creation behind the service layer."""
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction

    try:
        with transaction.atomic():
            return form.save()
    except IntegrityError:
        raise ValidationError("Username or email is already registered.") from None
