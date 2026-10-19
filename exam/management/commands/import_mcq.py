"""
Вариантли тест (тўғри жавоби сариқ билан белгиланган) .docx файлини «Касбий тест» бўлимига юклайди.

    python manage.py import_mcq файл.docx --bank "Иқтисод, молия, статистика" --prefix ИМС1 [--source "Касбий тестлар"]

Бир бўлимга бир нечта файл юкланса, ҳар бирига ўз --prefix берилади (саволлар коди: ИМС1-001, ...).
Рус варианти учун худди шу prefix ва бошқа --source ишлатилади — шунда make_ru_version саволларни код бўйича топади.
"""
from django.core.management.base import BaseCommand, CommandError

from exam.mcq_importer import import_mcq, parse_mcq


class Command(BaseCommand):
    help = "Вариантли тест ҳужжатини (тўғри жавоб сариқ рангда) саволлар базасига юклайди."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--bank", required=True, help="Бўлим номи")
        parser.add_argument("--prefix", required=True, help="Савол кодлари учун префикс (масалан ACCA)")
        parser.add_argument("--source", default="Касбий тестлар", help="Манба (тил бўйича ажратиш учун)")
        parser.add_argument("--dry-run", action="store_true", help="Фақат текшириш, базага ёзмаслик")

    def handle(self, path, bank, prefix, source, dry_run=False, **opts):
        parsed = parse_mcq(path)
        if parsed.errors:
            raise CommandError("Ҳужжатда хатолар бор:\n  " + "\n  ".join(parsed.errors))
        self.stdout.write(f"{len(parsed.items)} та савол топилди (ҳар бирида битта тўғри жавоб).")
        if dry_run:
            return
        r = import_mcq(parsed, bank_name=bank, source=source, prefix=prefix)
        self.stdout.write(self.style.SUCCESS(
            f"«{r['bank'].name}»: {r['created']} та янги, {r['updated']} та янгиланган. "
            f"Бўлимда жами {r['bank'].questions.count()} та савол."))
