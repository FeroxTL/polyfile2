from django.conf import settings
from django.template import RequestContext, Template
from django.test import RequestFactory, SimpleTestCase, override_settings

from polyfile.core.context_processors import settings_context


class SettingsContextTests(SimpleTestCase):
    def setUp(self) -> None:
        self.request = RequestFactory().get("/")

    @override_settings(TEMPLATE_CONTEXT_SETTINGS=("DEBUG", "LANGUAGE_CODE"))
    def test_exposes_whitelisted_settings(self) -> None:
        context = settings_context(self.request)

        self.assertEqual(
            context,
            {
                "DEBUG": settings.DEBUG,
                "LANGUAGE_CODE": settings.LANGUAGE_CODE,
            },
        )

    @override_settings(TEMPLATE_CONTEXT_SETTINGS=("DEBUG",))
    def test_does_not_expose_unlisted_settings(self) -> None:
        context = settings_context(self.request)

        self.assertNotIn("SECRET_KEY", context)
        self.assertNotIn("DATABASES", context)

    @override_settings(TEMPLATE_CONTEXT_SETTINGS=("MISSING_SETTING",))
    def test_ignores_missing_settings(self) -> None:
        self.assertEqual(settings_context(self.request), {})

    @override_settings(TEMPLATE_CONTEXT_SETTINGS=("DEBUG",), DEBUG=True)
    def test_processor_is_registered_for_templates(self) -> None:
        template = Template("{{ DEBUG }}")

        rendered = template.render(RequestContext(self.request))

        self.assertEqual(rendered, "True")

    def test_processor_is_configured(self) -> None:
        self.assertIn(
            "polyfile.core.context_processors.settings_context",
            settings.TEMPLATES[0]["OPTIONS"]["context_processors"],
        )
