"""
Барча танлов маълумотларини ўчиради: натижалар, номзодлар, тестлар ва саволлар базаси.
Фойдаланувчилар (суперадмин, тест тузувчи, экспертлар, HR) сақланади.

    python manage.py reset_tanlov --yes-delete-everything

Аввал албатта захира нусха олинг (pg_dump).
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exam.models import Assignment, Attempt, Candidate, QuestionBank, Test


class Command(BaseCommand):
    help = "Натижалар, номзодлар, тестлар ва саволлар базасини ўчиради (фойдаланувчилар қолади)."

    def add_arguments(self, parser):
        parser.add_argument("--yes-delete-everything", action="store_true")

    def handle(self, yes_delete_everything=False, **opts):
        if not yes_delete_everything:
            raise CommandError("Тасдиқлаш учун --yes-delete-everything беринг (аввал захира нусха олинг).")
        counts = {
            "натижа": Attempt.objects.count(), "номзод рўйхати": Assignment.objects.count(),
            "номзод": Candidate.objects.count(), "тест": Test.objects.count(), "бўлим": QuestionBank.objects.count(),
        }
        with transaction.atomic():
            for attempt in Attempt.objects.all():
                attempt.delete()          # жавоблар, баҳолар ва расм файли билан
            Assignment.objects.all().delete()
            Candidate.objects.all().delete()
            Test.objects.all().delete()   # блоклар, манбалар ва тест саволлари билан
            QuestionBank.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Ўчирилди: " + ", ".join(f"{v} та {k}" for k, v in counts.items())))
