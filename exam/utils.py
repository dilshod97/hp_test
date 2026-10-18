import random
import re

import nh3
from django.db import transaction

from .models import Answer, Attempt, BlockAttempt

ALLOWED_TAGS = {
    "p", "br", "b", "strong", "i", "em", "u", "s", "strike", "sub", "sup", "span", "div",
    "ul", "ol", "li", "blockquote", "pre", "code", "h2", "h3", "h4",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col", "hr",
}
STYLED = {"style"}
ALLOWED_ATTRIBUTES = {
    "p": STYLED, "span": STYLED, "div": STYLED, "h2": STYLED, "h3": STYLED, "h4": STYLED, "li": STYLED,
    "ul": STYLED, "ol": STYLED, "pre": STYLED, "blockquote": STYLED,
    "table": {"style", "border", "cellpadding", "cellspacing"}, "tr": STYLED, "col": STYLED,
    "td": {"colspan", "rowspan", "style"}, "th": {"colspan", "rowspan", "style", "scope"},
}
STYLE_PROPERTIES = {
    "text-align", "color", "background-color", "padding-left", "margin-left", "text-decoration",
    "font-weight", "font-style", "width", "height", "border-collapse", "border", "border-width",
    "border-style", "border-color", "vertical-align", "list-style-type",
}
# Савол тузувчи расм қўйиши мумкин (фақат тизимга юкланган расмлар)
AUTHOR_TAGS = ALLOWED_TAGS | {"img", "figure", "figcaption"}
AUTHOR_ATTRIBUTES = {**ALLOWED_ATTRIBUTES, "img": {"src", "alt", "width", "height", "style"}}


def _local_media_only(element, attribute, value):
    if element == "img" and attribute == "src":
        return value if value.startswith("/media/") and ".." not in value else None
    return value


def clean_html(value):
    """Савол матни (тест тузувчи). XSS дан ҳимоя; расмлар фақат /media/ дан."""
    return nh3.clean(
        value or "", tags=AUTHOR_TAGS, attributes=AUTHOR_ATTRIBUTES,
        filter_style_properties=STYLE_PROPERTIES, attribute_filter=_local_media_only,
    )


def clean_answer(value):
    """Номзод жавоби: форматлаш, жадвал ва псевдокод мумкин; расм ва ҳавола йўқ."""
    return nh3.clean(
        value or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, filter_style_properties=STYLE_PROPERTIES,
    )


def is_empty_html(value):
    text = re.sub(r"<[^>]+>", "", value or "").replace("&nbsp;", "").strip()
    return text == "" and "<table" not in (value or "") and "<img" not in (value or "")


@transaction.atomic
def create_attempt(candidate, test, ip=None):
    attempt = Attempt.objects.create(candidate=candidate, test=test, ip_address=ip)
    rng = random.SystemRandom()
    answers = []
    for block in test.blocks.prefetch_related("questions__options"):
        questions = list(block.questions.all())
        if block.is_drawn:
            # Ҳар бир номзодга ўзининг тасодифий тўплами
            questions = rng.sample(questions, block.per_candidate)
            if not test.shuffle_questions:
                questions.sort(key=lambda q: (q.order, q.pk))
        if test.shuffle_questions:
            rng.shuffle(questions)
        options = {}
        for q in questions:
            opts = [o.id for o in q.options.all()]
            if test.shuffle_options:
                rng.shuffle(opts)
            options[str(q.id)] = opts
            answers.append(Answer(attempt=attempt, question=q))
        BlockAttempt.objects.create(
            attempt=attempt, block=block,
            layout={"questions": [q.id for q in questions], "options": options},
        )
    Answer.objects.bulk_create(answers)
    return attempt


def client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
