"""
"Ҳисоб палатаси вакант лавозимларига танлов материаллари" .docx faylini import qiladi.

    python manage.py import_tanlov /path/to/file.docx [--no-tests]

Yaratiladi:
  * Banklar: МА 01–50, ТА 01–50 (har biri 5 mezon × 2 ball), 5 ta mantiqiy test to'plami
    (har biri 20 savol, kalit va izoh bilan), suhbat savollari (umumiy / auditor / tahlilchi).
  * Ikki namuna test (nofaol): "Молиявий аудитор" va "Тизимли таҳлилчи" —
    mantiqiy test 40 daqiqa + 6 ta amaliy topshiriq 180 daqiqa, 5 ta suhbat savoli.

Qayta ishga tushirilsa, bank savollari kod bo'yicha yangilanadi (testlardagi nusxalarga ta'sir qilmaydi,
suhbat savollari va ularning ballari saqlanib qoladi). Mavjud namuna testlar qayta yaratilmaydi.
"""
import re
from html import escape

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exam.models import Block, Kind, Question, QuestionBank, Test, User

LETTERS = "АБВГД"
CRITERION_RE = re.compile(r"^(\d)\.\s+(.*?)\s+(\d+)\s+балл$")
TASK_RE = re.compile(r"^(МА|ТА|С)\s+(\d{2})\s+(.*)$")
QUESTION_RE = re.compile(r"^(\d{1,2})\.\s+(.*)$")
OPTION_SPLIT_RE = re.compile(r"(?:^|\s{2,}|\t)([АБВГД])\)\s*")
SET_RE = re.compile(r"^(\d)\s+тўплам$")
KEY_RE = re.compile(r"^(\d)\s+тўплам калити$")

# Hujjatdagi tavsiya: auditor bileti — hisob-kitob, dalil va tanlanma, nazorat, xulosa, tavsiya;
# tahlilchi bileti — talablar, ma'lumotlar, integratsiya, nazorat va sinovlar.
SAMPLE_TESTS = [
    {
        "title": "Молиявий аудитор — танлов (намуна билет)",
        "logic_set": 1,
        "tasks": ["МА 01", "МА 05", "МА 21", "МА 30", "МА 38", "МА 46"],
        "interview": ["С 01", "С 02", "С 03", "С 13", "С 14"],
    },
    {
        "title": "Тизимли таҳлилчи — танлов (намуна билет)",
        "logic_set": 2,
        "tasks": ["ТА 01", "ТА 11", "ТА 20", "ТА 22", "ТА 36", "ТА 42"],
        "interview": ["С 01", "С 02", "С 03", "С 17", "С 18"],
    },
]

PRACTICAL_INSTRUCTION = (
    "Ҳар бир топшириқни алоҳида бажаринг. Ҳисоб натижаси, ўлчов бирлиги ва фаразларингизни кўрсатинг. "
    "Матн, жадвал ёки рўйхат шаклида жавоб беришингиз мумкин. Қоралама қоғозга рухсат берилади. "
    "Вақт тугаганда жавоблар автоматик сақланади."
)


