import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = "Create demo staff account from explicitly configured environment"

    def handle(self, *args, **kwargs):
        username = os.environ.get("OPERATOR_USERNAME", "").strip()
        password = os.environ.get("OPERATOR_PASSWORD", "")
        if not username or len(password) < 12:
            raise CommandError("Set OPERATOR_USERNAME and OPERATOR_PASSWORD (12+ chars)")
        user, created = get_user_model().objects.get_or_create(username=username, defaults={"is_staff": True})
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS("Operator account ready"))
