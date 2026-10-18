import hashlib
import json
import os
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import grading
from .models import Assignment, Attempt, Candidate, Kind, Question, QuestionBank, Review, Test, User

DOCX = os.environ.get(
    "TANLOV_DOCX", os.path.expanduser("~/Downloads/Hisob_palatasi_tanlov_materiallari_uz_kirill.docx")
)


class Base(TestCase):
    review_mode = Test.ReviewMode.DOUBLE

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # кириш уринишлари ҳисоблагичи тестлар орасида тўпланмасин
        self.admin = User.objects.create_user("admin", password="x" * 10, role=User.Role.SUPERADMIN)
        self.author = User.objects.create_user("author", password="x" * 10, role=User.Role.AUTHOR)
        self.c1 = User.objects.create_user("c1", password="x" * 10, role=User.Role.CHECKER)
        self.c2 = User.objects.create_user("c2", password="x" * 10, role=User.Role.CHECKER)
        self.c3 = User.objects.create_user("c3", password="x" * 10, role=User.Role.CHECKER)

        # Bank: suhbat savoli
        iv_bank = QuestionBank.objects.create(name="Suhbat", kind=Kind.INTERVIEW)
        self.iv = Question.objects.create(bank=iv_bank, code="С 01", title="Bosim", text="<p>?</p>", qtype="text", max_score=10)
        for i in range(5):
            self.iv.criteria.create(text=f"m{i}", max_score=2, order=i)

        self.client.force_login(self.author)
        self.client.post(reverse("test_create"), {
            "title": "Auditor", "is_active": "on", "shuffle_questions": "on", "review_mode": self.review_mode,
            "interview_questions": [self.iv.pk],
            "weight_practical": 55, "weight_logic": 15, "weight_interview": 15, "weight_defense": 15,
        })
        self.test = Test.objects.get()
        self.client.post(reverse("block_create", args=[self.test.pk]),
                         {"title": "Mantiq", "kind": "logic", "duration_minutes": 40, "order": 1})
        self.client.post(reverse("block_create", args=[self.test.pk]),
                         {"title": "Amaliy", "kind": "practical", "duration_minutes": 180, "order": 2})
        self.logic, self.practical = self.test.blocks.all()

        r = self.client.post(reverse("question_create", args=[self.logic.pk]), {
            "text": "<p>2+2?</p><script>alert(1)</script>", "qtype": "choice", "order": 1,
            "options_text": "3\n4\n5\n6\n7", "correct_number": 2,
        })
        self.assertEqual(r.status_code, 302, r.content[:2000])
        self.client.post(reverse("question_create", args=[self.logic.pk]), {
            "text": "<p>3+3?</p>", "qtype": "choice", "order": 2, "options_text": "5\n6\n7", "correct_number": 2,
        })
        for code in ("МА 01", "МА 02"):
            r = self.client.post(reverse("question_create", args=[self.practical.pk]), {
                "title": f"Vazifa {code}", "text": f"<p>{code} sharti</p>", "qtype": "text", "order": 1,
                "criteria_text": "a\nb\nc\nd\ne",
            })
            self.assertEqual(r.status_code, 302)
        self.test.checkers.set([self.c1, self.c2, self.c3])
        self.client.logout()

        self.q_logic1, self.q_logic2 = self.logic.questions.all()
        self.q_ma1, self.q_ma2 = self.practical.questions.all()
        self.assignment = self.register("Karimov", "Aziz", "Olimovich", "1995")

    def register(self, last, first, middle, born, test=None):
        self.client.force_login(self.admin)
        self.client.post(reverse("candidate_add"), {
            "last_name": last, "first_name": first, "middle_name": middle, "birth": born,
            "test": (test or self.test).pk,
        })
        self.client.logout()
        return Assignment.objects.get(candidate__last_name=last, candidate__first_name=first, test=test or self.test)

    def login_candidate(self, client=None, login=None, password=None, assignment=None):
        a = assignment or self.assignment
        data = {"login": login or a.login, "password": password or a.password}
        return (client or self.client).post(reverse("exam_login"), data)

    def save(self, payload):
        return self.client.post(reverse("exam_save"), json.dumps(payload), content_type="application/json")

    def take_test(self, logic_correct=True):
        self.login_candidate()
        self.client.get(reverse("exam_take"))
        opt = self.q_logic1.options.get(text="4" if logic_correct else "3")
        self.assertTrue(self.save({"question": self.q_logic1.pk, "option": opt.pk}).json()["ok"])
        attempt = Attempt.objects.get()
        self.client.post(reverse("exam_next"), {"block_attempt": attempt.block_attempts.first().pk})
        self.client.get(reverse("exam_take"))
        self.assertTrue(self.save({"question": self.q_ma1.pk, "text": "<p>Javob 475</p>"}).json()["ok"])
        self.assertTrue(self.save({"question": self.q_ma2.pk, "text": "<p>Ikkinchi</p>"}).json()["ok"])
        self.client.post(reverse("exam_next"), {"block_attempt": attempt.block_attempts.last().pk})
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.FINISHED)
        self.client.get(reverse("exam_done"))
        return attempt

    def grade(self, checker, attempt, scores_by_question, submit=True):
        """scores_by_question: {question: [m1..m5]}"""
        self.client.force_login(checker)
        post = {"submit": "1"} if submit else {"save": "1"}
        for q, scores in scores_by_question.items():
            a = attempt.answers.get(question=q)
            for i, s in enumerate(scores):
                post[f"s_{a.pk}_{i}"] = "" if s is None else str(s)
            post[f"c_{a.pk}"] = f"izoh-{checker.username}"
        return self.client.post(reverse("check_attempt", args=[attempt.code]), post)


