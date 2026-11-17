"""Reusable helpers for Django tests."""

from typing import Any

from django.test import Client, TestCase


class JsonApiClient(Client):
    """Test client that sends ``application/json`` bodies by default.

    ``Client.post`` normally uses ``multipart/form-data`` unless a content type
    is passed explicitly. API tests rarely need that, so this client defaults
    to ``application/json`` and lets Django serialize dicts, lists and tuples
    with ``json.dumps``. Pass ``content_type`` explicitly to override it, for
    example when uploading a file.
    """

    def post(
            self,
            path,
            data=None,
            content_type="application/json",
            follow=False,
            secure=False,
            *,
            headers=None,
            query_params=None,
            **extra,
    ) -> Any:
        return super().post(
            path,
            data=data,
            content_type=content_type,
            follow=follow,
            secure=secure,
            headers=headers,
            query_params=query_params,
            **extra,
        )


class JsonApiTestCase(TestCase):
    """``TestCase`` whose client posts JSON instead of multipart/form-data."""

    client_class = JsonApiClient
