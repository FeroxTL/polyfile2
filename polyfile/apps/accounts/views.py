from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page

from polyfile.apps.accounts.forms import CustomAuthenticationForm


@method_decorator(cache_page(60), name='dispatch')
class CustomLoginView(LoginView):
    """Display the login form and handle the login action."""
    template_name = 'accounts/login.html'
    form_class = CustomAuthenticationForm
    title = _('Log in')
    action_title = _('Log in')

    def get_context_data(self, **kwargs):
        """Extra context data for login form."""
        if self.request.user.is_authenticated:
            kwargs['username'] = self.request.user.username
        kwargs['title'] = 'Please sign in'
        return super().get_context_data(**kwargs)
