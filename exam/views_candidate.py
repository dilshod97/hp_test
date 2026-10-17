"""Nomzod (test yechuvchi) sahifalari. Hammasi /exam/ ostida va SEB middleware bilan himoyalangan."""
import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CandidateLoginForm
from .models import Answer, Attempt, BlockAttempt, Candidate
from .utils import clean_answer, client_ip, create_attempt, is_empty_html

SESSION_KEY = "attempt_id"


def _current_attempt(request):
    attempt_id = request.session.get(SESSION_KEY)
    if not attempt_id:
        return None
    return Attempt.objects.select_related("test", "candidate").filter(pk=attempt_id).first()


def candidate_login(request):
    attempt = _current_attempt(request)
    if attempt and attempt.status == Attempt.Status.IN_PROGRESS:
        return redirect("exam_take")

    form = CandidateLoginForm(request.POST or None)
    choices = None
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        key = Candidate.make_identity_key(d["last_name"], d["first_name"], d["middle_name"], d["birth_date"])
        candidate = Candidate.objects.filter(identity_key=key).first()
        assignments = []
        if candidate:
            assignments = [
                a for a in candidate.assignments.select_related("test").filter(test__is_active=True)
                if a.test.blocks.exists()
            ]
        pending = []
        for a in assignments:
            existing = a.attempt
            if existing is None or existing.status == Attempt.Status.IN_PROGRESS:
                pending.append((a, existing))
        if not candidate:
            form.add_error(None, "Сиз номзодлар рўйхатида топилмадингиз. Маълумотларни паспортдагидек "
                                 "текшириб ёзинг ёки назоратчига мурожаат қилинг.")
        elif not assignments:
            form.add_error(None, "Сизга ҳозир фаол тест бириктирилмаган. Назоратчига мурожаат қилинг.")
        elif not pending:
            form.add_error(None, "Сиз бу тестни аллақачон топширгансиз. Қайта топшириш мумкин эмас.")
        else:
            chosen = None
            if len(pending) == 1:
                chosen = pending[0]
            else:
                test_id = request.POST.get("test")
                chosen = next((p for p in pending if str(p[0].test_id) == test_id), None)
                if chosen is None:
                    choices = [p[0].test for p in pending]
            if chosen:
                assignment, attempt = chosen
                if attempt is None:
                    try:
                        attempt = create_attempt(candidate, assignment.test, ip=client_ip(request))
                    except IntegrityError:
                        attempt = Attempt.objects.get(candidate=candidate, test=assignment.test)
                else:
                    messages.info(request, "Тестни давом эттиряпсиз. Аввалги жавобларингиз сақланган.")
                request.session.flush()  # brauzerda xodim sessiyasi qolmasin
                request.session[SESSION_KEY] = attempt.pk
                return redirect("exam_take")

    return render(request, "exam/candidate/login.html", {"form": form, "choices": choices})


def take(request):
    attempt = _current_attempt(request)
    if attempt is None:
        return redirect("exam_login")
    if attempt.status != Attempt.Status.IN_PROGRESS:
        return redirect("exam_done")

    if attempt.test.require_photo and not attempt.photo_status:
        return redirect("exam_photo")

    with transaction.atomic():
        ba = attempt.close_expired_blocks()
    if ba is None:
        return redirect("exam_done")

    free = attempt.test.free_navigation
    all_blocks = list(attempt.block_attempts.select_related("block"))
    shown = [b for b in all_blocks if b.finished_at is None] if free else [ba]

    answers = {a.question_id: a for a in attempt.answers.filter(question__block__in=[b.block for b in shown])}
    items, sections = [], []
    for b in shown:
        questions = {q.id: q for q in b.block.questions.prefetch_related("options")}
        section = {"title": b.block.title, "items": []}
        for qid in b.layout.get("questions", []):
            q = questions.get(qid)
            if q is None:
                continue
            opts = {o.id: o for o in q.options.all()}
            ordered = [opts[oid] for oid in b.layout.get("options", {}).get(str(qid), []) if oid in opts]
            item = {"index": len(items), "number": len(items) + 1, "question": q, "options": ordered,
                    "answer": answers.get(qid), "block": b.block}
            items.append(item)
            section["items"].append(item)
        sections.append(section)

    blocks_state = [
        {"title": b.block.title, "minutes": b.block.duration_minutes,
         "state": "now" if (b in shown) else ("done" if b.finished_at else "todo")}
        for b in all_blocks
    ]
    return render(request, "exam/candidate/take.html", {
        "attempt": attempt,
        "block_attempt": ba,
        "cur_block": ba.block,
        "free": free,
        "items": items,
        "sections": sections,
        "shown_blocks": [b.block for b in shown],
        "seconds_left": ba.seconds_left(),
        "block_index": [b.pk for b in all_blocks].index(ba.pk) + 1,
        "block_count": len(all_blocks),
        "is_last_block": free or ba.pk == all_blocks[-1].pk,
        "blocks_state": blocks_state,
    })


