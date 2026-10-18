import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum
from django.utils import timezone

OPTION_LETTERS = "АБВГДЕЖЗИК"


class User(AbstractUser):
    """Xodim: superadmin, test qo'shuvchi yoki tekshiruvchi (ekspert). Nomzodlar bu jadvalda emas."""

    class Role(models.TextChoices):
        SUPERADMIN = "superadmin", "Суперадмин"
        AUTHOR = "author", "Тест тузувчи"
        CHECKER = "checker", "Эксперт"
        HR = "hr", "Кадрлар бўлими"

    role = models.CharField("Рол", max_length=20, choices=Role.choices, default=Role.CHECKER)

    @property
    def is_superadmin(self):
        return self.role == self.Role.SUPERADMIN or self.is_superuser

    @property
    def is_author(self):
        return self.role == self.Role.AUTHOR or self.is_superadmin

    @property
    def is_hr(self):
        return self.role == self.Role.HR

    @property
    def can_manage_candidates(self):
        return self.is_hr or self.is_superadmin

    @property
    def is_checker(self):
        return self.role == self.Role.CHECKER

    def __str__(self):
        full = self.get_full_name()
        return f"{full} ({self.username})" if full else self.username


class Kind(models.TextChoices):
    """Blok va bank turi. Yakuniy ball shu tur bo'yicha hisoblanadi."""
    PRACTICAL = "practical", "Ёзма амалий топшириқ"
    LOGIC = "logic", "Мантиқий тест"
    INTERVIEW = "interview", "Суҳбат саволлари"
    OTHER = "other", "Бошқа"


