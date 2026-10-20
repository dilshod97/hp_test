"""
Ўзбек тилидаги тестнинг рус вариантини яратади ва уни асосий тестга бириктиради.

    python manage.py make_ru_version <тест ID> --source "<манба 1>" [--source "<манба 2>"] --title "Финансовый аудитор — отбор"

Тузилма (блоклар, вақт, «ҳар номзодга N та» қоидалари, суҳбат саволлари) асосий тестдан олинади,
саволлар эса рус тилидаги бўлимлардан код бўйича олинади: МА → ФА, ТА → СА, С → С, Т1-01 → Т1-01.
Рус варианти нофаол яратилади — текшириб, кейин фаол қилинг.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exam.models import Block, BlockRule, Kind, Language, Question, QuestionBank, Test

CODE_MAP = {"МА": "ФА", "ТА": "СА"}
TEXT_RU = {
    "Мантиқий фикрлаш тести": "Тест логического мышления",
    "Ёзма амалий топшириқлар": "Письменные практические задания",
    "Иқтисод, молия, статистика": "Экономика, финансы, статистика",
    "ACCA бўйича тест": "Тест по ACCA",
    "Ҳар бир саволда битта тўғри жавобни белгиланг.": "В каждом вопросе отметьте один правильный ответ.",
    "Тест икки қисмдан иборат: мантиқий тест ва ёзма амалий топшириқлар. "
    "Интернет, сунъий интеллект, калькулятор ва ташқи ёрдамдан фойдаланиш мумкин эмас. "
    "Қоралама қоғозга рухсат берилади.":
        "Тест состоит из двух частей: логический тест и письменные практические задания. "
        "Пользоваться интернетом, искусственным интеллектом, калькулятором и посторонней помощью нельзя. "
        "Черновик разрешен.",
    "Ҳар бир топшириқни алоҳида бажаринг. Ҳисоб натижаси, ўлчов бирлиги ва фаразларингизни кўрсатинг. "
    "Матн, жадвал ёки рўйхат шаклида жавоб беришингиз мумкин. Қоралама қоғозга рухсат берилади.":
        "Выполняйте каждое задание отдельно. Указывайте результат расчета, единицы измерения и допущения. "
        "Отвечать можно текстом, таблицей или списком. Черновик разрешен.",
}


def ru_code(code):
    prefix, _, rest = code.partition(" ")
    return f"{CODE_MAP.get(prefix, prefix)} {rest}" if rest else code


class Command(BaseCommand):
    help = "Тестнинг рус тилидаги вариантини яратади (номзод киргач тилни танлайди)."

    def add_arguments(self, parser):
        parser.add_argument("test_id", type=int)
        parser.add_argument("--source", required=True, action="append",
                            help="Рус тилидаги бўлимларнинг манба номи (бир нечта бўлса, ҳар бирига --source)")
        parser.add_argument("--title", required=True)

    @transaction.atomic
    def handle(self, test_id, source, title, **opts):
        uz = Test.objects.filter(pk=test_id).first()
        if uz is None:
            raise CommandError("Тест топилмади.")
        if uz.ru_version_id:
            raise CommandError(f"Бу тестнинг рус варианти бор: {uz.ru_version}.")
        ru_banks = QuestionBank.objects.filter(source__in=source)
        missing = set(source) - set(ru_banks.values_list("source", flat=True))
        if missing:
            raise CommandError(f"Бу манбали бўлимлар топилмади: {', '.join(missing)}.")
        ru_questions = {q.code: q for q in Question.objects.filter(bank__in=ru_banks)}

        def twin(q):
            code = ru_code(q.code)
            if code not in ru_questions:
                raise CommandError(f"{q.code}: рус тилидаги «{code}» топилмади.")
            return ru_questions[code]

        def twin_bank(bank):
            sample = bank.questions.order_by("order").first()
            if sample is None:
                raise CommandError(f"«{bank.name}» бўлими бўш.")
            ru_bank = twin(sample).bank
            missing = [q.code for q in bank.questions.all() if ru_code(q.code) not in ru_questions]
            if missing:
                raise CommandError(f"«{bank.name}»: рус тилида йўқ саволлар: {', '.join(missing)}")
            return ru_bank

        ru = Test.objects.create(
            title=title, description=TEXT_RU.get(uz.description, uz.description), language=Language.RU,
            is_active=False, shuffle_questions=uz.shuffle_questions, shuffle_options=uz.shuffle_options,
            free_navigation=uz.free_navigation, require_photo=uz.require_photo, review_mode=uz.review_mode,
            weight_practical=uz.weight_practical, weight_logic=uz.weight_logic, weight_test=uz.weight_test,
            weight_interview=uz.weight_interview, weight_defense=uz.weight_defense, created_by=uz.created_by,
        )
        ru.checkers.set(uz.checkers.all())
        ru.interview_questions.set([twin(q) for q in uz.interview_questions.all()])
        for b in uz.blocks.all():
            description = b.description
            rules = list(b.rules.select_related("bank"))
            if b.kind == Kind.LOGIC and rules:
                description = twin_bank(rules[0].bank).description or description
            nb = Block.objects.create(
                test=ru, title=TEXT_RU.get(b.title, b.title), kind=b.kind,
                description=TEXT_RU.get(description, description), duration_minutes=b.duration_minutes,
                order=b.order, questions_per_candidate=b.questions_per_candidate,
            )
            for r in rules:
                rule = BlockRule.objects.create(block=nb, bank=twin_bank(r.bank), count=r.count)
                rule.sync_pool()
            for i, q in enumerate(b.questions.filter(rule=None).select_related("source"), start=1):
                twin(q.source or q).copy_to(block=nb, order=q.order or i)
            self.stdout.write(f"  {nb.title}: {nb.questions.count()} та савол, ҳар номзодга {nb.per_candidate}")
        uz.ru_version = ru
        uz.save(update_fields=["ru_version"])
        self.stdout.write(self.style.SUCCESS(
            f"Тайёр: «{ru.title}» (ID {ru.pk}, нофаол) → «{uz.title}» нинг рус варианти. Макс. балл: {ru.max_score}"))
