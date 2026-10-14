from dataclasses import asdict

from django import http
from django.contrib.auth import logout
from django_hint import RequestType

from polyfile.apps.accounts.models import User
from polyfile.apps.accounts.utils import get_sidebar_urls
from polyfile.core.rest.generics import BaseApiView


class DashboardContextView(BaseApiView):
    @staticmethod
    def get(request: RequestType) -> http.HttpResponse:
        return http.JsonResponse({
            'sidebar_urls': list(map(asdict, get_sidebar_urls(request.user)))
        })


class LogoutView(BaseApiView):
    """Logout API endpoint - invalidates session tokens."""

    @staticmethod
    def post(request: RequestType) -> http.HttpResponse:
        """Logout and invalidate session."""
        assert request.user.is_authenticated and isinstance(request.user, User)
        logout(request)

        return http.JsonResponse(
            status=204,
            data={'message': 'Logged out successfully'}
        )
