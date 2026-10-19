from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.conf import settings
from django.urls import path, re_path
from django.views.static import serve

from exam import views_candidate as c
from exam import views_staff as s

urlpatterns = [
    path("", lambda r: redirect("dashboard")),

    # Nomzod (Safe Exam Browser start URL: /exam/)
    path("exam/", c.candidate_login, name="exam_login"),
    path("exam/language/", c.choose_language, name="exam_lang"),
    path("exam/photo/", c.photo, name="exam_photo"),
    path("exam/photo/save/", c.photo_save, name="exam_photo_save"),
    path("exam/take/", c.take, name="exam_take"),
    path("exam/save/", c.save_answer, name="exam_save"),
    path("exam/next/", c.next_block, name="exam_next"),
    path("exam/done/", c.done, name="exam_done"),

    # Xodimlar
    path("staff/login/", s.StaffLoginView.as_view(), name="staff_login"),
    path("staff/logout/", auth_views.LogoutView.as_view(next_page="staff_login"), name="staff_logout"),
    path("staff/", s.dashboard, name="dashboard"),

    path("staff/tests/", s.test_list, name="test_list"),
    path("staff/tests/new/", s.test_create, name="test_create"),
    path("staff/tests/<int:pk>/", s.test_detail, name="test_detail"),
    path("staff/tests/<int:pk>/edit/", s.test_edit, name="test_edit"),
    path("staff/tests/<int:pk>/delete/", s.test_delete, name="test_delete"),
    path("staff/tests/<int:pk>/preview/", s.test_preview, name="test_preview"),
    path("staff/tests/<int:pk>/copy/", s.test_copy, name="test_copy"),
    path("staff/tests/<int:pk>/unlock/", s.test_unlock, name="test_unlock"),
    path("staff/tests/<int:pk>/checkers/", s.test_checkers, name="test_checkers"),
    path("staff/tests/<int:test_pk>/blocks/new/", s.block_create, name="block_create"),
    path("staff/blocks/<int:pk>/edit/", s.block_edit, name="block_edit"),
    path("staff/blocks/<int:pk>/delete/", s.block_delete, name="block_delete"),
    path("staff/blocks/<int:block_pk>/questions/new/", s.question_create, name="question_create"),
    path("staff/blocks/<int:pk>/from-bank/", s.block_add_from_bank, name="block_add_from_bank"),
    path("staff/banks/", s.bank_list, name="bank_list"),
    path("staff/banks/new/", s.bank_create, name="bank_create"),
    path("staff/banks/import/", s.bank_import, name="bank_import"),
    path("staff/banks/<int:pk>/", s.bank_detail, name="bank_detail"),
    path("staff/banks/<int:pk>/edit/", s.bank_edit, name="bank_edit"),
    path("staff/banks/<int:pk>/merge/", s.bank_merge, name="bank_merge"),
    path("staff/banks/<int:bank_pk>/questions/new/", s.bank_question_create, name="bank_question_create"),
    path("staff/questions/<int:pk>/edit/", s.question_edit, name="question_edit"),
    path("staff/questions/<int:pk>/delete/", s.question_delete, name="question_delete"),

    path("staff/check/", s.check_list, name="check_list"),
    path("staff/check/<str:code>/", s.check_attempt, name="check_attempt"),

    path("staff/users/", s.user_list, name="user_list"),
    path("staff/users/new/", s.user_create, name="user_create"),
    path("staff/users/<int:pk>/", s.user_edit, name="user_edit"),
    path("staff/users/<int:pk>/delete/", s.user_delete, name="user_delete"),
    path("staff/candidates/", s.candidate_list, name="candidate_list"),
    path("staff/candidates/add/", s.candidate_add, name="candidate_add"),
    path("staff/candidates/import/", s.candidate_import, name="candidate_import"),
    path("staff/candidates/template.xlsx", s.candidate_template, name="candidate_template"),
    path("staff/candidates/<int:pk>/delete/", s.assignment_delete, name="assignment_delete"),
    path("staff/candidates/<int:pk>/edit/", s.assignment_edit, name="assignment_edit"),
    path("staff/candidates/<int:pk>/new-password/", s.assignment_reset_password, name="assignment_reset_password"),
    path("staff/candidates/print/", s.candidate_print, name="candidate_print"),
    path("staff/results/", s.results, name="results"),
    path("staff/hr-results/", s.hr_results, name="hr_results"),
    path("staff/results/export/", s.results_export, name="results_export"),
    path("staff/results/<int:pk>/", s.result_detail, name="result_detail"),
    path("staff/results/<int:pk>/action/", s.result_action, name="result_action"),
    path("staff/results/<int:pk>/photo.jpg", s.result_photo, name="result_photo"),

    path("staff/upload-image/", s.upload_image, name="upload_image"),
    path("django-admin/", admin.site.urls),
    # Ички тармоқ учун расмларни Django ўзи беради (алоҳида веб-сервер шарт эмас)
    re_path(r"^media/(?P<path>questions/[\w.-]+)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
