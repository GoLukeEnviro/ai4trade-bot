"""Validate Hermes orchestrator config meets minimum requirements."""
import sys
from pathlib import Path

MIN_CONFIG_VERSION = 28

# Possible config locations, checked in order
CONFIG_SEARCH_PATHS = [
    Path("config.yaml"),
    Path("config.yml"),
    Path(".hermes/config.yaml"),
    Path("../config.yaml"),
]


def _find_config() -> Path | None:
    """Return the first config file that exists, or None."""
    for p in CONFIG_SEARCH_PATHS:
        if p.exists():
            return p
    return None


def _parse_yaml_value(path: Path, key: str):
    """Minimal YAML key lookup without requiring pyyaml.

    Walks the file line-by-line looking for ``key: <value>`` at the top level.
    Returns the string value (stripped) or None if not found.
    """
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            # Skip indented lines (nested keys, not top-level)
            if line[:1] in (" ", "\t") and line.strip():
                continue
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            if ":" not in stripped:
                continue
            k, _, v = stripped.partition(":")
            if k.strip() == key:
                return v.strip().strip("\"'")
    return None


def main() -> None:
    config_path = _find_config()
    checks: list[tuple[str, bool]] = []

    if config_path is None:
        print(f"WARN  config file not found (searched: {[str(p) for p in CONFIG_SEARCH_PATHS]})")
        print("WARN  skipping config-version check")
        # Missing config is a warning, not a hard failure
        checks.append(("config file exists", False))
        _print_summary(checks)
        sys.exit(1)

    checks.append(("config file exists", True))
    print(f"OK    config file found: {config_path}")

    # --- config version ---------------------------------------------------
    version_str = _parse_yaml_value(config_path, "_config_version")
    if version_str is None:
        print("WARN  _config_version key not found in config")
        checks.append(("config version >= 28", False))
    else:
        try:
            version = int(version_str)
        except ValueError:
            print(f"FAIL  _config_version is not an integer: {version_str!r}")
            checks.append(("config version >= 28", False))
        else:
            passed = version >= MIN_CONFIG_VERSION
            status = "OK  " if passed else "FAIL"
            print(f"{status}  _config_version={version} (minimum {MIN_CONFIG_VERSION})")
            checks.append(("config version >= 28", passed))

    _print_summary(checks)
    if all(p for _, p in checks):
        sys.exit(0)
    else:
        sys.exit(1)


def _print_summary(checks: list[tuple[str, bool]]) -> None:
    print()
    print("Summary:")
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")


if __name__ == "__main__":
    main()
