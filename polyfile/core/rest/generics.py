import json

from django import http
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_hint import RequestType
from marshmallow import Schema, ValidationError

from polyfile.core.exceptions import (
    BadRequest,
    FieldValidationError,
    HttpException,
    Unauthorized,
)
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

    @staticmethod
    def json_response(data: dict, status: int = 200) -> JsonResponse:
        """Build a JSON response with an explicit Content-Type."""
        return http.JsonResponse(data, status=status)

    def handle_no_permission(self) -> HttpResponseRedirect | JsonResponse:
        if wants_html(self.request):
            return http.HttpResponseRedirect(settings.LOGIN_URL)

        return http.JsonResponse({
            "error_id": Unauthorized.error_code,
            "description": Unauthorized.description,
            "detail": Unauthorized.description,
        }, status=Unauthorized.status_code)


class CreateApiView(BaseApiView):
    """Base view for endpoints that create a resource from a JSON body.

    Subclasses set ``serializer_class`` (a Marshmallow schema used for the
    request body) and implement :meth:`create`, which returns the
    JSON-serializable response payload. ``POST`` is handled by default and
    wraps :meth:`create` into :meth:`BaseApiView.json_response`.
    """

    serializer_class: type[Schema]

    @classmethod
    def load_params(cls, request: RequestType) -> dict:
        """
        Load and validate the JSON request body with ``serializer_class``.

        :raises BadRequest: On malformed JSON.
        :raises FieldValidationError: On invalid fields.
        """
        try:
            body = json.loads(request.body) if request.body.strip() else {}
        except json.JSONDecodeError:
            raise BadRequest("Invalid JSON body")

        try:
            return cls.serializer_class().load(body)
        except ValidationError as e:
            raise FieldValidationError(detail=e.messages)

    @classmethod
    def create(cls, request: RequestType) -> dict:
        """Create the resource and return the JSON-serializable payload."""
        raise NotImplementedError

    @classmethod
    def post(cls, request: RequestType) -> JsonResponse:
        """Handle POST by creating the resource and wrapping it in JSON."""
        return cls.json_response(cls.create(request))
