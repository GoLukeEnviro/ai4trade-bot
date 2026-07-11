# Rainbow Metadata Completeness — Sample Report

**Generated:** 2026-07-11 (fixture validation)  
**Checker:** `scripts/check_rainbow_metadata_completeness.py`  
**Issue:** #58

## Summary

| Fixture | Verdict |
|---------|---------|
| `valid_long_signal.json` | GREEN |
| `valid_short_signal.json` | GREEN |
| `no_signal.json` | GREEN |
| `heartbeat.json` | GREEN |
| `partial_metadata_signal.json` | GREEN — null `signal_strength` allowed |
| `heartbeat.json` | GREEN |
| `stale_signal.json` | YELLOW — semantically stale |
| `malformed_missing_required_fields.json` | RED — missing required fields (expected) |

## Usage

```bash
python scripts/check_rainbow_metadata_completeness.py
python scripts/check_rainbow_metadata_completeness.py --format markdown
python -m pytest tests/test_rainbow_metadata_completeness.py -q
```

Regenerate this report:

```bash
python scripts/check_rainbow_metadata_completeness.py --format markdown > docs/reports/rainbow-metadata-completeness.md
```