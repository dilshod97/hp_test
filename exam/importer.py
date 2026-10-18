"""
Танлов материаллари (.docx) импорти — буйруқ ва веб-саҳифа учун умумий.

Кутиладиган формат (Word услублари бўйича):

* «Heading 1» — бўлим. Ичида «Heading 2» топшириқлар бўлса, бу ёзма амалий топшириқлар бўлими.
  Бўлим номи «Суҳбат...» билан бошланса — суҳбат саволлари.
* «Heading 2» топшириқ: «МА 01 Сарлавҳа» (1–4 ҳарфли код, рақам, сарлавҳа). Ундан кейин:
  шарт матни (бир ёки бир нечта хатбоши) ва мезонлар «1. Мезон матни. 2 балл».
* Мантиқий тест тўплами: «Heading 1» «1 тўплам». Саволлар «1. Савол матни», вариантлар
  «А) ...  Б) ...» (бир қаторда ёки алоҳида қаторларда).
* Калитлар: «Heading 2» «1 тўплам калити» дан кейинги жадвал: № | Тўғри | Яқин вариантлар | Изоҳ.
* «Номзод учун кўрсатма: ...» хатбошиси мантиқий тест блоки учун кўрсатма бўлади.
* Суҳбат бўлими кириш матнида «С 01–С 12 — умумий; С 13–С 16 — ...» бўлса, саволлар гуруҳларга бўлинади.

Бир ҳужжат такрор юкланса, саволлар код бўйича янгиланади (тестлардаги нусхаларга таъсир қилмайди).
Ҳар бир ҳужжат ўз номи (манба) остида сақланади — бошқа ҳужжат мавжуд бўлимлар устига ёзмайди.
"""
import re
from dataclasses import dataclass, field
from html import escape

from django.db import transaction

from .models import Block, Kind, Question, QuestionBank, Test

UP = "A-ZА-ЯЎҚҒҲЁ"
TASK_RE = re.compile(rf"^([{UP}]{{1,4}})\s+(\d{{1,3}})\s+(.+)$")
CRITERION_RE = re.compile(r"^(\d{1,2})\.\s+(.*?)\s+(\d+)\s+балл\.?$")
QUESTION_RE = re.compile(r"^(\d{1,3})\.\s+(.*)$")
OPTION_START_RE = re.compile(r"^([А-ЕA-E])\)\s*")
OPTION_SPLIT_RE = re.compile(r"(?:^|\s{2,}|\t)([А-ЕA-E])\)\s*")
SET_RE = re.compile(r"^(\d{1,2})\s*[- ]?\s*тўплам$", re.I)
KEY_RE = re.compile(r"^(\d{1,2})\s*[- ]?\s*тўплам калити$", re.I)
GROUP_RE = re.compile(rf"([{UP}]{{1,4}})\s*(\d+)\s*[–-]\s*(?:[{UP}]{{1,4}}\s*)?(\d+)\s*[—–-]\s*([^;.]+)")
LATIN_TO_CYR = str.maketrans("ABCDE", "АБВГД")

# Ҳисоб палатаси ҳужжати учун намуна билетлар (фақат шу кодлар топилса яратилади)
SAMPLE_TESTS = [
    {
        "title": "Молиявий аудитор — танлов (намуна билет)", "logic_set": 1,
        "tasks": ["МА 01", "МА 05", "МА 21", "МА 30", "МА 38", "МА 46"],
        "interview": ["С 01", "С 02", "С 03", "С 13", "С 14"],
    },
    {
        "title": "Тизимли таҳлилчи — танлов (намуна билет)", "logic_set": 2,
        "tasks": ["ТА 01", "ТА 11", "ТА 20", "ТА 22", "ТА 36", "ТА 42"],
        "interview": ["С 01", "С 02", "С 03", "С 17", "С 18"],
    },
]
PRACTICAL_INSTRUCTION = (
    "Ҳар бир топшириқни алоҳида бажаринг. Ҳисоб натижаси, ўлчов бирлиги ва фаразларингизни кўрсатинг. "
    "Матн, жадвал ёки рўйхат шаклида жавоб беришингиз мумкин. Қоралама қоғозга рухсат берилади."
)


