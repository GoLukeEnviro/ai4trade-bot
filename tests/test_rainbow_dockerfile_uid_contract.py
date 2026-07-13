"""Tests for the rainbow.Dockerfile UID/GID storage-ownership contract.

Root cause this guards against: rainbow.Dockerfile created its runtime
user with `useradd -r` (an unpinned system UID), while HermesTrader's
docker-compose.hermestrader-dryrun.yml runs the container as a fixed
`user: "10000:10000"` and mounts a persistent named volume at
/app/rainbow/storage. When the image-baked UID did not match the
compose-forced runtime UID, the container could not write its own
SQLite database in a fresh volume (`sqlite3.OperationalError: attempt
to write a readonly database`) and never became healthy.

Static tests always run. Docker-based tests build the real image and
are skipped if a Docker daemon is not reachable (e.g. some local dev
setups); GitHub Actions' ubuntu-latest runners have Docker available
by default, so these run in CI.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "rainbow.Dockerfile"

RAINBOW_UID = 10000
RAINBOW_GID = 10000


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
    return result.returncode == 0


DOCKER_AVAILABLE = _docker_available()
requires_docker = pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not reachable")


class TestDockerfileStaticContract:
    def test_dockerfile_pins_uid_and_gid(self):
        content = DOCKERFILE.read_text()
        assert 'ARG RAINBOW_UID=10000' in content
        assert 'ARG RAINBOW_GID=10000' in content

    def test_dockerfile_creates_user_with_explicit_ids(self):
        content = DOCKERFILE.read_text()
        assert '--uid "${RAINBOW_UID}"' in content
        assert '--gid "${RAINBOW_GID}"' in content

    def test_dockerfile_does_not_use_unpinned_system_useradd(self):
        content = DOCKERFILE.read_text()
        assert "useradd -r -g rainbow rainbow" not in content

    def test_dockerfile_copies_source_with_explicit_ownership(self):
        content = DOCKERFILE.read_text()
        assert "COPY --chown=10000:10000 core ./core" in content
        assert "COPY --chown=10000:10000 rainbow ./rainbow" in content

    def test_dockerfile_chowns_storage_to_pinned_ids(self):
        content = DOCKERFILE.read_text()
        assert "chown -R 10000:10000 /app" in content

    def test_dockerfile_runs_as_pinned_user(self):
        content = DOCKERFILE.read_text()
        assert "USER 10000:10000" in content

    def test_dockerfile_does_not_run_as_root_or_named_user(self):
        content = DOCKERFILE.read_text()
        lines = [line.strip() for line in content.splitlines() if line.strip().startswith("USER ")]
        assert lines == ["USER 10000:10000"]

    def test_dockerignore_excludes_runtime_storage(self):
        dockerignore = (REPO_ROOT / ".dockerignore").read_text()
        assert "storage/" in dockerignore.splitlines()


@requires_docker
class TestRainbowImageUidContract:
    """Builds the real image once for this test class and verifies the
    contract behaviorally, including the exact failure mode of the bug
    (writing a fresh SQLite database in a freshly created named volume
    as the compose-forced runtime UID)."""

    @classmethod
    def setup_class(cls):
        cls.image_tag = f"rainbow-uid-contract-test:{uuid.uuid4().hex[:8]}"
        result = subprocess.run(
            ["docker", "build", "-f", str(DOCKERFILE), "-t", cls.image_tag, str(REPO_ROOT)],
            capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, f"image build failed:\n{result.stderr}"

    @classmethod
    def teardown_class(cls):
        subprocess.run(["docker", "image", "rm", "-f", cls.image_tag], capture_output=True, timeout=30)

    def test_image_config_user_is_pinned_uid_gid(self):
        result = subprocess.run(
            ["docker", "inspect", self.image_tag, "--format", "{{.Config.User}}"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        assert result.stdout.strip() == f"{RAINBOW_UID}:{RAINBOW_GID}"

    def test_app_storage_directory_owned_by_pinned_ids(self):
        result = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "sh", self.image_tag,
             "-c", "stat -c '%u:%g' /app /app/rainbow/storage"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        owners = result.stdout.strip().splitlines()
        assert owners == [f"{RAINBOW_UID}:{RAINBOW_GID}", f"{RAINBOW_UID}:{RAINBOW_GID}"]

    def test_no_signals_db_baked_into_image(self):
        result = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "sh", self.image_tag,
             "-c", "find /app -iname '*.db'"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        assert result.stdout.strip() == ""

    def test_sqlite_write_in_fresh_named_volume_as_pinned_uid(self):
        """Direct reproduction of the original failure: a fresh named
        volume mounted at /app/rainbow/storage must be writable by the
        image's own runtime user (no compose-level user override
        needed here -- the image's own USER directive is exercised)."""
        volume_name = f"rainbow-uid-contract-test-vol-{uuid.uuid4().hex[:8]}"
        subprocess.run(["docker", "volume", "create", volume_name], capture_output=True, timeout=15, check=True)
        try:
            script = (
                "import sqlite3, os, sys; "
                "assert os.getuid() == 10000 and os.getgid() == 10000, (os.getuid(), os.getgid()); "
                "conn = sqlite3.connect('/app/rainbow/storage/contract_test.db'); "
                "conn.execute('PRAGMA journal_mode=WAL'); "
                "conn.execute('CREATE TABLE t (id INTEGER)'); "
                "conn.execute('INSERT INTO t VALUES (1)'); "
                "conn.commit(); conn.close(); "
                "print('SQLITE_WRITE_OK')"
            )
            result = subprocess.run(
                ["docker", "run", "--rm",
                 "-v", f"{volume_name}:/app/rainbow/storage",
                 "--entrypoint", "python3", self.image_tag, "-c", script],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
            assert "SQLITE_WRITE_OK" in result.stdout
        finally:
            subprocess.run(["docker", "volume", "rm", "-f", volume_name], capture_output=True, timeout=15)

    def test_healthcheck_still_defined(self):
        result = subprocess.run(
            ["docker", "inspect", self.image_tag, "--format", "{{.Config.Healthcheck.Test}}"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        assert "python" in result.stdout