def _can_edit(ba, now):
    if ba.started_at is None:
        return False
    if now > ba.deadline + timedelta(seconds=settings.ANSWER_GRACE_SECONDS):
        return False
    # Nomzod o'zi "keyingi blok" ni bosgan bo'lsa, qaytib o'zgartira olmaydi
    return ba.finished_at is None or ba.finished_at >= ba.deadline


@require_POST
def save_answer(request):
    attempt = _current_attempt(request)
    if attempt is None or attempt.status != Attempt.Status.IN_PROGRESS:
        return JsonResponse({"ok": False, "reload": True}, status=409)
    try:
        data = json.loads(request.body)
        question_id = int(data["question"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False, "error": "bad request"}, status=400)

    with transaction.atomic():
        answer = (
            Answer.objects.select_for_update().select_related("question")
            .filter(attempt=attempt, question_id=question_id).first()
        )
        if answer is None:
            return JsonResponse({"ok": False, "error": "not found"}, status=404)
        ba = BlockAttempt.objects.select_related("block").get(attempt=attempt, block_id=answer.question.block_id)
        now = timezone.now()
        if not _can_edit(ba, now):
            return JsonResponse({"ok": False, "reload": True}, status=409)

        if answer.question.qtype == answer.question.Type.CHOICE:
            option_id = data.get("option")
            if option_id is None:
                answer.selected_option = None
            else:
                option = answer.question.options.filter(pk=int(option_id)).first()
                if option is None:
                    return JsonResponse({"ok": False, "error": "bad option"}, status=400)
                answer.selected_option = option
        else:
            text = clean_answer(str(data.get("text", ""))[:200_000])
            answer.text_answer = "" if is_empty_html(text) else text
        answer.save(update_fields=["selected_option", "text_answer", "updated_at"])

    return JsonResponse({"ok": True, "seconds_left": ba.seconds_left()})


@require_POST
def next_block(request):
    attempt = _current_attempt(request)
    if attempt is None:
        return redirect("exam_login")
    if attempt.status == Attempt.Status.IN_PROGRESS:
        with transaction.atomic():
            ba = attempt.close_expired_blocks()
            if ba is not None and attempt.test.free_navigation:
                attempt.finish()  # эркин режимда тугма бутун тестни якунлайди
            elif ba is not None and str(ba.pk) == request.POST.get("block_attempt"):
                ba.finished_at = timezone.now()
                ba.save(update_fields=["finished_at"])
                attempt.close_expired_blocks()
    return redirect("exam_take")


def done(request):
    attempt = _current_attempt(request)
    if attempt and attempt.status == Attempt.Status.IN_PROGRESS:
        return redirect("exam_take")
    request.session.pop(SESSION_KEY, None)
    return render(request, "exam/candidate/done.html", {"attempt": attempt})


# ---------------------------------------------------------------- Шахсни тасдиқлаш учун расм

def photo(request):
    attempt = _current_attempt(request)
    if attempt is None:
        return redirect("exam_login")
    if attempt.status != Attempt.Status.IN_PROGRESS or attempt.photo_status or not attempt.test.require_photo:
        return redirect("exam_take")
    return render(request, "exam/candidate/photo.html", {
        "attempt": attempt, "retention_days": settings.PHOTO_RETENTION_DAYS,
    })


@require_POST
def photo_save(request):
    import base64
    import uuid

    attempt = _current_attempt(request)
    if attempt is None or attempt.status != Attempt.Status.IN_PROGRESS or attempt.photo_status:
        return JsonResponse({"ok": True})
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"ok": False}, status=400)

    status = data.get("status")
    if status in (Attempt.Photo.NO_CAMERA, Attempt.Photo.DENIED, Attempt.Photo.DECLINED):
        attempt.photo_status = status
        attempt.save(update_fields=["photo_status"])
        return JsonResponse({"ok": True})

    raw = str(data.get("image", ""))
    prefix = "data:image/jpeg;base64,"
    if not raw.startswith(prefix) or len(raw) > 3_000_000:
        return JsonResponse({"ok": False, "error": "Расм нотўғри"}, status=400)
    try:
        jpeg = base64.b64decode(raw[len(prefix):], validate=True)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Расм нотўғри"}, status=400)
    if not jpeg.startswith(b"\xff\xd8\xff"):
        return JsonResponse({"ok": False, "error": "Расм нотўғри"}, status=400)

    folder = settings.MEDIA_ROOT / "photos"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    (folder / name).write_bytes(jpeg)
    attempt.photo, attempt.photo_status, attempt.photo_at = name, Attempt.Photo.TAKEN, timezone.now()
    attempt.save(update_fields=["photo", "photo_status", "photo_at"])
    return JsonResponse({"ok": True})
