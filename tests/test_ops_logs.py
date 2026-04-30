from pathlib import Path

from backend.ops_logs import read_log_tail


def test_unknown_job_key_rejected() -> None:
    root = Path(__file__).resolve().parents[1]
    path, content, err = read_log_tail(root, "totally-fake-job")
    assert path is None
    assert content == ""
    assert err and "Unknown" in err
