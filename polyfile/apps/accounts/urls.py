from django.urls import path

from polyfile.apps.accounts.views import CustomLoginView

urlpatterns = [
    path("accounts/login/", CustomLoginView.as_view(), name="accounts-login"),
]
