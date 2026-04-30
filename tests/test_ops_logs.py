from pathlib import Path

from backend.ops_logs import read_log_tail, read_run_log_excerpt


def test_unknown_job_key_rejected() -> None:
    root = Path(__file__).resolve().parents[1]
    path, content, err = read_log_tail(root, "totally-fake-job")
    assert path is None
    assert content == ""
    assert err and "Unknown" in err


def test_run_log_excerpt_finds_anchor(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir(parents=True)
    log = tmp_path / "logs" / "daily-active.log"
    log.write_text(
        "noise\n"
        "PIPELINE_RUN_LOG_ANCHOR id=1 job=daily-active\n"
        "first run\n"
        "PIPELINE_RUN_LOG_ANCHOR id=42 job=daily-active\n"
        "inside\n"
        "more\n",
        encoding="utf-8",
    )
    path, content, note = read_run_log_excerpt(tmp_path, "daily-active", 42, max_lines=50)
    assert path is not None
    assert "PIPELINE_RUN_LOG_ANCHOR id=42" in content
    assert "inside" in content
    assert "PIPELINE_RUN_LOG_ANCHOR id=1" not in content
    assert note is None or isinstance(note, str)


def test_run_log_excerpt_unknown_job() -> None:
    root = Path(__file__).resolve().parents[1]
    path, content, err = read_run_log_excerpt(root, "not-a-real-job", 1)
    assert path is None
    assert content == ""
    assert err and "Unknown" in err