class QuestionBank(models.Model):
    """Саволлар базаси (бўлим). Тестга саволлар базадан нусха қилиб қўшилади."""
    source = models.CharField("Манба ҳужжат", max_length=255, blank=True, help_text="Қайси ҳужжатдан юкланган")
    name = models.CharField("Номи", max_length=255)
    kind = models.CharField("Тури", max_length=20, choices=Kind.choices, default=Kind.PRACTICAL)
    description = models.TextField("Изоҳ / кўрсатма", blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Test(models.Model):
    class ReviewMode(models.TextChoices):
        SINGLE = "single", "Битта эксперт"
        DOUBLE = "double", "Икки мустақил эксперт (керак бўлса учинчиси)"

    title = models.CharField("Номи", max_length=255)
    description = models.TextField("Номзод учун кўрсатма", blank=True)
    is_active = models.BooleanField("Фаол", default=False, help_text="Фақат фаол тестни номзод бошлай олади")
    shuffle_questions = models.BooleanField("Саволларни аралаштириш", default=True)
    shuffle_options = models.BooleanField(
        "Вариантларни аралаштириш", default=False,
        help_text="Вариантларда бошқа вариант ҳарфига ҳавола бўлса, ўчиқ қолдиринг",
    )
    free_navigation = models.BooleanField(
        "Номзод исталган саволга қайта олсин", default=True,
        help_text="Ёқилса, барча блоклар бирданига очиқ бўлади ва вақт битта умумий таймерда ҳисобланади "
                  "(блоклар вақтининг йиғиндиси). Номзод исталган блок ва саволга қайтиб, жавобини ўзгартира олади. "
                  "Ўчирилса, блоклар кетма-кет очилади, ҳар бирининг ўз вақти бор ва ёпилган блокка қайтиб бўлмайди.",
    )
    require_photo = models.BooleanField(
        "Номзоднинг расмини олиш", default=True,
        help_text="Тест бошланишида веб-камера орқали бир марта расм олинади (номзод розилиги билан). "
                  "Камера бўлмаса, тест расмсиз давом этади. Расмни фақат суперадмин кўради.",
    )
    review_mode = models.CharField(
        "Текшириш тартиби", max_length=10, choices=ReviewMode.choices, default=ReviewMode.DOUBLE,
    )
    checkers = models.ManyToManyField(
        User, verbose_name="Экспертлар", blank=True, related_name="checker_tests",
        limit_choices_to={"role": User.Role.CHECKER},
    )
    interview_questions = models.ManyToManyField(
        "Question", verbose_name="Суҳбат саволлари", blank=True, related_name="interview_tests",
        limit_choices_to={"bank__kind": Kind.INTERVIEW},
        help_text="Барча номзодларга бир хил: одатда 3 та умумий ва 2 та касбий савол",
    )
    weight_practical = models.DecimalField("Вазн: ёзма амалий", max_digits=5, decimal_places=2, default=Decimal(55))
    weight_logic = models.DecimalField("Вазн: мантиқий тест", max_digits=5, decimal_places=2, default=Decimal(15))
    weight_interview = models.DecimalField("Вазн: суҳбат", max_digits=5, decimal_places=2, default=Decimal(15))
    weight_defense = models.DecimalField(
        "Вазн: амалий иш ҳимояси", max_digits=5, decimal_places=2, default=Decimal(15),
        help_text="Ҳимоя бали комиссия томонидан 0 дан шу қийматгача киритилади",
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_tests")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_locked(self):
        """Nomzod boshlagan testning tuzilmasini o'zgartirib bo'lmaydi."""
        return self.attempts.exists()

    @property
    def total_minutes(self):
        return self.blocks.aggregate(s=Sum("duration_minutes"))["s"] or 0

    @property
    def max_score(self):
        """Битта номзод учун максимал балл (блокдан танланадиган савол сонини ҳисобга олади)."""
        return sum((b.max_per_candidate for b in self.blocks.all()), Decimal(0))

    def max_score_for(self, kind):
        return sum((b.max_per_candidate for b in self.blocks.filter(kind=kind)), Decimal(0))

    @property
    def required_reviews(self):
        return 2 if self.review_mode == self.ReviewMode.DOUBLE else 1


class Block(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="blocks")
    title = models.CharField("Блок номи", max_length=255)
    kind = models.CharField(
        "Блок тури", max_length=20, choices=[c for c in Kind.choices if c[0] != Kind.INTERVIEW],
        default=Kind.PRACTICAL, help_text="Якуний бални ҳисоблаш учун",
    )
    description = models.TextField("Номзод учун кўрсатма", blank=True)
    duration_minutes = models.PositiveIntegerField("Вақт (дақиқа)", default=20)
    questions_per_candidate = models.PositiveIntegerField(
        "Ҳар бир номзодга нечта савол", default=0,
        help_text="0 — блокдаги барча саволлар ҳамма номзодга. Масалан 6 ёзилса, ҳар бир номзодга блокдаги "
                  "саволлардан ўзининг 6 таси тасодифий танланади (номзодларга ҳар хил савол тушади).",
    )
    order = models.PositiveIntegerField("Тартиб", default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    @property
    def pool_size(self):
        return self.questions.count()

    @property
    def per_candidate(self):
        n = self.pool_size
        return min(self.questions_per_candidate, n) if self.questions_per_candidate else n

    @property
    def is_drawn(self):
        return bool(self.questions_per_candidate) and self.questions_per_candidate < self.pool_size

    @property
    def max_per_candidate(self):
        scores = [q.max_score for q in self.questions.all()]
        if not scores:
            return Decimal(0)
        if not self.is_drawn:
            return sum(scores, Decimal(0))
        # Саволлар баллари бир хил бўлса аниқ; ҳар хил бўлса — ўртача
        return (sum(scores, Decimal(0)) / len(scores) * self.per_candidate).quantize(Decimal("0.01"))


class Question(models.Model):
    """Savol yo blokda (testning bir qismi), yo bankda turadi."""

    class Type(models.TextChoices):
        CHOICE = "choice", "Вариантли"
        TEXT = "text", "Ёзма жавоб (матн)"

    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="questions", null=True, blank=True)
    bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name="questions", null=True, blank=True)
    source = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="copies",
        help_text="Базадаги асл савол",
    )
    code = models.CharField(max_length=20, blank=True, editable=False)  # импорт учун ички калит
    title = models.CharField("Сарлавҳа", max_length=255, blank=True)
    text = models.TextField("Савол матни")
    qtype = models.CharField("Жавоб тури", max_length=10, choices=Type.choices, default=Type.CHOICE)
    max_score = models.DecimalField("Максимал балл", max_digits=6, decimal_places=2, default=Decimal("10"))
    correct_option = models.ForeignKey(
        "Option", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Тўғри вариант",
    )
    explanation = models.TextField("Калит изоҳи (фақат комиссия учун)", blank=True)
    order = models.PositiveIntegerField("Тартиб", default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or f"Савол #{self.pk}"

    @property
    def is_auto(self):
        """Kaliti bor variantli savol avtomatik baholanadi."""
        return self.qtype == self.Type.CHOICE and self.correct_option_id is not None

    @property
    def correct_letter(self):
        for i, o in enumerate(self.options.all()):
            if o.pk == self.correct_option_id:
                return OPTION_LETTERS[i]
        return ""

    def copy_to(self, block=None, bank=None, order=None):
        new = Question.objects.create(
            block=block, bank=bank, source=self if self.bank_id else self.source,
            code=self.code, title=self.title, text=self.text, qtype=self.qtype,
            max_score=self.max_score, explanation=self.explanation,
            order=self.order if order is None else order,
        )
        for o in self.options.all():
            no = new.options.create(text=o.text, order=o.order)
            if o.pk == self.correct_option_id:
                new.correct_option = no
        new.save(update_fields=["correct_option"])
        for c in self.criteria.all():
            new.criteria.create(text=c.text, max_score=c.max_score, order=c.order)
        return new


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField("Вариант", max_length=1000)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Criterion(models.Model):
    """Baholash mezoni (masalan, 0–2 ball). Nomzodga ko'rsatilmaydi."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="criteria")
    text = models.TextField("Мезон")
    max_score = models.PositiveIntegerField("Макс. балл", default=2)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Candidate(models.Model):
    last_name = models.CharField("Фамилия", max_length=100)
    first_name = models.CharField("Исм", max_length=100)
    middle_name = models.CharField("Отасининг исми", max_length=100, blank=True)
    birth_date = models.DateField("Туғилган сана", null=True, blank=True)
    birth_year = models.PositiveSmallIntegerField("Туғилган йили", null=True, blank=True)
    # Takrorlanishni aniqlash uchun normallashtirilgan kalit
    identity_key = models.CharField(max_length=400, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return " ".join(x for x in [self.last_name, self.first_name, self.middle_name] if x)

    @property
    def birth_display(self):
        if self.birth_date:
            return self.birth_date.strftime("%d.%m.%Y")
        return f"{self.birth_year} й." if self.birth_year else "—"

    @staticmethod
    def normalize(value):
        value = (value or "").strip().casefold()
        for ch in "ʻʼ‘’`´":
            value = value.replace(ch, "'")
        return " ".join(value.split())

    @classmethod
    def make_identity_key(cls, last_name, first_name, middle_name, birth):
        """birth — сана (date) ёки йил (int)."""
        born = birth.isoformat() if hasattr(birth, "isoformat") else str(birth)
        parts = [cls.normalize(last_name), cls.normalize(first_name), cls.normalize(middle_name), born]
        return "|".join(parts)


def generate_login():
    rng = random.SystemRandom()
    while True:
        login = str(rng.randint(100000, 999999))
        if not Assignment.objects.filter(login=login).exists():
            return login


def generate_password():
    # Ўхшаш рақамлар (масалан 0/8) аралашмаслиги учун фақат 2–9
    rng = random.SystemRandom()
    return "".join(rng.choice("23456789") for _ in range(6))


class Assignment(models.Model):
    """Номзоднинг қайси тестни ечиши. Рўйхатда йўқ одам тестни бошлай олмайди."""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="assignments", verbose_name="Номзод")
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="assignments", verbose_name="Тест")
    created_at = models.DateTimeField(auto_now_add=True)
    # Номзоднинг кириш маълумотлари (HR чоп этиб беради). Фақат шу тест учун, тест топширилгач ишламайди.
    login = models.CharField("Логин", max_length=12, unique=True, null=True, blank=True)
    password = models.CharField("Парол", max_length=12, blank=True)
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.login:
            self.login = generate_login()
        if not self.password:
            self.password = generate_password()
        super().save(*args, **kwargs)

    def reset_password(self):
        self.password = generate_password()
        self.failed_logins, self.locked_until = 0, None
        self.save(update_fields=["password", "failed_logins", "locked_until"])

    class Meta:
        ordering = ["candidate__last_name", "candidate__first_name"]
        constraints = [models.UniqueConstraint(fields=["candidate", "test"], name="one_assignment_per_test")]

    @property
    def attempt(self):
        return Attempt.objects.filter(candidate_id=self.candidate_id, test_id=self.test_id).first()


def generate_attempt_code():
    while True:
        code = f"K-{random.SystemRandom().randint(100000, 999999)}"
        if not Attempt.objects.filter(code=code).exists():
            return code


class Attempt(models.Model):
    """Nomzodning bitta testni yechishi. Tekshiruvchi faqat `code` ni ko'radi."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "Ечилмоқда"
        FINISHED = "finished", "Текширилмоқда"
        GRADED = "graded", "Баҳоланди"

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="attempts")
    test = models.ForeignKey(Test, on_delete=models.PROTECT, related_name="attempts")
    code = models.CharField("Аноним код", max_length=20, unique=True, default=generate_attempt_code)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Photo(models.TextChoices):
        PENDING = "", "Олинмаган"
        TAKEN = "taken", "Расм олинди"
        NO_CAMERA = "no_camera", "Камера йўқ"
        DENIED = "denied", "Камерага рухсат берилмади"
        DECLINED = "declined", "Номзод рози бўлмади"
        PURGED = "purged", "Муддати ўтиб ўчирилди"

    photo = models.CharField(max_length=100, blank=True)  # MEDIA_ROOT/photos/ ичидаги файл номи
    photo_status = models.CharField("Расм", max_length=12, choices=Photo.choices, blank=True, default="")
    photo_at = models.DateTimeField(null=True, blank=True)

    third_review_needed = models.BooleanField(default=False)
    third_review_reason = models.CharField(max_length=255, blank=True)

    # Komissiya kiritadi: {"<question_id>": [0, 2, 1, 2, 2], ...}
    interview_scores = models.JSONField(default=dict, blank=True)
    interview_comment = models.TextField("Суҳбат изоҳи", blank=True)
    defense_score = models.DecimalField("Ҳимоя бали", max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(fields=["candidate", "test"], name="one_attempt_per_candidate_per_test"),
        ]

    def __str__(self):
        return self.code

    @property
    def total_score(self):
        return self.answers.aggregate(s=Sum("score"))["s"]

    def current_block_attempt(self):
        return self.block_attempts.filter(finished_at__isnull=True).order_by("block__order", "block__id").first()

    def close_expired_blocks(self):
        """Vaqti tugagan bloklarni yopadi va keyingisini ochadi. Server vaqti asosida."""
        now = timezone.now()
        if self.test.free_navigation:
            return self._open_all_blocks(now)
        while True:
            ba = self.current_block_attempt()
            if ba is None:
                self.finish()
                return None
            if ba.started_at is None:
                ba.start()
                return ba
            if ba.deadline <= now:
                ba.finished_at = ba.deadline
                ba.save(update_fields=["finished_at"])
                continue
            return ba

    def _open_all_blocks(self, now):
        """Эркин режим: барча блоклар бир вақтда очилади, муддат — блоклар вақтининг йиғиндиси."""
        bas = list(self.block_attempts.select_related("block").order_by("block__order", "block__id"))
        total = sum(b.block.duration_minutes for b in bas)
        for b in bas:
            if b.started_at is None and b.finished_at is None:
                b.started_at = now
                b.extra_minutes += total - b.block.duration_minutes
                b.save(update_fields=["started_at", "extra_minutes"])
        open_blocks = [b for b in bas if b.finished_at is None]
        if not open_blocks or open_blocks[0].deadline <= now:
            for b in open_blocks:
                b.finished_at = min(b.deadline, now)
                b.save(update_fields=["finished_at"])
            self.finish()
            return None
        return open_blocks[0]

    def finish(self):
        from .grading import on_attempt_finished

        if self.status != self.Status.IN_PROGRESS:
            return
        now = timezone.now()
        self.block_attempts.filter(finished_at__isnull=True).update(finished_at=now)
        self.status = self.Status.FINISHED
        self.finished_at = now
        self.save(update_fields=["status", "finished_at"])
        on_attempt_finished(self)

    @property
    def photo_path(self):
        from django.conf import settings
        return settings.MEDIA_ROOT / "photos" / self.photo if self.photo else None

    def delete_photo_file(self):
        path = self.photo_path
        if path and path.exists():
            path.unlink()

    @classmethod
    def purge_old_photos(cls):
        """Сақлаш муддати ўтган расмларни ўчиради (PHOTO_RETENTION_DAYS)."""
        from django.conf import settings
        cutoff = timezone.now() - timedelta(days=settings.PHOTO_RETENTION_DAYS)
        n = 0
        for attempt in cls.objects.exclude(photo="").filter(photo_at__lt=cutoff):
            attempt.delete_photo_file()
            attempt.photo = ""
            attempt.photo_status = cls.Photo.PURGED
            attempt.save(update_fields=["photo", "photo_status"])
            n += 1
        return n

    @classmethod
    def finish_abandoned(cls, minutes=60):
        """Bloki vaqti tugaganiga `minutes` daqiqadan oshgan, lekin nomzod qaytmagan urinishlarni yakunlaydi."""
        cutoff = timezone.now() - timedelta(minutes=minutes)
        for attempt in cls.objects.filter(status=cls.Status.IN_PROGRESS):
            ba = attempt.current_block_attempt()
            if ba is None or (ba.started_at and ba.deadline <= cutoff):
                attempt.finish()


