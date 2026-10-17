from django.apps import AppConfig


class ExamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "exam"
    verbose_name = "Тест тизими"

    def ready(self):
        # Django'нинг ўзбекча таржимаси лотинча, шунинг учун асосий хабарларни кириллчада берамиз
        from django import forms
        from django.core import validators

        forms.Field.default_error_messages["required"] = "Бу майдонни тўлдиринг."
        forms.DateField.default_error_messages["invalid"] = "Санани тўғри киритинг."
        forms.IntegerField.default_error_messages["invalid"] = "Бутун сон киритинг."
        forms.DecimalField.default_error_messages["invalid"] = "Сон киритинг."
        forms.ChoiceField.default_error_messages["invalid_choice"] = "Рўйхатдан танланг."
        forms.ModelChoiceField.default_error_messages["invalid_choice"] = "Рўйхатдан танланг."
        forms.ModelMultipleChoiceField.default_error_messages["invalid_choice"] = "Рўйхатдан танланг."
        forms.FileField.default_error_messages["required"] = "Файлни танланг."
        forms.FileField.default_error_messages["empty"] = "Файл бўш."
        validators.MaxLengthValidator.message = "Кўпи билан %(limit_value)d белги бўлиши керак."
        validators.MinLengthValidator.message = "Камида %(limit_value)d белги бўлиши керак."
        validators.MinValueValidator.message = "Қиймат камида %(limit_value)s бўлиши керак."
        validators.MaxValueValidator.message = "Қиймат кўпи билан %(limit_value)s бўлиши керак."