@dataclass
class Section:
    kind: str                 # practical | interview | logic
    name: str
    intro: list = field(default_factory=list)
    items: list = field(default_factory=list)
    set_no: int = 0           # мантиқий тест тўплами рақами


@dataclass
class Parsed:
    title: str = ""
    sections: list = field(default_factory=list)
    keys: dict = field(default_factory=dict)     # тўплам рақами -> {савол рақами: [тўғри, яқин, изоҳ]}
    logic_instruction: str = ""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def question_count(self):
        return sum(len(s.items) for s in self.sections)


def _blocks(document):
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = p.text.strip()  # бўшлиқларни сақлаймиз: вариантлар «А) ...     Б) ...» шаклида ажратилган
            if text:
                yield "p", (p.style.name if p.style is not None else ""), text
        elif tag == "tbl":
            t = Table(child, document)
            yield "table", "", [[c.text.strip() for c in row.cells] for row in t.rows]


def parse(fileobj):
    """Ҳужжатни таҳлил қилади. fileobj — йўл ёки очилган файл."""
    import docx

    out = Parsed()
    try:
        document = docx.Document(fileobj)
    except Exception:
        out.errors.append("Файлни ўқиб бўлмади. У Word (.docx) форматида эканини текширинг.")
        return out

    section = None
    mode = None            # None | "section" | "keys"
    current = None
    key_set = None

    for kind, style, payload in _blocks(document):
        if kind == "table":
            if mode == "keys" and key_set:
                rows = {}
                for row in payload:
                    if row and row[0].strip().isdigit():
                        rows[int(row[0])] = [c.strip() for c in row[1:]]
                out.keys[key_set] = rows
            continue
        text = payload
        if style == "Title" and not out.title:
            out.title = text
            continue

        if style.startswith("Heading 1"):
            current, key_set = None, None
            m = SET_RE.match(text)
            low = text.lower()
            if m:
                section = Section("logic", f"Мантиқий тест — {int(m.group(1))}-тўплам", set_no=int(m.group(1)))
                out.sections.append(section)
                mode = "section"
            elif "калит" in low or low.startswith("тест жавоблари"):
                section, mode = None, "keys"
            elif low.startswith("суҳбат"):
                section = Section("interview", text)
                out.sections.append(section)
                mode = "section"
            else:
                section = Section("practical", text)
                out.sections.append(section)
                mode = "section"
            continue

        if style.startswith("Heading 2"):
            if mode == "keys":
                m = KEY_RE.match(text)
                key_set = int(m.group(1)) if m else None
                continue
            m = TASK_RE.match(text)
            if section is not None and section.kind != "logic" and m:
                current = {"code": f"{m.group(1)} {int(m.group(2)):02d}", "title": m.group(3).strip(),
                           "text": [], "criteria": []}
                section.items.append(current)
            continue

        if text.startswith("Номзод учун кўрсатма") and not out.logic_instruction:
            out.logic_instruction = text.split(" Жавоблар калити")[0]
        if section is None:
            continue

        if section.kind == "logic":
            if text.startswith(("Номзод коди", "Жавоблар:", "Номзод учун")):
                continue
            items = section.items
            if OPTION_START_RE.match(text) and items:
                parts = OPTION_SPLIT_RE.split(text)
                for i in range(1, len(parts) - 1, 2):
                    letter = parts[i].translate(LATIN_TO_CYR)
                    items[-1]["options"].append((letter, parts[i + 1].strip()))
                continue
            m = QUESTION_RE.match(text)
            if m:
                items.append({"number": int(m.group(1)), "text": m.group(2).strip(), "options": []})
            elif items:
                items[-1]["text"] += " " + text
            continue

        if current is None:
            section.intro.append(text)
            continue
        m = CRITERION_RE.match(text)
        if m:
            current["criteria"].append((m.group(2).strip(), int(m.group(3))))
        else:
            current["text"].append(text)

    # Топшириқсиз «practical» бўлимлар — бу оддий матн бўлимлари (йўриқнома ва ҳ.к.)
    out.sections = [s for s in out.sections if s.items]
    _validate(out)
    return out