class FlowTests(Base):
    def test_question_form_parses_key_and_criteria(self):
        self.assertNotIn("<script", self.q_logic1.text)
        self.assertEqual(self.q_logic1.correct_option.text, "4")
        self.assertEqual(self.q_logic1.max_score, 1)
        self.assertTrue(self.q_logic1.is_auto)
        self.assertEqual(self.q_ma1.criteria.count(), 5)
        self.assertEqual(self.q_ma1.max_score, 10)
        self.assertEqual(self.test.max_score_for(Kind.PRACTICAL), 20)

    def test_candidate_sees_letters_not_key_or_criteria(self):
        self.login_candidate()
        r = self.client.get(reverse("exam_take"))
        self.assertContains(r, 'class="letter">А<')
        self.assertContains(r, 'class="letter">Д<')
        self.assertNotContains(r, "to&#x27;g&#x27;ri")
        self.assertNotContains(r, "kalit")

    def test_double_review_average(self):
        attempt = self.take_test()
        # Mantiqiy: 1 to'g'ri, 1 bo'sh -> avtomatik
        self.assertEqual(attempt.answers.get(question=self.q_logic1).score, 1)
        self.assertEqual(attempt.answers.get(question=self.q_logic2).score, 0)
        reviews = list(attempt.reviews.all())
        self.assertEqual(len(reviews), 2)
        first, second = [r.checker for r in reviews]

        # Ekspert ism ko'rmaydi
        self.client.force_login(first)
        r = self.client.get(reverse("check_attempt", args=[attempt.code]))
        self.assertContains(r, "Javob 475")
        self.assertNotContains(r, "<td>М1")
        self.assertNotContains(r, "Karimov")
        self.assertNotContains(r, "1995")
        self.assertNotContains(r, "2+2")  # avtomatik savollar ko'rsatilmaydi

        # Topshirish uchun hamma mezon kerak
        r = self.grade(first, attempt, {self.q_ma1: [2, 2, 2, 2, None], self.q_ma2: [1] * 5}, submit=True)
        self.assertFalse(Review.objects.get(attempt=attempt, checker=first).is_submitted)

        self.grade(first, attempt, {self.q_ma1: [2, 2, 2, 2, 1], self.q_ma2: [1] * 5})
        self.assertTrue(Review.objects.get(attempt=attempt, checker=first).is_submitted)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.FINISHED)

        # Topshirilgandan keyin o'zgartirib bo'lmaydi
        self.grade(first, attempt, {self.q_ma1: [0] * 5, self.q_ma2: [0] * 5})
        self.assertEqual(Review.objects.get(attempt=attempt, checker=first).items.get(answer__question=self.q_ma1).scores, [2, 2, 2, 2, 1])

        # Ikkinchi ekspert birinchisining balini ko'rmaydi
        self.client.force_login(second)
        r = self.client.get(reverse("check_attempt", args=[attempt.code]))
        self.assertNotContains(r, f"izoh-{first.username}")
        self.assertNotContains(r, 'selected>2')
        self.grade(second, attempt, {self.q_ma1: [2, 1, 2, 2, 2], self.q_ma2: [1, 1, 1, 2, 1]})

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.GRADED)
        self.assertFalse(attempt.third_review_needed)
        # MA1: (9 + 9) / 2 = 9; MA2: (5 + 6) / 2 = 5.5
        self.assertEqual(attempt.answers.get(question=self.q_ma1).score, Decimal("9"))
        self.assertEqual(attempt.answers.get(question=self.q_ma2).score, Decimal("5.5"))

        # Yakuniy: amaliy 55*14.5/20 = 39.88, mantiqiy 15*1/2 = 7.5; suhbat va himoya yo'q -> final None
        s = grading.summary(attempt)
        self.assertEqual(s["practical"]["weighted"], Decimal("39.88"))
        self.assertEqual(s["logic"]["weighted"], Decimal("7.50"))
        self.assertIsNone(s["final"])

        # Superadmin suhbat va himoyani kiritadi
        self.client.force_login(self.admin)
        post = {"action": "interview", "defense_score": "12"}
        for i, v in enumerate([2, 2, 1, 2, 1]):
            post[f"iv_{self.iv.pk}_{i}"] = str(v)
        self.client.post(reverse("result_action", args=[attempt.pk]), post)
        attempt.refresh_from_db()
        s = grading.summary(attempt)
        self.assertEqual(s["interview"]["score"], 8)
        self.assertEqual(s["final"], Decimal("39.88") + Decimal("7.50") + Decimal("12.00") + Decimal("12"))

        r = self.client.get(reverse("results"))
        self.assertContains(r, "Karimov Aziz Olimovich")
        r = self.client.get(reverse("result_detail", args=[attempt.pk]))
        self.assertContains(r, "Эксп. 2")
        r = self.client.get(reverse("results_export"))
        self.assertTrue(r.content.startswith(b"PK"))

    def test_third_review_on_large_difference_uses_median(self):
        attempt = self.take_test()
        first, second = [r.checker for r in attempt.reviews.all()]
        self.grade(first, attempt, {self.q_ma1: [2, 2, 2, 2, 2], self.q_ma2: [2, 2, 2, 1, 1]})
        self.grade(second, attempt, {self.q_ma1: [1, 1, 1, 1, 1], self.q_ma2: [1, 1, 1, 1, 1]})
        attempt.refresh_from_db()
        # Farq 18 - 10 = 8 > 20 * 15% = 3
        self.assertTrue(attempt.third_review_needed)
        self.assertIn("фарқи", attempt.third_review_reason)
        self.assertEqual(attempt.status, Attempt.Status.FINISHED)
        third = attempt.reviews.get(round=3)
        self.assertNotIn(third.checker, (first, second))
        self.grade(third.checker, attempt, {self.q_ma1: [1, 2, 1, 2, 1], self.q_ma2: [1, 2, 2, 2, 1]})
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.GRADED)
        # MA1 mediana: [2,1,1]=1, [2,1,2]=2, [2,1,1]=1, [2,1,2]=2, [2,1,1]=1 -> 7
        self.assertEqual(attempt.answers.get(question=self.q_ma1).score, 7)
        # MA2: [2,1,1]=1, [2,1,2]=2, [2,1,2]=2, [1,1,2]=1, [1,1,1]=1 -> 7
        self.assertEqual(attempt.answers.get(question=self.q_ma2).score, 7)

    def test_third_review_on_zero_vs_two(self):
        attempt = self.take_test()
        first, second = [r.checker for r in attempt.reviews.all()]
        self.grade(first, attempt, {self.q_ma1: [2, 2, 2, 2, 0], self.q_ma2: [1] * 5})
        self.grade(second, attempt, {self.q_ma1: [2, 2, 2, 2, 2], self.q_ma2: [1] * 5})
        attempt.refresh_from_db()
        self.assertTrue(attempt.third_review_needed)
        self.assertIn("Vazifa МА 01", attempt.third_review_reason)

    def test_superadmin_reopen_and_add_reviewer(self):
        attempt = self.take_test()
        first, second = [r.checker for r in attempt.reviews.all()]
        self.grade(first, attempt, {self.q_ma1: [2] * 5, self.q_ma2: [2] * 5})
        review = attempt.reviews.get(checker=first)
        self.client.force_login(self.admin)
        self.client.post(reverse("result_action", args=[attempt.pk]), {"action": "reopen_review", "review": review.pk})
        review.refresh_from_db()
        self.assertFalse(review.is_submitted)
        r2 = attempt.reviews.get(checker=second)
        self.client.post(reverse("result_action", args=[attempt.pk]), {"action": "delete_review", "review": r2.pk})
        third = (set([self.c1, self.c2, self.c3]) - {first, second}).pop()
        self.client.post(reverse("result_action", args=[attempt.pk]), {"action": "add_review", "checker": third.pk})
        self.assertTrue(attempt.reviews.filter(checker=third).exists())

    def test_checker_isolation_and_roles(self):
        attempt = self.take_test()
        reviewers = {r.checker for r in attempt.reviews.all()}
        outsider = ({self.c1, self.c2, self.c3} - reviewers).pop()
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("check_attempt", args=[attempt.code])).status_code, 404)
        self.assertEqual(self.client.get(reverse("results")).status_code, 403)
        self.assertEqual(self.client.get(reverse("test_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("bank_list")).status_code, 403)
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("check_list")).status_code, 403)

    def test_duplicate_blocked_and_lock(self):
        self.take_test()
        r = self.login_candidate()
        self.assertContains(r, "суперадмин рухсати")
        self.client.force_login(self.author)
        r = self.client.get(reverse("question_edit", args=[self.q_ma1.pk]))
        self.assertRedirects(r, reverse("test_detail", args=[self.test.pk]))

    def test_block_timer_expires_on_server(self):
        self.login_candidate()
        self.client.get(reverse("exam_take"))
        attempt = Attempt.objects.get()
        ba1 = attempt.block_attempts.first()
        ba1.started_at = timezone.now() - timedelta(minutes=41)
        ba1.save()
        opt = self.q_logic1.options.first()
        self.assertEqual(self.save({"question": self.q_logic1.pk, "option": opt.pk}).status_code, 409)
        r = self.client.get(reverse("exam_take"))
        self.assertContains(r, "Amaliy")

    def test_resume_after_restart(self):
        self.login_candidate()
        self.client.get(reverse("exam_take"))
        r = self.login_candidate(client=self.client_class())
        self.assertRedirects(r, reverse("exam_take"))
        self.assertEqual(Attempt.objects.count(), 1)

    def test_weights_must_sum_to_100(self):
        self.client.force_login(self.author)
        r = self.client.post(reverse("test_edit", args=[self.test.pk]), {
            "title": "X", "review_mode": "single",
            "weight_practical": 50, "weight_logic": 15, "weight_interview": 15, "weight_defense": 15,
        })
        self.assertContains(r, "100 бўлиши керак")

    def test_copy_test(self):
        self.take_test()
        self.client.force_login(self.author)
        self.client.post(reverse("test_copy", args=[self.test.pk]))
        copy = Test.objects.exclude(pk=self.test.pk).get()
        self.assertFalse(copy.is_active)
        self.assertEqual(copy.max_score, self.test.max_score)
        q = Question.objects.get(block__test=copy, title="Vazifa МА 01")
        self.assertEqual(q.criteria.count(), 5)
        q = Question.objects.filter(block__test=copy, qtype="choice").first()
        self.assertEqual(q.correct_option.question, q)
        self.assertEqual([x.pk for x in copy.interview_questions.all()], [self.iv.pk])

    def test_bank_pick(self):
        bank = QuestionBank.objects.create(name="MA", kind=Kind.PRACTICAL)
        src = Question.objects.create(bank=bank, code="МА 07", title="Kredit", text="<p>t</p>", qtype="text", max_score=10)
        src.criteria.create(text="x", max_score=2)
        self.client.force_login(self.author)
        r = self.client.get(reverse("block_add_from_bank", args=[self.practical.pk]) + f"?bank={bank.pk}")
        self.assertContains(r, "Kredit")
        self.client.post(reverse("block_add_from_bank", args=[self.practical.pk]), {"bank": bank.pk, "questions": [src.pk]})
        copy = self.practical.questions.get(title="Kredit")
        self.assertEqual(copy.source, src)
        self.assertEqual(copy.criteria.count(), 1)
        # Bankdagi o'zgarish nusxaga ta'sir qilmaydi
        src.title = "Boshqa"
        src.save()
        copy.refresh_from_db()
        self.assertEqual(copy.title, "Kredit")


class SingleReviewTests(Base):
    review_mode = Test.ReviewMode.SINGLE

    def test_single_review(self):
        attempt = self.take_test(logic_correct=False)
        self.assertEqual(attempt.reviews.count(), 1)
        self.assertEqual(attempt.answers.get(question=self.q_logic1).score, 0)
        checker = attempt.reviews.get().checker
        self.grade(checker, attempt, {self.q_ma1: [2, 2, 2, 2, 2], self.q_ma2: [0, 0, 0, 0, 0]})
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.GRADED)
        self.assertEqual(attempt.total_score, 10)


