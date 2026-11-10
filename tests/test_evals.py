"""Quality gates for the deterministic scenario set."""

from evals.run import run


def test_20_or_more_scenarios_pass():
    result = run()
    assert result["total_scenarios"] >= 20
    assert result["failed"] == 0, result["failures"]
    assert result["external_requests"] == 0
