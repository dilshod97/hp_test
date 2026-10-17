from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*checks):
    """Masalan: @role_required("is_author") yoki @role_required("is_checker", "is_superadmin")."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not any(getattr(request.user, c) for c in checks):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