class SebTests(Base):
    @override_settings(REQUIRE_SEB=True)
    def test_seb_required(self):
        self.assertEqual(self.client.get(reverse("exam_login")).status_code, 403)
        r = self.client.get(reverse("exam_login"), HTTP_USER_AGENT="Mozilla/5.0 SEB/3.7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("staff_login")).status_code, 200)

    @override_settings(SEB_CONFIG_KEYS=["abc123"])
    def test_seb_config_key(self):
        url = "http://testserver" + reverse("exam_login")
        good = hashlib.sha256((url + "abc123").encode()).hexdigest()
        self.assertEqual(self.client.get(reverse("exam_login")).status_code, 403)
        self.assertEqual(self.client.get(reverse("exam_login"), HTTP_X_SAFEEXAMBROWSER_CONFIGKEYHASH=good).status_code, 200)


class ImportTests(TestCase):
    def setUp(self):
        if not os.path.exists(DOCX):
            self.skipTest("Tanlov materiallari fayli topilmadi")
        User.objects.create_user("admin", password="x" * 10, role=User.Role.SUPERADMIN)

    def test_import(self):
        call_command("import_tanlov", DOCX, verbosity=0)
        self.assertEqual(Question.objects.filter(bank__isnull=False).count(), 220)
        self.assertEqual(Question.objects.filter(bank__kind=Kind.LOGIC, correct_option__isnull=False).count(), 100)
        self.assertEqual(Test.objects.count(), 2)
        for t in Test.objects.all():
            self.assertEqual(t.max_score_for(Kind.LOGIC), 20)
            self.assertEqual(t.max_score_for(Kind.PRACTICAL), 60)
            self.assertEqual(t.interview_questions.count(), 5)
            self.assertEqual(t.total_minutes, 220)
        # Kodlar (МА 01, Т1-01) ekranda ko'rinmaydi
        admin = User.objects.get(username="admin")
        self.client.force_login(admin)
        t = Test.objects.get(title__startswith="Молиявий")
        r = self.client.get(reverse("test_detail", args=[t.pk]))
        self.assertContains(r, "Банк қолдиғини солиштириш")
        self.assertNotContains(r, "МА 01")
        self.assertNotContains(r, "Т1-01")
        # Qayta import — dublikat yo'q
        call_command("import_tanlov", DOCX, verbosity=0)
        self.assertEqual(Question.objects.filter(bank__isnull=False).count(), 220)
        self.assertEqual(Test.objects.count(), 2)


class SessionTests(Base):
    def test_candidate_login_drops_staff_session(self):
        self.client.force_login(self.admin)
        self.login_candidate()
        self.assertEqual(self.client.get(reverse("results")).status_code, 302)
        self.assertEqual(self.client.get(reverse("exam_take")).status_code, 200)


class RegistrationTests(Base):
    def test_credentials_generated(self):
        a = self.assignment
        self.assertRegex(a.login, r"^\d{6}$")
        self.assertRegex(a.password, r"^[2-9]{6}$")
        self.assertEqual(a.candidate.birth_year, 1995)
        self.assertIsNone(a.candidate.birth_date)

    def test_wrong_password_and_lock(self):
        r = self.login_candidate(password="000000")
        self.assertContains(r, "Логин ёки парол нотўғри")
        r = self.login_candidate(login="999999")
        self.assertContains(r, "Логин ёки парол нотўғри")
        for _ in range(5):
            self.login_candidate(password="000000")
        r = self.login_candidate()  # тўғри парол ҳам блокланган
        self.assertContains(r, "кўп марта нотўғри")
        self.assertEqual(Attempt.objects.count(), 0)

    def test_inactive_test_rejected(self):
        self.test.is_active = False
        self.test.save()
        r = self.login_candidate()
        self.assertContains(r, "ҳали очилмаган")

    def test_each_test_has_own_login(self):
        other = Test.objects.create(title="Tahlilchi", is_active=True, created_by=self.admin, require_photo=False)
        other.blocks.create(title="B", kind="logic", duration_minutes=5)
        a2 = self.register("Karimov", "Aziz", "Olimovich", "1995", test=other)
        self.assertNotEqual(a2.login, self.assignment.login)
        r = self.login_candidate(assignment=a2)
        self.assertRedirects(r, reverse("exam_take"))
        self.assertEqual(Attempt.objects.get().test, other)

    def test_retake_needs_superadmin(self):
        attempt = self.take_test()
        r = self.login_candidate()
        self.assertContains(r, "суперадмин рухсати")
        hr = User.objects.create_user("hr", password="x" * 10, role=User.Role.HR)
        self.client.force_login(hr)
        self.assertEqual(self.client.post(reverse("result_action", args=[attempt.pk]), {"action": "delete"}).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(reverse("result_action", args=[attempt.pk]), {"action": "delete"})
        self.client.logout()
        self.assertRedirects(self.login_candidate(), reverse("exam_take"))

    def test_hr_role(self):
        hr = User.objects.create_user("hr", password="x" * 10, role=User.Role.HR)
        self.client.force_login(hr)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("candidate_list"))
        r = self.client.get(reverse("candidate_list"))
        self.assertContains(r, self.assignment.login)
        self.assertContains(r, self.assignment.password)
        for name in ("results", "test_list", "bank_list", "user_list", "check_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.client.post(reverse("candidate_add"), {"last_name": "Ali", "first_name": "Vali", "middle_name": "",
                                                    "birth": "12.04.1994", "test": self.test.pk})
        new = Assignment.objects.get(candidate__last_name="Ali")
        self.assertEqual(new.candidate.birth_year, 1994)
        r = self.client.get(reverse("candidate_print") + f"?test={self.test.pk}")
        self.assertContains(r, new.login)
        self.assertContains(r, new.password)
        self.assertContains(r, "Ali Vali")
        old = new.password
        self.client.post(reverse("assignment_reset_password", args=[new.pk]))
        new.refresh_from_db()
        self.assertNotEqual(new.password, old)

    def test_print_skips_finished(self):
        self.take_test()
        self.client.force_login(self.admin)
        r = self.client.get(reverse("candidate_print") + f"?test={self.test.pk}")
        self.assertNotContains(r, self.assignment.password)
        r = self.client.get(reverse("candidate_print") + f"?id={self.assignment.pk}")
        self.assertContains(r, "тестни топшириб бўлган")

    def test_excel_import(self):
        from io import BytesIO

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Фамилия", "Исм", "Отасининг исми", "Туғилган йили"])
        ws.append(["Тошматов", "Бобур", "Акмалович", 1993])
        ws.append(["Каримова", "Нилуфар", "", "11.02.1996"])
        ws.append([None, None, None, None])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "list.xlsx"
        self.client.force_login(self.admin)
        self.client.post(reverse("candidate_import"), {"file": buf, "test": self.test.pk})
        self.assertEqual(Assignment.objects.filter(test=self.test).count(), 3)
        self.client.logout()
        a = Assignment.objects.get(candidate__last_name="Тошматов")
        self.assertEqual(a.candidate.birth_year, 1993)
        self.assertRedirects(self.login_candidate(assignment=a), reverse("exam_take"))

    def test_assignment_delete_only_before_start(self):
        x = Assignment.objects.get()
        self.login_candidate()
        self.client.force_login(self.admin)
        self.client.post(reverse("assignment_delete", args=[x.pk]))
        self.assertTrue(Assignment.objects.filter(pk=x.pk).exists())


