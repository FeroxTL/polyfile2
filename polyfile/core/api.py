from dataclasses import asdict

from django import http
from django.contrib.auth import logout as dj_logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_hint import RequestType

from polyfile.apps.accounts.models import User
from polyfile.apps.accounts.utils import get_sidebar_urls
from polyfile.core.exceptions import HttpException, Unauthorized


class BaseApiView(LoginRequiredMixin, View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        """Handles HttpException and returns appropriate http.JsonResponse."""
        try:
            return super().dispatch(*args, **kwargs)
        except HttpException as e:
            return http.JsonResponse(status=e.status_code, data={
                'error_id': e.error_code,
                'description': e.description,
                'detail': e.detail,
            })

    def handle_no_permission(self) -> http.HttpResponse:
        raise Unauthorized


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
        dj_logout(request)

        return http.JsonResponse(
            status=204,
            data={'message': 'Logged out successfully'}
        )
