
from scripts.check_rainbow_metadata_completeness import FIXTURES_DIR, run


class TestRainbowMetadataCompleteness:
    def test_all_fixtures_parse_without_red(self):
        reports = run(FIXTURES_DIR)
        assert reports, "expected fixture reports"
        by_name = {r.path: r for r in reports}
        assert by_name["malformed_missing_required_fields.json"].verdict == "RED"
        assert by_name["valid_long_signal.json"].verdict == "GREEN"
        assert by_name["partial_metadata_signal.json"].verdict == "GREEN"
        assert by_name["heartbeat.json"].verdict == "GREEN"
        assert by_name["stale_signal.json"].verdict == "YELLOW"

    def test_valid_fixtures_have_no_missing_required(self):
        for report in run(FIXTURES_DIR):
            if report.path == "malformed_missing_required_fields.json":
                continue
            assert not report.missing_required, report.path