class EditorContentTests(Base):
    def test_sanitizers(self):
        from .utils import clean_answer, clean_html
        html = ('<h3 style="text-align:center;position:fixed">S</h3><p style="color:#b91c1c">r</p>'
                '<pre>x = 1</pre><img src="/media/questions/a.png"><img src="http://evil/x.png">'
                '<a href="http://x">l</a><table border="1"><tr><td style="width:50%">c</td></tr></table>')
        author = clean_html(html)
        self.assertIn('text-align:center', author)
        self.assertNotIn('position', author)
        self.assertIn('color:#b91c1c', author)
        self.assertIn('<pre>', author)
        self.assertIn('src="/media/questions/a.png"', author)
        self.assertNotIn('evil', author)
        self.assertNotIn('<a', author)
        answer = clean_answer(html)
        self.assertNotIn('<img', answer)
        self.assertIn('<table', answer)

    def test_image_upload(self):
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        with tempfile.TemporaryDirectory() as tmp, self.settings(MEDIA_ROOT=__import__("pathlib").Path(tmp)):
            self.client.force_login(self.c1)
            r = self.client.post(reverse("upload_image"), {"file": SimpleUploadedFile("a.png", png)})
            self.assertEqual(r.status_code, 403)
            self.client.force_login(self.author)
            r = self.client.post(reverse("upload_image"), {"file": SimpleUploadedFile("a.png", png)})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["location"].startswith("/media/questions/"))
            r = self.client.post(reverse("upload_image"), {"file": SimpleUploadedFile("a.png", b"<script>")})
            self.assertEqual(r.status_code, 400)


