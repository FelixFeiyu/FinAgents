from datetime import datetime, timezone
from pathlib import Path

from finagent.pipeline import run_pipeline


def test_mock_pipeline_writes_auditable_run(tmp_path: Path):
    result = run_pipeline(datetime(2026, 6, 10, tzinfo=timezone.utc), str(tmp_path))
    assert result.views
    assert result.aggregated
    assert all(view.evidence_ids for view in result.views)
    assert list(tmp_path.glob("run-*.json"))
    assert (tmp_path / "evidence.sqlite").exists()

