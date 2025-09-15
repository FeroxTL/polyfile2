from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext as _


class CustomAuthenticationForm(AuthenticationForm):
    """AuthenticationForm with bootstrap widgets."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': _('Username'),
            'autofocus': True,
        })
        self.fields['username'].label_suffix = ''
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'current-password',
            'placeholder': _('Password'),
        })
        self.fields['password'].label_suffix = ''
