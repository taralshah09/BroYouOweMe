from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    username = models.CharField(max_length=32, unique=True, validators=[UnicodeUsernameValidator()])
    email = models.EmailField(unique=True)
    first_name = None
    last_name = None
    date_joined = None
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="users_username_ci_unique"),
            models.UniqueConstraint(Lower("email"), name="users_email_ci_unique"),
        ]
