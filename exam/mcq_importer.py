"""
Вариантли тест ҳужжатлари (.docx) импорти: тўғри жавоб сариқ ранг билан белгиланган.

Таниладиган шакллар:
* савол — рақамли хатбоши («12. Матн», «25.1 Матн») ёки Word рўйхати (List Paragraph);
* вариантлар — «A) …», «А) …», «+ …» / «- …» ёки «Жавоб:» / «Ответ:» дан кейинги оддий қаторлар;
* «Тўғри / Нотўғри» («Верно / Неверно») қатори — икки вариантли савол;
* тўғри жавоб — сариқ highlight, хатбошининг сариқ фони ёки «+» белгиси.
Сарлавҳалар (Heading) ва йўриқнома матнлари саволга қўшилмайди.
"""
import re
from dataclasses import dataclass, field
from html import escape

from django.db import transaction

from .models import Kind, Question, QuestionBank

OPTION_RE = re.compile(r"^\s*(?:([A-DА-Г])\s*[\)\.]|([+\-–])\s)\s*(.*)$", re.S)
QUESTION_RE = re.compile(r"^\s*\d{1,3}(?:\.\d{1,2}\s|[.)]\s)")
NUMBER_RE = re.compile(r"^\s*\d{1,3}(?:\.\d{1,2})?[.)]?\s+")
ANSWER_LABEL_RE = re.compile(r"^(Жавоб|Ответ)\s*:?\s*$", re.I)
TRUE_FALSE_RE = re.compile(r"^(Тўғри|Верно)\s*/\s*(Нотўғри|Неверно)$", re.I)
SKIP_LINES = re.compile(r"^(Тарифлар|Определения)\s*:?\s*$", re.I)
NO_FILL = {"", "auto", "FFFFFF", "ffffff"}


@dataclass
class McqParsed:
    items: list = field(default_factory=list)   # {"text", "options": [..], "correct": [индекслар], "topic"}
    errors: list = field(default_factory=list)


def _marked_text(p):
    """Сариқ белгиланган матн: run highlight ёки хатбоши/run фони."""
    runs = [r.text for r in p.runs if r.text.strip() and (r.font.highlight_color or _run_fill(r))]
    if runs:
        return "".join(runs)
    fills = [f for f in p._p.xpath("./w:pPr/w:shd/@w:fill") if f not in NO_FILL]
    return p.text if fills else ""


def _run_fill(run):
    return any(f not in NO_FILL for f in run._r.xpath("./w:rPr/w:shd/@w:fill"))


def parse_mcq(fileobj):
    import docx

    out = McqParsed()
    try:
        document = docx.Document(fileobj)
    except Exception:
        out.errors.append("Файлни ўқиб бўлмади. У Word (.docx) форматида эканини текширинг.")
        return out

    cur, topic, answer_mode = None, "", False

    def start(text):
        nonlocal cur, answer_mode
        cur = {"text": NUMBER_RE.sub("", text, count=1).strip(), "options": [], "correct": [], "topic": topic}
        out.items.append(cur)
        answer_mode = False

    for p in document.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name if p.style is not None else ""
        if style.startswith("Heading"):
            topic, cur, answer_mode = text, None, False
            continue
        marked = _marked_text(p).strip()

        tf = TRUE_FALSE_RE.match(text)
        if tf and cur is not None and not cur["options"]:
            for word in tf.groups():
                cur["options"].append(word)
                if marked and marked.lower() == word.lower():
                    cur["correct"].append(len(cur["options"]) - 1)
            continue

        m = OPTION_RE.match(text)
        if m and cur is not None:
            cur["options"].append(m.group(3).strip())
            if marked or m.group(2) == "+":
                cur["correct"].append(len(cur["options"]) - 1)
            continue

        if answer_mode and cur is not None and not QUESTION_RE.match(text):
            cur["options"].append(text)
            if marked:
                cur["correct"].append(len(cur["options"]) - 1)
            continue

        if ANSWER_LABEL_RE.match(text):
            answer_mode = cur is not None
            continue

        if QUESTION_RE.match(text) or style == "List Paragraph":
            start(text)
        elif cur is not None and not cur["options"] and not SKIP_LINES.match(text):
            cur["text"] += " " + text   # саволнинг давоми

    for i, q in enumerate(out.items, start=1):
        label = f"{i}-савол («{q['text'][:50]}…»)"
        if len(q["options"]) < 2:
            out.errors.append(f"{label}: вариантлар топилмади.")
        elif len(q["correct"]) != 1:
            out.errors.append(f"{label}: сариқ билан белгиланган тўғри жавоб {len(q['correct'])} та (битта бўлиши керак).")
    if not out.items and not out.errors:
        out.errors.append("Ҳужжатда савол топилмади.")
    return out


@transaction.atomic
def import_mcq(parsed, *, bank_name, source, prefix, description=""):
    """Саволларни «Касбий тест» бўлимига ёзади. Код бўйича янгилайди (такрор юклаш дубликат қилмайди)."""
    order_base = QuestionBank.objects.order_by("-order").values_list("order", flat=True).first() or 0
    bank, _ = QuestionBank.objects.get_or_create(
        source=source, name=bank_name, defaults={"kind": Kind.TEST, "description": description, "order": order_base + 1},
    )
    created = updated = 0
    start = bank.questions.exclude(code__startswith=f"{prefix}-").count()
    for i, item in enumerate(parsed.items, start=1):
        q, is_new = Question.objects.update_or_create(
            bank=bank, code=f"{prefix}-{i:03d}",
            defaults={"title": item["topic"], "text": f"<p>{escape(item['text'])}</p>", "qtype": Question.Type.CHOICE,
                      "max_score": 1, "order": start + i, "correct_option": None, "explanation": ""},
        )
        q.options.all().delete()
        for n, opt in enumerate(item["options"], start=1):
            o = q.options.create(text=opt, order=n)
            if n - 1 == item["correct"][0]:
                q.correct_option = o
        q.save(update_fields=["correct_option"])
        created, updated = created + is_new, updated + (not is_new)
    return {"bank": bank, "created": created, "updated": updated}