class BlockAttempt(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="block_attempts")
    block = models.ForeignKey(Block, on_delete=models.PROTECT)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    extra_minutes = models.PositiveIntegerField(default=0)
    # Nomzod uchun aralashtirilgan tartib: {"questions": [id, ...], "options": {"qid": [id, ...]}}
    layout = models.JSONField(default=dict)

    class Meta:
        ordering = ["block__order", "block__id"]
        constraints = [models.UniqueConstraint(fields=["attempt", "block"], name="one_block_attempt")]

    @property
    def deadline(self):
        if not self.started_at:
            return None
        return self.started_at + timedelta(minutes=self.block.duration_minutes + self.extra_minutes)

    def start(self):
        self.started_at = timezone.now()
        self.save(update_fields=["started_at"])

    def seconds_left(self):
        if not self.started_at:
            return self.block.duration_minutes * 60
        return max(0, int((self.deadline - timezone.now()).total_seconds()))


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    selected_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True)
    text_answer = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Yakuniy ball: kalit bo'yicha avtomatik yoki ekspertlar baholaridan hisoblanadi
    score = models.DecimalField("Балл", max_digits=6, decimal_places=2, null=True, blank=True)
    auto_graded = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")]

    @property
    def is_empty(self):
        return self.selected_option_id is None and not self.text_answer


class Review(models.Model):
    """Bitta ekspertning bitta nomzod ishini mustaqil tekshirishi."""
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="reviews")
    checker = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reviews")
    round = models.PositiveSmallIntegerField("Текширув", default=1)
    assigned_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["round", "id"]
        constraints = [models.UniqueConstraint(fields=["attempt", "checker"], name="one_review_per_checker")]

    @property
    def is_submitted(self):
        return self.submitted_at is not None


class ReviewAnswer(models.Model):
    """Ekspertning bitta javobga qo'ygan mezon ballari: [M1, M2, ...] yoki mezon bo'lmasa [ball]."""
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="items")
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="review_items")
    scores = models.JSONField(default=list)
    comment = models.TextField("Баллнинг қисқа асоси", blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["review", "answer"], name="one_item_per_review_answer")]

    @property
    def total(self):
        if not self.scores or any(s is None for s in self.scores):
            return None
        return sum(Decimal(str(s)) for s in self.scores)


from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=Attempt)
def _remove_photo(sender, instance, **kwargs):
    instance.delete_photo_file()
