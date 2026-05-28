import json

from offline_meeting_notes.__main__ import main
from offline_meeting_notes.evaluation import run_eval


def test_eval_report_scores_fixture_set() -> None:
    report = run_eval()

    assert report.totals["fixtures"] >= 6
    assert report.totals["expected_actions"] >= 8
    assert report.totals["owner_accuracy"] >= 0.75
    assert report.totals["citation_coverage"] > 0


def test_eval_cli_text_output(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["eval"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Offline Note Taker Eval" in output
    assert "| Fixture |" in output


def test_eval_cli_json_output(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["eval", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert "cases" in payload
    assert "totals" in payload
