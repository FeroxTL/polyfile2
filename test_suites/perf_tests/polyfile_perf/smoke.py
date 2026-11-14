"""End-to-end smoke flow that exercises the main Polyfile API paths.

The flow is intentionally idempotent: every run creates its own directory and
removes it through the asynchronous deletion job before returning.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Self

import httpx

from polyfile_perf.client import PolyfileApiError, PolyfileClient

CLEANUP_ERRORS = (
    PolyfileApiError,
    httpx.HTTPError,
    TimeoutError,
    KeyError,
    AssertionError,
)


@dataclass
class SmokeStep:
    """Result of one smoke-flow step."""

    name: str
    ok: bool
    duration_ms: float = 0.0
    detail: str = ""


@dataclass
class SmokeResult:
    """Aggregate smoke-flow result."""

    steps: list[SmokeStep] = field(default_factory=list)
    directory_id: str | None = None
    directory_path: str | None = None
    file_path: str | None = None
    share_token: str | None = None
    cleanup_job_id: str | None = None

    @property
    def ok(self) -> bool:
        """Return whether every recorded step succeeded."""
        return all(step.ok for step in self.steps)

    @property
    def failures(self) -> list[SmokeStep]:
        """Return only the failed steps."""
        return [step for step in self.steps if not step.ok]


def run_smoke_flow(
    client: PolyfileClient,
    *,
    payload_size: int = 1024,
    delete_timeout: float = 60.0,
    on_step: Callable[[SmokeStep], None] | None = None,
) -> SmokeResult:
    """Run the smoke flow and return its result.

    Steps: dashboard probe, root listing, mkdir, touch, upload, listing check,
    share create/detail/revoke, and asynchronous delete with job polling.
    """
    result = SmokeResult()
    run_id = uuid.uuid4().hex[:12]
    directory_name = f"perf-smoke-{run_id}"
    directory_path = f"/{directory_name}"
    file_name = "payload.bin"
    file_path = f"{directory_path}/{file_name}"
    payload = (bytes(range(256)) * ((max(1, payload_size) // 256) + 1))[: max(1, payload_size)]

    def step(name: str) -> _StepTimer:
        return _StepTimer(name, result, on_step)

    try:
        with step("dashboard-context") as timer:
            context = client.dashboard_context()
            timer.detail = f"{len(context)} keys"

        with step("list-root") as timer:
            root = client.list_nodes("/")
            timer.detail = f"{len(root.get('children', []))} children"

        with step("mkdir") as timer:
            directory = client.mkdir(directory_name)
            result.directory_id = str(directory["id"])
            result.directory_path = directory_path
            timer.detail = directory_path

        with step("touch") as timer:
            node = client.touch(file_name, parent_id=result.directory_id)
            result.file_path = file_path
            upload_url = node["upload_url"]
            timer.detail = file_path

        with step("upload") as timer:
            uploaded = client.upload(upload_url, payload)
            timer.detail = f"{uploaded.get('size', 0)} bytes"

        with step("list-directory") as timer:
            listing = client.list_nodes(directory_path)
            children = listing.get("children", [])
            names = {child.get("name") for child in children}
            if file_name not in names:
                raise AssertionError(f"{file_name!r} missing from {sorted(names)}")
            timer.detail = f"{len(children)} children"

        with step("share-create") as timer:
            share = client.create_share(result.directory_id)
            result.share_token = str(share["id"])
            timer.detail = result.share_token

        with step("share-detail") as timer:
            detail = client.share_detail(result.share_token)
            timer.detail = str(detail.get("current", {}).get("name"))

        with step("share-revoke") as timer:
            client.revoke_share(result.share_token)
            timer.detail = "revoked"

    except CLEANUP_ERRORS:
        # The failing step is already recorded; cleanup still runs below.
        pass
    finally:
        _cleanup(client, result, step, delete_timeout)

    return result


def _cleanup(
    client: PolyfileClient,
    result: SmokeResult,
    step: Callable[[str], _StepTimer],
    delete_timeout: float,
) -> None:
    """Remove the smoke directory without masking the original failure."""
    if result.directory_id is None:
        return

    try:
        with step("delete-directory") as timer:
            job = client.delete_node(result.directory_id)
            result.cleanup_job_id = str(job["job_id"])
            timer.detail = result.cleanup_job_id
    except CLEANUP_ERRORS:
        return

    if result.cleanup_job_id is None:
        return

    try:
        with step("wait-deletion") as timer:
            job_status = client.wait_for_deletion(
                result.cleanup_job_id,
                timeout=delete_timeout,
            )
            timer.detail = str(job_status.get("status"))
            if job_status.get("status") != "done":
                raise AssertionError(f"Deletion job ended as {job_status.get('status')!r}")
    except CLEANUP_ERRORS:
        return


class _StepTimer:
    """Context manager that records a :class:`SmokeStep`."""

    def __init__(
        self,
        name: str,
        result: SmokeResult,
        on_step: Callable[[SmokeStep], None] | None,
    ) -> None:
        self.name = name
        self._result = result
        self._on_step = on_step
        self._started = 0.0
        self.detail = ""

    def __enter__(self) -> Self:
        self._started = time.monotonic()
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> bool:
        step = SmokeStep(
            name=self.name,
            ok=exc is None,
            duration_ms=(time.monotonic() - self._started) * 1000.0,
            detail=self.detail if exc is None else f"{type(exc).__name__}: {exc}",
        )
        self._result.steps.append(step)
        if self._on_step is not None:
            self._on_step(step)
        return False
