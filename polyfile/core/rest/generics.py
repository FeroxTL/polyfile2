from django import http
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from marshmallow import ValidationError

from polyfile.core.exceptions import FieldValidationError, HttpException, Unauthorized
from polyfile.core.http import wants_html


class AnonymousApiView(View):
    """Base view for anonymous users."""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        """Handles HttpException and returns appropriate http.JsonResponse."""
        try:
            return super().dispatch(*args, **kwargs)
        except ValidationError as e:
            return http.JsonResponse({
                "error_id": FieldValidationError.error_code,
                "description": FieldValidationError.description,
                "detail": e.normalized_messages(),
            }, status=FieldValidationError.status_code)
        except HttpException as e:
            return http.JsonResponse({
                "error_id": e.error_code,
                "description": e.description,
                "detail": e.detail,
            }, status=e.status_code)


@method_decorator(csrf_exempt, name="dispatch")
class BaseApiView(LoginRequiredMixin, AnonymousApiView):
    """Base view for all api views."""

    def handle_no_permission(self) -> HttpResponseRedirect | JsonResponse:
        if wants_html(self.request):
            return http.HttpResponseRedirect(settings.LOGIN_URL)

        return http.JsonResponse({
            "error_id": Unauthorized.error_code,
            "description": Unauthorized.description,
            "detail": Unauthorized.description,
        }, status=Unauthorized.status_code)
