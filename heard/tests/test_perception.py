import json
import pytest
from heard.app.pipeline import perception
from heard.app.schemas import Finding
from .conftest import FakeLLM, ROOT

GOOD = json.dumps({"findings": [{"id": "F1", "t_start": 7.0, "t_end": 8.0, "announced_text": "button", "visible_text_or_description": "cart icon",
                                 "issue_type": "missing_name", "severity": "high", "wcag_guess": "4.1.2", "evidence": "heard only 'button'"}]})
SESSION = ROOT / "data/sessions/shop_buggy"


def test_parse_strips_prose_and_fences():
    fl = perception.parse_findings("Sure!\n```json\n" + GOOD + "\n```")
    assert fl.findings[0].issue_type == "missing_name"


def test_schema_rejects_bad_issue_type():
    bad = GOOD.replace("missing_name", "made_up")
    with pytest.raises(Exception):
        perception.parse_findings(bad)


def test_retry_once_on_schema_failure():
    llm = FakeLLM({"perception": ["not json at all", GOOD]})
    out = perception.run_perception(llm, SESSION, {"PERCEPTION_MODE": "text_only_log"})
    assert len(llm.calls) == 2 and out["raw_count"] == 1


def test_fails_after_two_invalid_replies():
    llm = FakeLLM({"perception": ["nope", "still nope"]})
    with pytest.raises(RuntimeError):
        perception.run_perception(llm, SESSION, {"PERCEPTION_MODE": "text_only_log"})


def f(t, text):
    return Finding(id="F", t_start=t, t_end=t + 1, announced_text=text, visible_text_or_description="", issue_type="other",
                   severity="low", wcag_guess="4.1.2", evidence="")


def test_evidence_check_keeps_quoted_speech_and_rejects_invented():
    log = [{"t": 7.0, "text": "button"}, {"t": 30.0, "text": "Checkout, button"}]
    ok, rej = perception.evidence_check([f(7.2, "button"), f(7.2, "Delete account, button"), f(50, "button")], log, [])
    assert [x.announced_text for x in ok] == ["button"]
    assert len(rej) == 2 and "not found in speech log" in rej[0]["reason"]


def test_evidence_check_silence_needs_silent_step():
    steps = [{"t": 18.0, "silent": True}]
    ok, rej = perception.evidence_check([f(18.5, ""), f(40, "")], [], steps)
    assert len(ok) == 1 and len(rej) == 1


def test_perception_messages_adapt_to_mode():
    steps = json.loads((SESSION / "steps.json").read_text())
    m = perception.build_messages(SESSION, steps, "text_only_log", {})
    assert all(c["type"] == "text" for c in m[1]["content"])
    m = perception.build_messages(SESSION, steps, "native_av", {"tests": {"audio": {"working_variant": "input_audio_wav_b64"}}})
    assert {c["type"] for c in m[1]["content"]} == {"text", "video_url", "input_audio"}


def test_native_av_sends_the_recordings_own_audio():
    steps = json.loads((SESSION / "steps.json").read_text())
    caps = {"tests": {"audio": {"working_variant": "video_audio_track"}}}
    m = perception.build_messages(SESSION, steps, "native_av", caps)
    assert {c["type"] for c in m[1]["content"]} == {"text", "video_url"}
    assert m[1]["content"][0]["text"].startswith("The attached recording includes the screen reader's audio")
    assert perception.request_extra("native_av", caps) == {"mm_processor_kwargs": {"use_audio_in_video": True}}
    url = {"tests": {"audio": {"working_variant": "audio_url_data_uri"}}}
    parts = perception.build_messages(SESSION, steps, "native_av", url)[1]["content"]
    assert parts[-1]["type"] == "audio_url" and parts[-1]["audio_url"]["url"].startswith("data:audio/wav;base64,")
    assert perception.request_extra("native_av", url) is None and perception.request_extra("frames_plus_log", caps) is None


def test_evidence_accepts_spanning_quotes_and_written_out_silence():
    log = [{"t": 0.9, "text": "Sales dashboard, heading level 1"}, {"t": 4.1, "text": "Overview, heading level 3"}, {"t": 7.1, "text": "Export CSV, clickable"}]   # real dashboard timings: the pair spans 3.2s
    steps = [{"t": 9.6, "silent": True}]
    mk = lambda t, q: Finding(id="F", t_start=t, t_end=t, announced_text=q, visible_text_or_description="", issue_type="other",
                              severity="low", wcag_guess="", evidence="")
    ok, rej = perception.evidence_check([mk(0.9, "Sales dashboard, heading level 1 Overview, heading level 3"),   # two announcements quoted together
                                         mk(9.6, "(silence)"), mk(9.6, "silence"),                                   # silence written out
                                         mk(0.9, "Dashboard, heading level 2"),                                    # never said
                                         mk(0.9, "Overview, heading level 3 Sales dashboard")], log, steps)        # wrong order
    assert [f.announced_text for f in ok] == ["Sales dashboard, heading level 1 Overview, heading level 3", "(silence)", "silence"]
    assert len(rej) == 2