def _validate(out):
    if not out.sections and not out.errors:
        out.errors.append("Ҳужжатда савол топилмади. Формат йўриқномасини текширинг.")
    for s in out.sections:
        if s.kind == "logic":
            keys = out.keys.get(s.set_no)
            if not keys:
                out.errors.append(f"«{s.name}»: калит жадвали топилмади («{s.set_no} тўплам калити»).")
                continue
            for q in s.items:
                letters = [x for x, _ in q["options"]]
                if len(letters) < 2:
                    out.errors.append(f"«{s.name}», {q['number']}-савол: вариантлар топилмади.")
                key = keys.get(q["number"])
                if not key or not key[0]:
                    out.errors.append(f"«{s.name}», {q['number']}-савол: калитда жавоб йўқ.")
                elif key[0].strip().translate(LATIN_TO_CYR) not in letters:
                    out.errors.append(f"«{s.name}», {q['number']}-савол: калитдаги «{key[0]}» вариантлар орасида йўқ.")
        else:
            seen = set()
            for item in s.items:
                if item["code"] in seen:
                    out.errors.append(f"«{s.name}»: {item['code']} коди икки марта учрайди.")
                seen.add(item["code"])
                if not item["text"]:
                    out.errors.append(f"{item['code']}: топшириқ шарти йўқ.")
                if not item["criteria"]:
                    out.warnings.append(f"{item['code']}: баҳолаш мезонлари йўқ — эксперт умумий балл қўяди (макс. 10).")


def _html(lines):
    return "".join(f"<p>{escape(line)}</p>" for line in lines)


def _bank(source, name, kind, description, order):
    bank, created = QuestionBank.objects.update_or_create(
        source=source, name=name, defaults={"kind": kind, "description": description, "order": order},
    )
    return bank, created


def _upsert(bank, code, **fields):
    q, created = Question.objects.update_or_create(bank=bank, code=code, defaults={**fields, "correct_option": None})
    q.options.all().delete()
    q.criteria.all().delete()
    return q, created


def _add_task(bank, item, order):
    max_score = sum(s for _, s in item["criteria"]) or 10
    q, created = _upsert(bank, item["code"], title=item["title"], text=_html(item["text"]),
                         qtype=Question.Type.TEXT, max_score=max_score, order=order)
    for i, (text, score) in enumerate(item["criteria"], start=1):
        q.criteria.create(text=text, max_score=score, order=i)
    return q, created


def _interview_groups(section):
    """Кириш матнидаги «С 01–С 12 — умумий; ...» бўйича гуруҳлар."""
    intro = " ".join(section.intro)
    groups = []
    for m in GROUP_RE.finditer(intro):
        lo, hi = int(m.group(2)), int(m.group(3))
        label = re.sub(r"\s+учун$", "", m.group(4).strip().rstrip(","))
        groups.append((label, range(lo, hi + 1)))
    return groups