class TemplateVarTests(Base):
    def test_bank_pick_breadcrumb(self):
        self.client.force_login(self.author)
        r = self.client.get(reverse("block_add_from_bank", args=[self.practical.pk]))
        self.assertContains(r, "Amaliy")
        self.assertNotContains(r, "BlockNode")


class FreeNavigationTests(Base):
    def setUp(self):
        super().setUp()
        self.test.free_navigation = True
        self.test.save()

    def test_all_blocks_open_and_editable(self):
        self.login_candidate()
        r = self.client.get(reverse("exam_take"))
        # Иккала блок саволлари бир саҳифада
        self.assertContains(r, "2+2?")
        self.assertContains(r, "МА 02 sharti")
        attempt = Attempt.objects.get()
        deadlines = {ba.deadline for ba in attempt.block_attempts.all()}
        self.assertEqual(len(deadlines), 1)  # битта умумий муддат
        total = (deadlines.pop() - attempt.block_attempts.first().started_at).total_seconds() / 60
        self.assertAlmostEqual(total, 220, delta=0.1)
        # Аввал амалий, кейин мантиқий саволга қайтиб жавоб ўзгартириш
        self.assertTrue(self.save({"question": self.q_ma2.pk, "text": "<p>javob</p>"}).json()["ok"])
        opt = self.q_logic1.options.get(text="4")
        self.assertTrue(self.save({"question": self.q_logic1.pk, "option": opt.pk}).json()["ok"])
        opt = self.q_logic1.options.get(text="5")
        self.assertTrue(self.save({"question": self.q_logic1.pk, "option": opt.pk}).json()["ok"])
        # Якунлаш бутун тестни топширади
        self.client.post(reverse("exam_next"), {"block_attempt": attempt.block_attempts.first().pk})
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.FINISHED)
        self.assertEqual(attempt.answers.get(question=self.q_logic1).score, 0)

    def test_total_time_expires(self):
        self.login_candidate()
        self.client.get(reverse("exam_take"))
        attempt = Attempt.objects.get()
        attempt.block_attempts.update(started_at=timezone.now() - timedelta(minutes=221))
        self.client.get(reverse("exam_take"))
        attempt.refresh_from_db()
        self.assertNotEqual(attempt.status, Attempt.Status.IN_PROGRESS)
        self.assertFalse(attempt.block_attempts.filter(finished_at__isnull=True).exists())

    def test_extend_all_blocks(self):
        self.login_candidate()
        self.client.get(reverse("exam_take"))
        attempt = Attempt.objects.get()
        self.client.force_login(self.admin)
        self.client.post(reverse("result_action", args=[attempt.pk]), {"action": "extend", "minutes": 10})
        self.assertEqual(len({ba.deadline for ba in attempt.block_attempts.all()}), 1)


