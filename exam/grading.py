"""
Baholash qoidalari (tanlov materiallaridagi "Қўллаш ва баҳолаш тартиби" bo'yicha):

* Kaliti bor variantli savol: to'g'ri — maksimal ball (odatda 1), noto'g'ri yoki bo'sh — 0.
* Yozma amaliy topshiriq: har bir mezon 0–2 ball, ish nomzod kodi bilan ekspert(lar)ga beriladi.
* Ikki ekspert rejimi: ikkalasi mustaqil baholaydi (bir-birining balini ko'rmaydi).
  Jami farq maksimal ballning 15 foizidan oshsa (60 dan 9) yoki biror mezonda biri 0, ikkinchisi
  to'liq ball qo'ysa — uchinchi mustaqil tekshiruv tayinlanadi va har mezon bo'yicha uch bahoning
  medianasi olinadi. Uchinchisiz holatda ikki baho o'rtachasi olinadi.
* Yakuniy shkala: amaliy 55 × ball/maks + mantiqiy 15 × ball/maks + suhbat 15 × ball/maks + himoya (0–15).
"""
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from django.db.models import Count, Q
from django.utils import timezone

from .models import Attempt, Kind, Review, ReviewAnswer, Test

THIRD_REVIEW_DIFF_RATIO = Decimal("0.15")
TWO_PLACES = Decimal("0.01")

LOGIC_BANDS = [  # 20 ballik shkala bo'yicha
    (7, "Сезиларли қийинчилик"),
    (13, "Қисман ўзлаштириш"),
    (17, "Яхши натижа"),
    (20, "Юқори натижа"),
]


def d(value):
    return Decimal(str(value))


def _fmt(value):
    return f"{d(value).normalize():f}".replace(".", ",")


def manual_answers(attempt):
    return attempt.answers.filter(auto_graded=False)


def answer_scale(answer):
    """Javob qaysi mezonlar bo'yicha baholanadi: [(matn, maks), ...]."""
    criteria = list(answer.question.criteria.all())
    if criteria:
        return [(c.text, c.max_score) for c in criteria]
    return [("Умумий балл", answer.question.max_score)]


def auto_grade(attempt):
    for a in attempt.answers.select_related("question"):
        q = a.question
        if q.is_auto:
            a.score = q.max_score if a.selected_option_id == q.correct_option_id else Decimal(0)
            a.auto_graded = True
        elif a.is_empty:
            a.score = Decimal(0)
            a.auto_graded = True
        else:
            continue
        a.save(update_fields=["score", "auto_graded"])


def pick_checker(test, exclude_ids):
    """Testga biriktirilgan, hali bu ishni ko'rmagan va eng kam ochiq ishi bor tekshiruvchi.
    Рус вариантига алоҳида эксперт бириктирилмаган бўлса — асосий тестнинг экспертлари."""
    checkers = test.checkers.all()
    if not checkers.exists() and getattr(test, "uz_original", None) is not None:
        checkers = test.uz_original.checkers.all()
    return (
        checkers.filter(is_active=True).exclude(pk__in=exclude_ids)
        .annotate(load=Count("reviews", filter=Q(reviews__submitted_at__isnull=True)))
        .order_by("load", "?").first()
    )


def required_reviews(attempt):
    return attempt.test.required_reviews + (1 if attempt.third_review_needed else 0)


def ensure_reviews(attempt):
    if not manual_answers(attempt).exists():
        return
    existing = list(attempt.reviews.all())
    while len(existing) < required_reviews(attempt):
        checker = pick_checker(attempt.test, [r.checker_id for r in existing])
        if checker is None:
            break  # superadmin qo'lda biriktiradi
        existing.append(Review.objects.create(attempt=attempt, checker=checker, round=len(existing) + 1))


def on_attempt_finished(attempt):
    auto_grade(attempt)
    ensure_reviews(attempt)
    recompute(attempt)


def combine(values):
    values = [d(v) for v in values]
    if len(values) >= 3:
        return d(median(values[:3]))
    if len(values) == 2:
        return (values[0] + values[1]) / 2
    return values[0]


def _complete(scores):
    return bool(scores) and all(s is not None for s in scores)


def discrepancy_reason(attempt, first, second):
    """Uchinchi tekshiruv kerakligining sababi yoki None."""
    manual = list(manual_answers(attempt).select_related("question").prefetch_related("question__criteria"))
    if not manual:
        return None
    items = {(i.review_id, i.answer_id): i.scores for i in ReviewAnswer.objects.filter(review__in=[first, second])}
    total_max = sum(d(a.question.max_score) for a in manual)
    t1 = t2 = Decimal(0)
    for a in manual:
        s1, s2 = items.get((first.pk, a.pk)), items.get((second.pk, a.pk))
        if not (_complete(s1) and _complete(s2)):
            continue
        t1 += sum(d(x) for x in s1)
        t2 += sum(d(x) for x in s2)
        for (text, mx), x, y in zip(answer_scale(a), s1, s2):
            if {d(x), d(y)} == {Decimal(0), d(mx)} and d(mx) > 1:
                label = a.question.title or "савол"
                return f"«{label}»: битта мезонга 0 ва {mx} балл қўйилган"
    limit = (total_max * THIRD_REVIEW_DIFF_RATIO).quantize(TWO_PLACES)
    if abs(t1 - t2) > limit:
        return f"Экспертлар фарқи {_fmt(abs(t1 - t2))} балл (чегара {_fmt(limit)})"
    return None


