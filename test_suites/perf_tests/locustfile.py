"""Locust entry point for the Polyfile performance harness.

Run through the CLI (``polyfile-perf run``) or directly:

    locust -f test_suites/perf_tests/locustfile.py --headless --host http://127.0.0.1:8000 \
        --users 10 --spawn-rate 2 --run-time 1m
"""

from polyfile_perf.scenarios import PolyfileUser

__all__ = ["PolyfileUser"]
