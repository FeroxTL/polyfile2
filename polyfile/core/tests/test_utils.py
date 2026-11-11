from datetime import timedelta

from django.test import SimpleTestCase

from polyfile.core.utils import parse_duration, parse_size


class ParseDurationTests(SimpleTestCase):
    def test_parses_supported_units(self) -> None:
        self.assertEqual(parse_duration("30s"), timedelta(seconds=30))
        self.assertEqual(parse_duration("15m"), timedelta(minutes=15))
        self.assertEqual(parse_duration("24h"), timedelta(hours=24))
        self.assertEqual(parse_duration("7d"), timedelta(days=7))

    def test_parses_fractional_values_and_normalizes_input(self) -> None:
        self.assertEqual(parse_duration(" 1.5h "), timedelta(minutes=90))

    def test_rejects_invalid_values(self) -> None:
        for value in ("", "24", "h", "24x", "abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_duration(value)


class ParseSizeTests(SimpleTestCase):
    def test_parses_binary_units(self) -> None:
        self.assertEqual(parse_size("512B"), 512)
        self.assertEqual(parse_size("10KB"), 10 * 1024)
        self.assertEqual(parse_size("10MB"), 10 * 1024 ** 2)
        self.assertEqual(parse_size("10GB"), 10 * 1024 ** 3)
        self.assertEqual(parse_size("1TiB"), 1024 ** 4)

    def test_parses_fractional_values_and_normalizes_input(self) -> None:
        self.assertEqual(parse_size(" 1.5 MB "), int(1.5 * 1024 ** 2))

    def test_parses_bare_values_as_bytes(self) -> None:
        self.assertEqual(parse_size("15"), 15)
        self.assertEqual(parse_size(15), 15)

    def test_rejects_invalid_values(self) -> None:
        for value in ("", "GB", "10XB", "-1GB", "nanGB", "infGB", -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_size(value)