@transaction.atomic
def import_parsed(parsed, source, user=None, create_tests=True):
    """Таҳлил қилинган ҳужжатни базага ёзади. Ҳисобот (dict) қайтаради."""
    report = {"banks": [], "created": 0, "updated": 0, "tests": [], "skipped_tests": []}
    order_base = (QuestionBank.objects.exclude(source=source).order_by("-order").values_list("order", flat=True).first() or 0)
    by_code, logic_sets = {}, {}   # logic_sets: тўплам рақами -> [саволлар]
    logic_bank = None              # барча мантиқий тўпламлар битта бўлимда

    def note(bank, n):
        report["banks"].append({"name": bank.name, "kind": bank.get_kind_display(), "count": n})

    for idx, s in enumerate(parsed.sections, start=1):
        order = order_base + idx
        intro = " ".join(s.intro)
        if s.kind == "logic":
            if logic_bank is None:
                logic_bank, _ = _bank(source, "Мантиқий тест", Kind.LOGIC, parsed.logic_instruction, order)
            bank = logic_bank
            keys = parsed.keys[s.set_no]
            for q in s.items:
                key = keys[q["number"]] + ["", "", ""]
                parts = [f"Тўғри: {key[0]}."]
                if key[1]:
                    parts.append(f"Яқин чалғитувчилар: {key[1]}.")
                if key[2]:
                    parts.append(key[2])
                question, created = _upsert(
                    bank, f"Т{s.set_no}-{q['number']:02d}", title=f"{s.set_no}-тўплам, {q['number']}-тест",
                    text=f"<p>{escape(q['text'])}</p>", qtype=Question.Type.CHOICE, max_score=1,
                    order=s.set_no * 100 + q["number"],
                    explanation=" ".join(parts),
                )
                report["created" if created else "updated"] += 1
                correct = key[0].strip().translate(LATIN_TO_CYR)
                for i, (letter, text) in enumerate(q["options"], start=1):
                    option = question.options.create(text=text, order=i)
                    if letter == correct:
                        question.correct_option = option
                question.save(update_fields=["correct_option"])
                logic_sets.setdefault(s.set_no, []).append(question)
            continue

        if s.kind == "interview":
            groups = _interview_groups(s) or [("", None)]
            for g, (label, numbers) in enumerate(groups):
                name = f"Суҳбат — {label}" if label else s.name
                bank, _ = _bank(source, name, Kind.INTERVIEW, intro, order * 10 + g)
                items = [x for x in s.items if numbers is None or int(x["code"].split()[1]) in numbers]
                for i, item in enumerate(items, start=1):
                    q, created = _add_task(bank, item, i)
                    by_code[item["code"]] = q
                    report["created" if created else "updated"] += 1
                note(bank, len(items))
            continue

        name = s.name.replace(" учун амалий топшириқлар", " — амалий топшириқлар")
        bank, _ = _bank(source, name, Kind.PRACTICAL, intro, order)
        for i, item in enumerate(s.items, start=1):
            q, created = _add_task(bank, item, i)
            by_code[item["code"]] = q
            report["created" if created else "updated"] += 1
        note(bank, len(s.items))

    if logic_bank is not None:
        note(logic_bank, sum(len(v) for v in logic_sets.values()))

    if create_tests and user is not None:
        for spec in SAMPLE_TESTS:
            codes = spec["tasks"] + spec["interview"]
            if spec["logic_set"] not in logic_sets or any(c not in by_code for c in codes):
                continue
            if Test.objects.filter(title=spec["title"]).exists():
                report["skipped_tests"].append(spec["title"])
                continue
            test = Test.objects.create(
                title=spec["title"], is_active=False, created_by=user, shuffle_questions=True,
                shuffle_options=False, review_mode=Test.ReviewMode.DOUBLE,
                description=("Тест икки қисмдан иборат: мантиқий тест ва ёзма амалий топшириқлар. "
                             "Интернет, сунъий интеллект, калькулятор ва ташқи ёрдамдан фойдаланиш мумкин эмас. "
                             "Қоралама қоғозга рухсат берилади."),
            )
            logic = Block.objects.create(test=test, title="Мантиқий фикрлаш тести", kind=Kind.LOGIC,
                                         duration_minutes=40, order=1, description=parsed.logic_instruction)
            for q in logic_sets[spec["logic_set"]]:
                q.copy_to(block=logic)
            practical = Block.objects.create(test=test, title="Ёзма амалий топшириқлар", kind=Kind.PRACTICAL,
                                             duration_minutes=180, order=2, description=PRACTICAL_INSTRUCTION)
            for i, code in enumerate(spec["tasks"], start=1):
                by_code[code].copy_to(block=practical, order=i)
            test.interview_questions.set([by_code[c] for c in spec["interview"]])
            report["tests"].append(test.title)
    return report
