"""API-key authentication middleware."""

import logging
from collections.abc import Callable

from axes.handlers.proxy import AxesProxyHandler
from django.conf import settings
from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseBase

from polyfile.apps.accounts.models import ApiKey
from polyfile.core.exceptions import TooManyRequests, Unauthorized

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"
BEARER_PREFIX = "bearer "
# Axes tracks API-key brute-force attempts under a sentinel username so that
# lockouts are bucketed by IP rather than by a real user account.
API_KEY_AXES_USERNAME = None


def _extract_token(request: HttpRequest) -> str | None:
    """Return the API token from headers, or ``None`` when no key was sent."""
    authorization = request.META.get("HTTP_AUTHORIZATION", "")
    if authorization.lower().startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX) :].strip()

    header_token = request.META.get("HTTP_X_API_KEY", "")
    if header_token:
        return header_token.strip()
    return None


def _unauthorized_response(detail: str) -> JsonResponse:
    """Build the same JSON error shape as the rest of the API."""
    exception = Unauthorized(detail)
    response = JsonResponse(
        {
            "error_id": exception.error_code,
            "description": exception.description,
            "detail": exception.detail,
        },
        status=exception.status_code,
    )
    response["WWW-Authenticate"] = "Bearer"
    return response


def _too_many_requests_response(detail: str) -> JsonResponse:
    """Return a 429 JSON response when the source is axes-locked."""
    exception = TooManyRequests(detail)
    return JsonResponse(
        {
            "error_id": exception.error_code,
            "description": exception.description,
            "detail": exception.detail,
        },
        status=exception.status_code,
    )


class ApiKeyAuthenticationMiddleware:
    """Authenticate API requests that carry a bearer token.

    Session authentication is handled by Django's ``AuthenticationMiddleware``
    before this middleware. When an API key header is present, it takes
    precedence and an invalid key is rejected instead of falling back to a
    session.
    """

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponseBase],
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        token = _extract_token(request)
        if token is not None:
            axes_enabled = getattr(settings, "AXES_ENABLED", True)
            credentials = {"username": API_KEY_AXES_USERNAME}

            if axes_enabled:
                AxesProxyHandler.update_request(request)
                if AxesProxyHandler.is_locked(request, credentials):
                    return _too_many_requests_response(
                        "Too many failed API key attempts from this IP."
                    )

            def _record_api_key_failure() -> None:
                if axes_enabled:
                    AxesProxyHandler.user_login_failed(
                        sender=__name__,
                        request=request,
                        credentials=credentials,
                    )

            if not token:
                _record_api_key_failure()
                if axes_enabled and AxesProxyHandler.is_locked(request, credentials):
                    return _too_many_requests_response(
                        "Too many failed API key attempts from this IP."
                    )
                return _unauthorized_response("API key is empty.")

            api_key = ApiKey.authenticate(token)
            if api_key is None:
                _record_api_key_failure()
                if axes_enabled and AxesProxyHandler.is_locked(request, credentials):
                    return _too_many_requests_response(
                        "Too many failed API key attempts from this IP."
                    )
                return _unauthorized_response("Invalid or expired API key.")

            request.user = api_key.user
            request.auth = api_key
            request.api_key = api_key

            try:
                api_key.mark_used()
            except DatabaseError:
                # A failed usage timestamp must not reject an otherwise valid
                # request. The next request will retry the update.
                logger.exception("Failed to update API key last_used_at")

        return self.get_response(request)
