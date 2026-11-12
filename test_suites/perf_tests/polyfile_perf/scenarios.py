"""Locust user scenarios for Polyfile.

One ``HttpUser`` class keeps locust's task weighting and tagging simple. The
active scenario is selected through ``PERF_SCENARIO`` and locust's ``--tags``.

All endpoints are path-based: nodes are addressed by their logical path
(``/api/v1/fs-node/?path=/...``), never by UUID.
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, tag, task

PAYLOAD_SIZE = int(os.environ.get("PERF_PAYLOAD_SIZE", "1024"))
WAIT_MIN = float(os.environ.get("PERF_WAIT_MIN", "0.5"))
WAIT_MAX = float(os.environ.get("PERF_WAIT_MAX", "2.0"))
SCENARIO = os.environ.get("PERF_SCENARIO", "mixed")


def build_payload(size: int | None = None) -> bytes:
    """Return deterministic binary content of ``size`` bytes."""
    length = max(1, size if size is not None else PAYLOAD_SIZE)
    return (bytes(range(256)) * ((length // 256) + 1))[:length]


class PolyfileUser(HttpUser):
    """Authenticated user exercising read, write and share endpoints."""

    wait_time = between(WAIT_MIN, max(WAIT_MIN, WAIT_MAX))

    def on_start(self) -> None:
        """Authenticate and, for write scenarios, create a working directory."""
        api_key = os.environ.get("POLYFILE_API_KEY")
        if api_key:
            self.client.headers["Authorization"] = f"Bearer {api_key}"

        self.work_dir_path: str | None = None
        if SCENARIO == "read":
            return

        path = f"/perf-{uuid.uuid4().hex[:10]}"
        response = self.client.post(
            "/api/v1/fs-node/mkdir",
            params={"path": path},
            name="mkdir setup",
        )
        if response.status_code == 200:
            self.work_dir_path = path

    def on_stop(self) -> None:
        """Remove the working directory created in ``on_start``."""
        if self.work_dir_path:
            self.client.delete(
                "/api/v1/fs-node/",
                params={"path": self.work_dir_path},
                name="delete setup",
            )

    @tag("read")
    @task(5)
    def list_root(self) -> None:
        """List the user's root-level nodes."""
        self.client.get("/api/v1/fs-node/", params={"path": "/"}, name="list root")

    @tag("read")
    @task(3)
    def list_working_directory(self) -> None:
        """List the working directory by path."""
        if self.work_dir_path:
            self.client.get(
                "/api/v1/fs-node/",
                params={"path": self.work_dir_path},
                name="list directory",
            )
        else:
            self.client.get("/api/v1/fs-node/", params={"path": "/"}, name="list root")

    @tag("write")
    @task(2)
    def mkdir_and_delete(self) -> None:
        """Create and immediately delete a directory."""
        path = f"/perf-dir-{uuid.uuid4().hex[:10]}"
        response = self.client.post(
            "/api/v1/fs-node/mkdir",
            params={"path": path},
            name="mkdir",
        )
        if response.status_code != 200:
            return
        self.client.delete(
            "/api/v1/fs-node/",
            params={"path": path},
            name="delete directory",
        )

    @tag("write")
    @task(2)
    def upload_and_delete(self) -> None:
        """Create a file, upload content and schedule its deletion."""
        name = f"perf-file-{uuid.uuid4().hex[:10]}.bin"
        path = f"{self.work_dir_path}/{name}" if self.work_dir_path else f"/{name}"

        response = self.client.post(
            "/api/v1/fs-node/touch",
            params={"path": path},
            name="touch",
        )
        if response.status_code != 200:
            return

        data = response.json()
        self.client.post(
            data["upload_url"],
            data=build_payload(),
            headers={"Content-Type": "application/octet-stream"},
            name="upload",
        )
        self.client.delete(
            "/api/v1/fs-node/",
            params={"path": path},
            name="delete file",
        )

    @tag("share")
    @task(1)
    def share_and_revoke(self) -> None:
        """Create, read and revoke a public share for the working directory."""
        if not self.work_dir_path:
            return

        response = self.client.post(
            f"/api/shares/create{self.work_dir_path}",
            name="share create",
        )
        if response.status_code != 200:
            return

        token = response.json()["id"]
        self.client.get(f"/api/shares/detail/{token}/", name="share detail")
        self.client.post(f"/api/shares/{token}/revoke", name="share revoke")
