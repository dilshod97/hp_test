import os

from django.core.management.base import BaseCommand, CommandError

from exam.models import User


class Command(BaseCommand):
    help = "Superadmin yaratadi (yoki parolini yangilaydi)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("SUPERADMIN_USERNAME"))
        parser.add_argument("--password", default=os.environ.get("SUPERADMIN_PASSWORD"))

    def handle(self, *args, username=None, password=None, **opts):
        if not username or not password:
            raise CommandError("--username va --password kerak (yoki SUPERADMIN_USERNAME / SUPERADMIN_PASSWORD).")
        user, created = User.objects.get_or_create(username=username)
        user.role = User.Role.SUPERADMIN
        user.is_staff = user.is_superuser = user.is_active = True
        if created:
            user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Superadmin {'yaratildi' if created else 'mavjud'}: {username}"))
