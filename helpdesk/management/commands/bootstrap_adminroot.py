import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the dedicated Django Admin superuser from environment configuration"

    def handle(self, *args, **kwargs):
        username = "adminroot"
        password = os.environ.get("ADMINROOT_PASSWORD", "")
        if len(password) < 16:
            raise CommandError("Set ADMINROOT_PASSWORD to a random password of at least 16 characters")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if not user.is_staff or not user.is_superuser or not user.is_active:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save(update_fields=["is_staff", "is_superuser", "is_active"])
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS("Django Admin account adminroot is ready"))