def recompute(attempt):
    """Ekspert baholaridan javob ballarini va urinish holatini qayta hisoblaydi."""
    test = attempt.test
    submitted = list(attempt.reviews.filter(submitted_at__isnull=False).order_by("round", "id"))
    items = {(i.review_id, i.answer_id): i.scores for i in ReviewAnswer.objects.filter(review__in=submitted)}
    manual = list(manual_answers(attempt))

    for a in manual:
        per_reviewer = [items.get((r.pk, a.pk)) for r in submitted]
        per_reviewer = [s for s in per_reviewer if _complete(s)]
        if per_reviewer:
            n = min(len(s) for s in per_reviewer)
            score = sum(combine([s[i] for s in per_reviewer]) for i in range(n))
            score = score.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            score = None
        if score != a.score:
            a.score = score
            a.save(update_fields=["score"])

    if (
        test.review_mode == Test.ReviewMode.DOUBLE and not attempt.third_review_needed
        and len(submitted) >= 2
    ):
        reason = discrepancy_reason(attempt, submitted[0], submitted[1])
        if reason:
            attempt.third_review_needed = True
            attempt.third_review_reason = reason
            attempt.save(update_fields=["third_review_needed", "third_review_reason"])
            ensure_reviews(attempt)

    if attempt.status == Attempt.Status.IN_PROGRESS:
        return
    done = not manual or len(submitted) >= required_reviews(attempt)
    new_status = Attempt.Status.GRADED if done else Attempt.Status.FINISHED
    if new_status != attempt.status:
        attempt.status = new_status
        attempt.graded_at = timezone.now() if done else None
        attempt.save(update_fields=["status", "graded_at"])


# ---------------------------------------------------------------- Yakuniy ball

def _part(attempt, kind):
    answers = [a for a in attempt.answers.select_related("question__block") if a.question.block and a.question.block.kind == kind]
    if not answers:
        return None
    mx = sum(d(a.question.max_score) for a in answers)
    scores = [a.score for a in answers]
    score = None if any(s is None for s in scores) else sum(d(s) for s in scores)
    return {"score": score, "max": mx}


def interview_part(attempt):
    questions = list(attempt.test.interview_questions.order_by("bank__order", "order").prefetch_related("criteria"))
    if not questions:
        return None
    mx = Decimal(0)
    score = Decimal(0)
    complete = True
    for q in questions:
        crit = list(q.criteria.all())
        mx += sum(d(c.max_score) for c in crit) if crit else d(q.max_score)
        vals = attempt.interview_scores.get(str(q.pk))
        if not _complete(vals):
            complete = False
            continue
        score += sum(d(v) for v in vals)
    return {"score": score if complete else None, "max": mx}


def logic_band(part):
    if not part or part["score"] is None or not part["max"]:
        return ""
    on20 = part["score"] * 20 / part["max"]
    for limit, label in LOGIC_BANDS:
        if on20 <= limit:
            return label
    return LOGIC_BANDS[-1][1]


def summary(attempt):
    """Komponentlar va 100 ballik yakuniy natija. Biror komponent yo'q bo'lsa — final None."""
    test = attempt.test
    parts = {
        "logic": _part(attempt, Kind.LOGIC),
        "test": _part(attempt, Kind.TEST),
        "practical": _part(attempt, Kind.PRACTICAL),
        "interview": interview_part(attempt),
    }
    weights = {"logic": test.weight_logic, "test": test.weight_test, "practical": test.weight_practical, "interview": test.weight_interview}
    final = Decimal(0)
    complete = True
    for key, part in parts.items():
        if part is None:
            continue
        part["weight"] = d(weights[key])
        if part["score"] is None or not part["max"]:
            complete = False
            part["weighted"] = None
            continue
        part["weighted"] = (d(weights[key]) * part["score"] / part["max"]).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        final += part["weighted"]
    if test.weight_defense:
        if attempt.defense_score is None:
            complete = False
        else:
            final += d(attempt.defense_score)
    return {
        **parts,
        "defense": attempt.defense_score,
        "defense_max": test.weight_defense,
        "logic_band": logic_band(parts["logic"]),
        "final": final.quantize(TWO_PLACES) if complete else None,
        "partial": final.quantize(TWO_PLACES),
    }


def missing_reviewers(attempt):
    """Нечта эксперт етишмаяпти (тестга эксперт бириктирилмагани сабабли иш тиқилиб қолганда)."""
    if attempt.status != Attempt.Status.FINISHED or not manual_answers(attempt).exists():
        return 0
    return max(0, required_reviews(attempt) - attempt.reviews.count())


def refresh_test_attempts(test):
    """Текшириш тартиби ёки экспертлар ўзгарганда кутиб турган ишларни қайта ҳисоблайди."""
    for attempt in test.attempts.filter(status__in=[Attempt.Status.FINISHED, Attempt.Status.GRADED]):
        ensure_reviews(attempt)
        recompute(attempt)