class SetupAndUnlockTests(Base):
    def test_checklist_and_presets(self):
        self.client.force_login(self.author)
        t = Test.objects.create(title="Yangi", created_by=self.author)
        r = self.client.get(reverse("test_detail", args=[t.pk]))
        self.assertContains(r, "Тестни тайёрлаш")
        r = self.client.get(reverse("block_create", args=[t.pk]) + "?preset=logic")
        self.assertContains(r, "Мантиқий фикрлаш тести")
        r = self.client.post(reverse("block_create", args=[t.pk]), {"title": "", "kind": "logic", "duration_minutes": 40, "order": 1})
        self.assertContains(r, "Бу майдонни тўлдиринг")

    def test_unlock(self):
        self.login_candidate()
        self.client.get(reverse("exam_take"))
        self.assertTrue(self.test.is_locked)
        self.client.force_login(self.author)
        self.assertEqual(self.client.post(reverse("test_unlock", args=[self.test.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(reverse("test_unlock", args=[self.test.pk]))
        self.assertFalse(self.test.is_locked)
        self.assertTrue(Assignment.objects.filter(test=self.test).exists())  # рўйхат сақланади


class PhotoTests(Base):
    JPEG = "data:image/jpeg;base64," + __import__("base64").b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()

    def setUp(self):
        super().setUp()
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.media = self.settings(MEDIA_ROOT=Path(self.tmp.name))
        self.media.enable()
        self.test.require_photo = True
        self.test.save()

    def tearDown(self):
        self.media.disable()
        self.tmp.cleanup()

    def post_photo(self, payload):
        return self.client.post(reverse("exam_photo_save"), json.dumps(payload), content_type="application/json")

    def test_photo_flow_and_privacy(self):
        self.login_candidate()
        self.assertRedirects(self.client.get(reverse("exam_take")), reverse("exam_photo"))
        self.assertContains(self.client.get(reverse("exam_photo")), "Шахсни тасдиқлаш")
        self.assertEqual(self.post_photo({"image": "data:image/jpeg;base64,PHNjcmlwdD4="}).status_code, 400)
        self.assertTrue(self.post_photo({"image": self.JPEG}).json()["ok"])
        attempt = Attempt.objects.get()
        self.assertEqual(attempt.photo_status, "taken")
        self.assertTrue(attempt.photo_path.exists())
        self.assertEqual(self.client.get(reverse("exam_take")).status_code, 200)

        # Тестни якунлаб, экспертга юборамиз
        ba1, ba2 = attempt.block_attempts.all()
        self.client.post(reverse("exam_next"), {"block_attempt": ba1.pk})
        self.client.get(reverse("exam_take"))
        self.assertTrue(self.save({"question": self.q_ma1.pk, "text": "<p>javob</p>"}).json()["ok"])
        self.client.post(reverse("exam_next"), {"block_attempt": ba2.pk})
        attempt.refresh_from_db()
        url = reverse("result_photo", args=[attempt.pk])
        checker = attempt.reviews.first().checker
        self.client.force_login(checker)
        self.assertNotContains(self.client.get(reverse("check_attempt", args=[attempt.code])), url)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("result_detail", args=[attempt.pk])), url)

        path = attempt.photo_path
        attempt.delete()
        self.assertFalse(path.exists())

    def test_no_camera_continues(self):
        self.login_candidate()
        self.assertTrue(self.post_photo({"status": "no_camera"}).json()["ok"])
        self.assertEqual(self.client.get(reverse("exam_take")).status_code, 200)
        self.assertEqual(Attempt.objects.get().photo_status, "no_camera")

    def test_purge(self):
        self.login_candidate()
        self.post_photo({"image": self.JPEG})
        attempt = Attempt.objects.get()
        Attempt.objects.filter(pk=attempt.pk).update(photo_at=timezone.now() - timedelta(days=181))
        self.assertEqual(Attempt.purge_old_photos(), 1)
        attempt.refresh_from_db()
        self.assertEqual((attempt.photo, attempt.photo_status), ("", "purged"))


def make_docx(title="Ички аудит танлови", logic_key="Б", code="ИТ"):
    from io import BytesIO

    import docx
    d = docx.Document()
    d.add_paragraph(title, style="Title")
    d.add_paragraph("Ички аудитор учун амалий топшириқлар", style="Heading 1")
    d.add_paragraph("Кириш матни.")
    d.add_paragraph(f"{code} 01 Тармоқ хавфсизлиги", style="Heading 2")
    d.add_paragraph("Тармоқдаги хавфни баҳоланг.")
    d.add_paragraph("1. Хавфни аниқлайди. 2 балл")
    d.add_paragraph("2. Чора таклиф этади. 3 балл")
    d.add_paragraph("1 тўплам", style="Heading 1")
    d.add_paragraph("1. 2+2 нечага тенг?")
    d.add_paragraph("А) 3     Б) 4     В) 5")
    d.add_paragraph("Тест жавоблари ва изоҳлари", style="Heading 1")
    d.add_paragraph("1 тўплам калити", style="Heading 2")
    t = d.add_table(rows=2, cols=4)
    for i, v in enumerate(["№", "Тўғри", "Яқин вариантлар", "Қисқа изоҳ"]):
        t.rows[0].cells[i].text = v
    for i, v in enumerate(["1", logic_key, "А, В", "Оддий қўшиш"]):
        t.rows[1].cells[i].text = v
    buf = BytesIO()
    d.save(buf)
    buf.seek(0)
    buf.name = "hujjat.docx"
    return buf


class WebImportTests(Base):
    def setUp(self):
        super().setUp()
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.media = self.settings(MEDIA_ROOT=Path(self.tmp.name))
        self.media.enable()
        self.client.force_login(self.author)

    def tearDown(self):
        self.media.disable()
        self.tmp.cleanup()

    def upload(self, buf, source=None):
        r = self.client.post(reverse("bank_import"), {"step": "check", "file": buf})
        self.assertEqual(r.status_code, 200)
        token = r.context.get("token")
        if r.context["parsed"].errors:
            return r, None
        r2 = self.client.post(reverse("bank_import"), {"step": "import", "token": token,
                                                       "source": source or r.context["source"]})
        return r, r2

    def test_check_then_import(self):
        r, r2 = self.upload(make_docx())
        self.assertContains(r, "Юклашга тайёр")
        self.assertContains(r, "Ички аудитор учун амалий топшириқлар")
        self.assertRedirects(r2, reverse("bank_list"))
        banks = QuestionBank.objects.filter(source="Ички аудит танлови")
        self.assertEqual(banks.count(), 2)
        task = Question.objects.get(bank__source="Ички аудит танлови", code="ИТ 01")
        self.assertEqual(task.max_score, 5)
        self.assertEqual(task.criteria.count(), 2)
        logic = Question.objects.get(bank__source="Ички аудит танлови", qtype="choice")
        self.assertEqual(logic.correct_option.text, "4")
        # Қайта юклаш — дубликат йўқ, калит янгиланади
        self.upload(make_docx(logic_key="В"))
        self.assertEqual(Question.objects.filter(bank__source="Ички аудит танлови").count(), 2)
        logic = Question.objects.get(bank__source="Ички аудит танлови", qtype="choice")
        self.assertEqual(logic.correct_option.text, "5")
        # Бошқа ҳужжат бошқа манба остида — мавжудлар устига ёзмайди
        self.upload(make_docx(title="Бошқа танлов"))
        self.assertEqual(Question.objects.filter(bank__source="Ички аудит танлови").count(), 2)
        self.assertEqual(Question.objects.filter(bank__source="Бошқа танлов").count(), 2)

    def test_errors_block_import(self):
        r, r2 = self.upload(make_docx(logic_key="Е"))
        self.assertIsNone(r2)
        self.assertContains(r, "калитдаги")
        self.assertEqual(QuestionBank.objects.filter(source="Ички аудит танлови").count(), 0)
        from io import BytesIO
        bad = BytesIO(b"not a docx"); bad.name = "x.docx"
        r = self.client.post(reverse("bank_import"), {"step": "check", "file": bad})
        self.assertContains(r, "Файлни ўқиб бўлмади")

    def test_experts_cannot_import(self):
        self.client.force_login(self.c1)
        self.assertEqual(self.client.get(reverse("bank_import")).status_code, 403)


class ConfirmSubmitTests(Base):
    def test_confirm_uses_prototype_submit(self):
        # Баҳолаш формасида name="submit" тугма бор — form.submit() уни кўрмайди, прототип орқали юбориш шарт
        self.client.force_login(self.author)
        r = self.client.get(reverse("test_list"))
        self.assertContains(r, "HTMLFormElement.prototype.submit.call(form)")


class RandomPickTests(Base):
    def test_random_n_from_bank(self):
        bank = QuestionBank.objects.create(name="Katta bank", kind=Kind.LOGIC)
        for i in range(30):
            q = Question.objects.create(bank=bank, code=f"R{i}", title=f"Savol {i}", text=f"<p>{i}</p>", qtype="choice", max_score=1)
            o = q.options.create(text="ha", order=1); q.options.create(text="yo'q", order=2)
            q.correct_option = o; q.save()
        self.client.force_login(self.author)
        url = reverse("block_add_from_bank", args=[self.logic.pk])
        before = self.logic.questions.count()
        self.client.post(url, {"bank": bank.pk, "mode": "random", "count": "10"})
        added = self.logic.questions.filter(source__bank=bank)
        self.assertEqual(added.count(), 10)
        self.assertEqual(self.logic.questions.count(), before + 10)
        self.assertTrue(all(q.correct_option and q.correct_option.question_id == q.pk for q in added))
        # Иккинчи марта — блокдагилар такрорланмайди
        self.client.post(url, {"bank": bank.pk, "mode": "random", "count": "20"})
        self.assertEqual(self.logic.questions.filter(source__bank=bank).values("source").distinct().count(), 30)
        # Ортиқча сон рад этилади
        r = self.client.post(url, {"bank": bank.pk, "mode": "random", "count": "5"}, follow=True)
        self.assertContains(r, "гача сон киритинг")
        self.assertEqual(self.logic.questions.filter(source__bank=bank).count(), 30)


class PerCandidateDrawTests(Base):
    def test_each_candidate_gets_own_set(self):
        for i in range(3, 9):  # амалий блокда жами 8 та савол
            q = Question.objects.create(block=self.practical, code=f"МА 0{i}", title=f"V{i}", text=f"<p>{i}</p>",
                                        qtype="text", max_score=10, order=i)
            q.criteria.create(text="x", max_score=2)
        self.practical.questions_per_candidate = 3
        self.practical.save()
        self.assertTrue(self.practical.is_drawn)
        self.assertEqual(self.practical.max_per_candidate, 30)
        self.assertEqual(self.test.max_score_for(Kind.PRACTICAL), 30)

        sets = []
        for n in range(8):
            a = self.register(f"Nomzod{n}", "Test", "", "1990")
            self.client.logout()
            c = self.client_class()
            c.post(reverse("exam_login"), {"login": a.login, "password": a.password})
            attempt = Attempt.objects.get(candidate=a.candidate)
            practical = attempt.answers.filter(question__block=self.practical)
            self.assertEqual(practical.count(), 3)
            self.assertEqual(attempt.answers.filter(question__block=self.logic).count(), 2)  # бошқа блок тўлиқ
            sets.append(frozenset(practical.values_list("question_id", flat=True)))
            r = c.get(reverse("exam_take"))
            self.assertEqual(r.status_code, 200)
        self.assertGreater(len(set(sets)), 1)  # номзодларга ҳар хил тўплам тушган

        # Балл ва якуний натижа номзоднинг ўз саволлари бўйича
        attempt = Attempt.objects.first()
        from . import grading
        self.assertEqual(grading.summary(attempt)["practical"]["max"], 30)

    def test_zero_means_all(self):
        self.assertFalse(self.practical.is_drawn)
        self.assertEqual(self.practical.per_candidate, 2)
