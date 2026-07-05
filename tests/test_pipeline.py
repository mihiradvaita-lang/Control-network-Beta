"""Tests: pipeline smoke test, ZDR scrub, SSE event ordering/content, graceful degradation."""
import json

import app.scenarios as s
from app.pipeline import alert_from_scenario, triage_full, stream_triage_events
from app import zdr, narrative


def _parse_sse(raw: str):
    """Parse one SSE frame 'event: X\\ndata: {...}\\n\\n' into (event, data_dict)."""
    event = None
    data = None
    for line in raw.split("\n"):
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data = line[len("data:"):].strip()
    return event, (json.loads(data) if data is not None else None)


def _collect_events(scn: dict):
    return [_parse_sse(frame) for frame in stream_triage_events(scn)]


def test_all_scenarios_triage():
    for scn in s.SCENARIOS:
        out = triage_full(alert_from_scenario(dict(scn)))
        assert "Incident Report" in out["report_markdown"]
        assert "Advisory only" in out["report_markdown"]
        assert out["context_meta"]["tokens_after"] <= 2000


def test_zdr_scrub():
    d = {"a": 1, "b": "secret"}
    zdr.scrub(d)
    assert d == {}


def test_facts_event_present_and_ordered_before_token_and_done():
    scn = s.SCENARIOS[0]
    events = _collect_events(scn)
    names = [e for e, _ in events]

    assert "facts" in names
    facts_idx = names.index("facts")

    # facts must precede any token event and the done event
    token_indices = [i for i, n in enumerate(names) if n == "token"]
    done_idx = names.index("done")
    for ti in token_indices:
        assert facts_idx < ti
    assert facts_idx < done_idx

    # facts payload carries header metadata + a list of {key,value,provenance}
    _, facts_data = events[facts_idx]
    assert "pattern" in facts_data and "service" in facts_data and "facts" in facts_data
    for f in facts_data["facts"]:
        assert set(["key", "value", "provenance"]).issubset(f.keys())


def test_phase_events_in_order():
    scn = s.SCENARIOS[1]
    events = _collect_events(scn)
    phases = [data["phase"] for name, data in events if name == "phase"]
    assert phases == ["DETECTED", "CORRELATING", "ANALYZING", "DONE"]

    names = [e for e, _ in events]
    detected_idx = names.index("phase")  # first phase event = DETECTED
    correlating_idx = [i for i, (n, d) in enumerate(events) if n == "phase" and d["phase"] == "CORRELATING"][0]
    facts_idx = names.index("facts")
    analyzing_idx = [i for i, (n, d) in enumerate(events) if n == "phase" and d["phase"] == "ANALYZING"][0]
    token_indices = [i for i, n in enumerate(names) if n == "token"]
    done_phase_idx = [i for i, (n, d) in enumerate(events) if n == "phase" and d["phase"] == "DONE"][0]
    done_idx = names.index("done")

    assert detected_idx < correlating_idx < facts_idx < analyzing_idx
    if token_indices:
        assert analyzing_idx < min(token_indices)
    assert done_phase_idx < done_idx


def test_graceful_degradation_on_provider_failure(monkeypatch):
    """If the configured provider explodes for any reason, the stream must still complete
    with a `notice` event and a valid `done` event containing a report -- never crash."""
    def _boom(c, skill_md):
        raise RuntimeError("simulated network failure")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setitem(narrative._PROVIDERS, "anthropic", _boom)

    class _FakeSettings:
        llm_provider = "anthropic"
        anthropic_api_key = "fake-key-not-real"
        llm_model = "claude-haiku-4-5-20251001"
        llm_max_tokens = 500
        llm_temperature = 0.2
        token_hard_cap = 2000
        openai_base_url = ""
        openai_api_key = ""
        ollama_base_url = ""

        @property
        def llm_enabled(self):
            return True

        @property
        def active_provider(self):
            return "anthropic"

    import app.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(narrative, "get_settings", lambda: _FakeSettings())

    scn = s.SCENARIOS[2]
    events = _collect_events(scn)
    names = [e for e, _ in events]

    assert "error" not in names
    assert "notice" in names
    notice_data = dict(events[names.index("notice")][1])
    assert notice_data["level"] == "warning"

    assert "done" in names
    done_data = dict(events[names.index("done")][1])
    assert "Incident Report" in done_data["report_markdown"]
    assert done_data["llm"] == "deterministic"


def test_all_scenarios_have_evidence_and_analysis_sections():
    for scn in s.SCENARIOS:
        out = triage_full(alert_from_scenario(dict(scn)))
        md = out["report_markdown"]
        assert "Evidence" in md
        assert "Analysis" in md


# ---- connector tests (no network) ----
def test_default_data_source_is_sim_and_scenarios_triage():
    from app.config import get_settings
    s = get_settings()
    assert s.data_mode == "sim"
    assert s.prometheus_enabled is False
    assert s.datadog_enabled is False
    import app.scenarios as sc
    from app.pipeline import alert_from_scenario, triage_full
    for scn in sc.SCENARIOS:
        out = triage_full(alert_from_scenario(dict(scn)))
        assert "Incident Report" in out["report_markdown"]


def test_prometheus_parser_maps_vector():
    from app.collectors_real import parse_prom_scalar
    sample = {"status": "success", "data": {"resultType": "vector",
              "result": [{"metric": {"pod": "p"}, "value": [1720000000, "1073741824"]}]}}
    assert parse_prom_scalar(sample) == 1073741824.0
    assert parse_prom_scalar({"data": {"resultType": "vector", "result": []}}) is None


def test_datadog_parsers():
    from app.collectors_real import parse_dd_series_last, parse_dd_logs
    assert parse_dd_series_last({"series": [{"pointlist": [[1, 2.0], [3, 4.5]]}]}) == 4.5
    assert parse_dd_series_last({"series": []}) is None
    logs = parse_dd_logs({"data": [{"attributes": {"message": "boom"}}, {"attributes": {}}]})
    assert logs == ["boom"]


def test_health_reports_data_source():
    from app.health import health
    assert health()["data_source"] == "sim"
