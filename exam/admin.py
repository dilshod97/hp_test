from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Answer, Assignment, Attempt, Block, Candidate, Criterion, Option, Question, QuestionBank, Review, ReviewAnswer, Test, User,
)


@admin.register(User)
class StaffUserAdmin(UserAdmin):
    list_display = ("username", "last_name", "first_name", "role", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Rol", {"fields": ("role",)}),)


admin.site.register([
    QuestionBank, Test, Block, Assignment, Question, Option, Criterion, Candidate, Attempt, Answer, Review, ReviewAnswer,
])
