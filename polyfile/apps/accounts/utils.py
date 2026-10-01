from dataclasses import dataclass

from django.contrib.auth.models import AbstractUser
from django.urls import reverse


@dataclass
class DashboardUrl:
    id: str
    name: str
    url: str


def get_sidebar_urls(user: AbstractUser) -> list[DashboardUrl]:
    sidebar_urls: list[DashboardUrl] = [
        DashboardUrl(id='files', name='Files', url=reverse('files_dashboard', kwargs={'path': '/'})),
    ]

    if user.is_staff or user.is_superuser:
        sidebar_urls.append(DashboardUrl(id='admin', name='Admin', url=reverse('admin:index')))

    return sidebar_urls