def iter_blocks(document):
    """Hujjatni (tur, uslub, matn | jadval qatorlari) ketma-ketligiga aylantiradi."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = p.text.strip()
            if text:
                yield "p", (p.style.name if p.style is not None else ""), text
        elif tag == "tbl":
            t = Table(child, document)
            yield "table", "", [[c.text.strip() for c in row.cells] for row in t.rows]


def html_paragraphs(lines):
    return "".join(f"<p>{escape(line)}</p>" for line in lines)


def parse(path):
    import docx

    doc = docx.Document(path)
    data = {"МА": [], "ТА": [], "С": [], "sets": {}, "keys": {}, "logic_instruction": "", "intros": {}}
    section = None       # "МА", "ТА", "logic", "С", "keys", None
    current = None       # joriy topshiriq/savol
    current_set = None
    current_key = None

    for kind, style, payload in iter_blocks(doc):
        if kind == "table":
            if section == "keys" and current_key:
                rows = payload[1:]
                data["keys"][current_key] = rows
            continue
        text = payload
        if style.startswith("Heading 1"):
            current = None
            if text.startswith("Молиявий аудитор"):
                section = "МА"
            elif text.startswith("Тизимли таҳлилчи"):
                section = "ТА"
            elif text.startswith("Мантиқий фикрлаш"):
                section = "logic"
            elif SET_RE.match(text):
                section = "logic"
                current_set = int(SET_RE.match(text).group(1))
                data["sets"][current_set] = []
            elif text.startswith("Суҳбат саволлари"):
                section = "С"
            elif text.startswith("Тест жавоблари"):
                section = "keys"
            else:
                section = None
            continue
        if style.startswith("Heading 2"):
            m = TASK_RE.match(text)
            if section in ("МА", "ТА", "С") and m:
                current = {"code": f"{m.group(1)} {m.group(2)}", "title": m.group(3).strip(), "text": [], "criteria": []}
                data[section].append(current)
            elif section == "keys" and KEY_RE.match(text):
                current_key = int(KEY_RE.match(text).group(1))
            continue

        # Oddiy paragraf
        if section in ("МА", "ТА", "С"):
            if current is None:
                data["intros"].setdefault(section, []).append(text)
                continue
            m = CRITERION_RE.match(text)
            if m:
                current["criteria"].append((m.group(2).strip(), int(m.group(3))))
            else:
                current["text"].append(text)
        elif section == "logic":
            if current_set is None:
                if text.startswith("Номзод учун кўрсатма"):
                    data["logic_instruction"] = text
                continue
            if text.startswith("Номзод коди") or text.startswith("Жавоблар:"):
                continue
            questions = data["sets"][current_set]
            if re.match(r"^[АБВГД]\)", text) and questions:
                parts = OPTION_SPLIT_RE.split(text)
                # parts: ["", "А", "matn", "Б", "matn", ...]
                for i in range(1, len(parts) - 1, 2):
                    questions[-1]["options"][parts[i]] = parts[i + 1].strip()
                continue
            m = QUESTION_RE.match(text)
            if m:
                questions.append({"number": int(m.group(1)), "text": m.group(2).strip(), "options": {}})
            elif questions:
                questions[-1]["text"] += " " + text
    return data


def validate(data):
    errors = []
    for prefix in ("МА", "ТА"):
        if len(data[prefix]) != 50:
            errors.append(f"{prefix}: 50 ta o'rniga {len(data[prefix])} ta topshiriq topildi")
    for item in data["МА"] + data["ТА"] + data["С"]:
        if len(item["criteria"]) != 5:
            errors.append(f"{item['code']}: {len(item['criteria'])} ta mezon")
        if not item["text"]:
            errors.append(f"{item['code']}: matn yo'q")
    for n, questions in data["sets"].items():
        if len(questions) != 20:
            errors.append(f"{n}-to'plam: {len(questions)} ta savol")
        for q in questions:
            if sorted(q["options"]) != sorted(LETTERS):
                errors.append(f"{n}-to'plam {q['number']}-savol: variantlar {''.join(sorted(q['options']))}")
        keys = data["keys"].get(n, [])
        if len(keys) != 20:
            errors.append(f"{n}-to'plam kaliti: {len(keys)} ta qator")
    return errors


class Command(BaseCommand):
    help = "Tanlov materiallari .docx faylidan savollar banki va namuna testlarni yaratadi."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--no-tests", action="store_true", help="Faqat banklar, namuna testlarsiz")
        parser.add_argument("--author", help="Testlar muallifi (login). Standart: birinchi superadmin")

    def handle(self, path, no_tests=False, author=None, **opts):
        self.verbosity = opts.get("verbosity", 1)
        data = parse(path)
        errors = validate(data)
        if errors:
            raise CommandError("Hujjat formati kutilganidek emas:\n  " + "\n  ".join(errors))

        with transaction.atomic():
            banks = self.import_banks(data)
            if not no_tests:
                user = (
                    User.objects.filter(username=author).first() if author
                    else User.objects.filter(role=User.Role.SUPERADMIN).order_by("pk").first()
                )
                if user is None:
                    raise CommandError("Muallif topilmadi. Avval superadmin yarating yoki --author bering.")
                self.create_tests(data, banks, user)

    def log(self, message):
        if self.verbosity:
            self.stdout.write(message)

    def bank(self, name, kind, description, order):
        bank, _ = QuestionBank.objects.update_or_create(
            name=name, defaults={"kind": kind, "description": description, "order": order},
        )
        return bank

    def upsert(self, bank, code, **fields):
        q, _ = Question.objects.update_or_create(bank=bank, code=code, defaults={**fields, "correct_option": None})
        q.options.all().delete()
        q.criteria.all().delete()
        return q

    def add_task(self, bank, item, order):
        q = self.upsert(
            bank, item["code"], title=item["title"], text=html_paragraphs(item["text"]),
            qtype=Question.Type.TEXT, max_score=sum(s for _, s in item["criteria"]), order=order,
        )
        for i, (text, score) in enumerate(item["criteria"], start=1):
            q.criteria.create(text=text, max_score=score, order=i)
        return q

    def import_banks(self, data):
        banks = {}
        banks["МА"] = self.bank(
            "Молиявий аудитор — амалий топшириқлар", Kind.PRACTICAL,
            " ".join(data["intros"].get("МА", [])), 1,
        )
        banks["ТА"] = self.bank(
            "Тизимли таҳлилчи — амалий топшириқлар", Kind.PRACTICAL,
            " ".join(data["intros"].get("ТА", [])), 2,
        )
        for prefix in ("МА", "ТА"):
            for i, item in enumerate(data[prefix], start=1):
                self.add_task(banks[prefix], item, i)

        for n in sorted(data["sets"]):
            bank = self.bank(f"Мантиқий тест — {n}-тўплам", Kind.LOGIC, data["logic_instruction"], 10 + n)
            keys = {int(row[0]): row for row in data["keys"][n] if row and row[0].isdigit()}
            for q in data["sets"][n]:
                key = keys[q["number"]]
                question = self.upsert(
                    bank, f"Т{n}-{q['number']:02d}", title=f"{n}-тўплам, {q['number']}-тест",
                    text=f"<p>{escape(q['text'])}</p>", qtype=Question.Type.CHOICE, max_score=1, order=q["number"],
                    explanation=f"Тўғри: {key[1]}. Яқин чалғитувчилар: {key[2]}. {key[3]}",
                )
                for i, letter in enumerate(LETTERS, start=1):
                    option = question.options.create(text=q["options"][letter], order=i)
                    if letter == key[1].strip():
                        question.correct_option = option
                if question.correct_option is None:
                    raise CommandError(f"{n}-to'plam {q['number']}-savol: kalit '{key[1]}' noto'g'ri")
                question.save(update_fields=["correct_option"])
            banks[f"logic{n}"] = bank

        groups = [
            ("general", "Суҳбат — умумий саволлар", range(1, 13), 21),
            ("МА", "Суҳбат — молиявий аудитор", range(13, 17), 22),
            ("ТА", "Суҳбат — тизимли таҳлилчи", range(17, 21), 23),
        ]
        intro = " ".join(data["intros"].get("С", []))
        for key, name, numbers, order in groups:
            bank = self.bank(name, Kind.INTERVIEW, intro, order)
            for i, item in enumerate(x for x in data["С"] if int(x["code"].split()[1]) in numbers):
                self.add_task(bank, item, i + 1)
            banks[f"interview_{key}"] = bank

        total = sum(b.questions.count() for b in banks.values())
        self.log(self.style.SUCCESS(f"Banklar yangilandi: {len(banks)} ta bank, {total} ta savol."))
        return banks

    def create_tests(self, data, banks, user):
        by_code = {q.code: q for q in Question.objects.filter(bank__in=banks.values())}
        for spec in SAMPLE_TESTS:
            if Test.objects.filter(title=spec["title"]).exists():
                self.log(f"Test allaqachon bor, o'tkazib yuborildi: {spec['title']}")
                continue
            test = Test.objects.create(
                title=spec["title"], is_active=False, created_by=user,
                shuffle_questions=True, shuffle_options=False, review_mode=Test.ReviewMode.DOUBLE,
                description=(
                    "Тест икки қисмдан иборат: мантиқий тест (40 дақиқа) ва ёзма амалий топшириқлар (180 дақиқа). "
                    "Интернет, сунъий интеллект, калькулятор ва ташқи ёрдамдан фойдаланиш мумкин эмас. "
                    "Қоралама қоғозга рухсат берилади."
                ),
            )
            logic = Block.objects.create(
                test=test, title="Мантиқий фикрлаш тести", kind=Kind.LOGIC, duration_minutes=40, order=1,
                description=data["logic_instruction"].split(" Жавоблар калити")[0],
            )
            for q in banks[f"logic{spec['logic_set']}"].questions.prefetch_related("options", "criteria"):
                q.copy_to(block=logic)
            practical = Block.objects.create(
                test=test, title="Ёзма амалий топшириқлар", kind=Kind.PRACTICAL, duration_minutes=180, order=2,
                description=PRACTICAL_INSTRUCTION,
            )
            for i, code in enumerate(spec["tasks"], start=1):
                by_code[code].copy_to(block=practical, order=i)
            test.interview_questions.set([by_code[c] for c in spec["interview"]])
            self.log(self.style.SUCCESS(f"Test yaratildi (nofaol): {test.title}"))
