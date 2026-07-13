"""Static regression tests for Rainbow container build."""

from pathlib import Path


def test_rainbow_dockerfile_copies_shared_core_package() -> None:
    dockerfile = Path("rainbow.Dockerfile").read_text(encoding="utf-8")

    assert "COPY core ./core" in dockerfile


def test_rainbow_dockerfile_creates_runtime_storage_directory() -> None:
    dockerfile = Path("rainbow.Dockerfile").read_text(encoding="utf-8")

    assert "mkdir -p /app/rainbow/storage" in dockerfile
