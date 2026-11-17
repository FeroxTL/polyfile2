from dataclasses import dataclass

from django.contrib.auth.models import AbstractUser
from django.urls import reverse


@dataclass
class DashboardUrl:
    id: str
    name: str
    url: str
    icon: str = ""


def get_sidebar_urls(user: AbstractUser) -> list[DashboardUrl]:
    sidebar_urls: list[DashboardUrl] = [
        DashboardUrl(id="files", name="Files", url=reverse("fs_node_browse", kwargs={"path": "/"}), icon="fa-folder"),
        DashboardUrl(id="trash", name="Trash", url=reverse("trash_dashboard"), icon="fa-trash"),
        DashboardUrl(id="shares", name="Public links", url=reverse("shares_dashboard"), icon="fa-share"),
    ]

    if user.is_staff or user.is_superuser:
        sidebar_urls.append(DashboardUrl(id='admin', name='Admin', url=reverse('admin:index'), icon='fa-user-shield'))

    return sidebar_urls
