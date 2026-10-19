"""
Танлов материаллари (.docx) ни саволлар базасига юклайди.

    python manage.py import_tanlov /path/to/file.docx [--source "Ҳужжат номи"] [--no-tests]

Формат ва қоидалар: exam/importer.py. Худди шу ишни веб-саҳифада ҳам қилиш мумкин:
«Саволлар базаси» → «Ҳужжатдан юклаш».
"""
from django.core.management.base import BaseCommand, CommandError

from exam.importer import import_parsed, parse, use_keys_from
from exam.models import User


class Command(BaseCommand):
    help = "Танлов материаллари .docx файлидан саволлар базаси ва намуна тестларни яратади."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--source", help="Манба номи (стандарт: ҳужжат сарлавҳаси)")
        parser.add_argument("--no-tests", action="store_true", help="Намуна тестларсиз")
        parser.add_argument("--author", help="Тестлар муаллифи (логин). Стандарт: биринчи суперадмин")
        parser.add_argument("--keys-from", help="Мантиқий тест калитларини шу (асл) ҳужжатдан олиш")

    def handle(self, path, source=None, no_tests=False, author=None, keys_from=None, **opts):
        parsed = parse(path)
        if keys_from:
            parsed = use_keys_from(parsed, parse(keys_from))
        if parsed.errors:
            raise CommandError("Ҳужжатда хатолар бор:\n  " + "\n  ".join(parsed.errors))
        user = (User.objects.filter(username=author).first() if author
                else User.objects.filter(role=User.Role.SUPERADMIN).order_by("pk").first())
        report = import_parsed(parsed, source or parsed.title or "Ҳужжат", user=user, create_tests=not no_tests)
        if opts.get("verbosity", 1):
            for w in parsed.warnings:
                self.stdout.write(self.style.WARNING(w))
            for b in report["banks"]:
                self.stdout.write(f"  {b['name']} ({b['kind']}): {b['count']} та савол")
            self.stdout.write(self.style.SUCCESS(
                f"Тайёр: {report['created']} та янги, {report['updated']} та янгиланган савол."))
            for t in report["tests"]:
                self.stdout.write(self.style.SUCCESS(f"Намуна тест яратилди (нофаол): {t}"))
