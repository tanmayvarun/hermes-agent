from __future__ import annotations

import math

from plugin.perception.observation import AxNode, Observation
from plugin.perception.ocr.base import OCRRun, OCRSpan
from plugin.perception.ocr.recovery import recover_observation_with_ocr
from plugin.perception.ocr.selector import OCRSelector


class _FakeEngine:
    def __init__(self, engine_id: str, runs: list[OCRRun]) -> None:
        self.engine_id = engine_id
        self._runs = runs
        self.calls: list[str] = []

    def recognize(self, screenshot_path: str, *, use_case: str = "") -> OCRRun:
        self.calls.append(use_case)
        if self._runs:
            return self._runs.pop(0)
        return OCRRun(engine_id=self.engine_id, use_case=use_case, spans=[])


def test_selector_prefers_engine_by_use_case_and_success_rate():
    selector = OCRSelector(min_learn_attempts=1)

    class Easy:
        engine_id = "easyocr"

    class Paddle:
        engine_id = "paddleocr"

    engines = [Easy(), Paddle()]
    assert selector.rank(engines, use_case="pdf invoice scan")[0].engine_id == "paddleocr"
    assert selector.rank(engines, use_case="whatsapp chat")[0].engine_id == "easyocr"

    selector.record("whatsapp chat", OCRRun(engine_id="easyocr", use_case="whatsapp chat", spans=[]))
    selector.record("whatsapp chat", OCRRun(engine_id="easyocr", use_case="whatsapp chat", spans=[]))
    selector.record(
        "whatsapp chat",
        OCRRun(
            engine_id="paddleocr",
            use_case="whatsapp chat",
            spans=[OCRSpan(text="Zarooratwala", confidence=0.92)],
        ),
    )
    selector.record(
        "whatsapp chat",
        OCRRun(
            engine_id="paddleocr",
            use_case="whatsapp chat",
            spans=[OCRSpan(text="Zarooratwala", confidence=0.91)],
        ),
    )
    assert selector.rank(engines, use_case="whatsapp chat")[0].engine_id == "paddleocr"


def test_recovery_switches_between_engines_based_on_success(monkeypatch):
    selector = OCRSelector(min_learn_attempts=1)
    easy = _FakeEngine(
        "easyocr",
        [OCRRun(engine_id="easyocr", use_case="whatsapp chat", spans=[])],
    )
    paddle = _FakeEngine(
        "paddleocr",
        [
            OCRRun(
                engine_id="paddleocr",
                use_case="whatsapp chat",
                spans=[OCRSpan(text="Zarooratwala", confidence=0.94, bbox=(10.0, 20.0, 40.0, 12.0))],
            )
        ],
    )
    monkeypatch.setattr(
        "plugin.perception.ocr.recovery.available_ocr_engines",
        lambda: [easy, paddle],
    )

    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[],
        screenshot_path="/tmp/fake.png",
        coverage=0.05,
        degraded=True,
    )
    recovered = recover_observation_with_ocr(obs, use_case="whatsapp chat", selector=selector)

    assert recovered.source == "screen2ax:paddleocr"
    assert len(recovered.nodes) == 1
    assert recovered.nodes[0].attributes.get("ocr") is True
    assert recovered.nodes[0].attributes.get("ocr_engine") == "paddleocr"
    assert recovered.meta["ocr"]["selected_engine"] == "paddleocr"
    assert easy.calls == ["whatsapp chat"]
    assert paddle.calls == ["whatsapp chat"]
    assert selector.success_rate("whatsapp chat", "paddleocr") == 1.0


def test_forced_ocr_retry_applies_even_with_high_coverage(monkeypatch):
    selector = OCRSelector(min_learn_attempts=1)
    easy = _FakeEngine(
        "easyocr",
        [
            OCRRun(
                engine_id="easyocr",
                use_case="whatsapp chat",
                spans=[OCRSpan(text="Attachment", confidence=0.87, bbox=(3.0, 4.0, 20.0, 10.0))],
            )
        ],
    )
    monkeypatch.setattr(
        "plugin.perception.ocr.recovery.available_ocr_engines",
        lambda: [easy],
    )

    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[AxNode(role="AXButton", name="Search", bbox=(0.0, 0.0, 10.0, 10.0))],
        screenshot_path="/tmp/fake.png",
        coverage=1.0,
        degraded=False,
    )
    recovered = recover_observation_with_ocr(obs, use_case="whatsapp chat", force=True, selector=selector)

    assert recovered.source == "screen2ax:easyocr"
    assert len(recovered.nodes) == 2
    assert recovered.meta["ocr"]["status"] == "applied"
    assert recovered.meta["ocr"]["selected_engine"] == "easyocr"


def _whatsapp_obs(*, coverage: float, source: str = "macapptree") -> Observation:
    return Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[AxNode(role="AXButton", name="Search", bbox=(0.0, 0.0, 10.0, 10.0))],
        screenshot_path="/tmp/fake.png",
        source=source,
        coverage=coverage,
        degraded=False,
    )


def test_maybe_recover_is_adaptive_noop_when_coverage_is_high(monkeypatch):
    # OCR is enabled, but when accessibility already covers the surface there is
    # nothing to recover: unforced recovery on high coverage is a no-op.
    easy = _FakeEngine(
        "easyocr",
        [OCRRun(engine_id="easyocr", use_case="whatsapp chat", spans=[OCRSpan(text="Search", confidence=0.93)])],
    )
    monkeypatch.setattr("plugin.perception.ocr.recovery.available_ocr_engines", lambda: [easy])
    monkeypatch.delenv("HERMES_PERCEPTION_OCR", raising=False)
    from plugin.perception.macos.fusion.coverage import maybe_recover_with_ocr

    obs = _whatsapp_obs(coverage=1.0)
    recovered = maybe_recover_with_ocr(obs, use_case="whatsapp chat", force=False)

    assert recovered is obs
    assert "ocr" not in recovered.meta


def test_maybe_recover_runs_ocr_when_accessibility_is_blind(monkeypatch):
    # The regression case: a chrome-only AX tree. OCR must recover content so the
    # perceptor is not blind. Coverage is thin -> unforced recovery still fires.
    easy = _FakeEngine(
        "easyocr",
        [
            OCRRun(
                engine_id="easyocr",
                use_case="whatsapp chat",
                spans=[OCRSpan(text="Zarooratwala", confidence=0.9, bbox=(10.0, 20.0, 80.0, 16.0))],
            )
        ],
    )
    monkeypatch.setattr("plugin.perception.ocr.recovery.available_ocr_engines", lambda: [easy])
    monkeypatch.delenv("HERMES_PERCEPTION_OCR", raising=False)
    from plugin.perception.macos.fusion.coverage import maybe_recover_with_screen2ax

    obs = _whatsapp_obs(coverage=0.05)
    recovered = maybe_recover_with_screen2ax(obs)

    assert recovered.source == "screen2ax:easyocr"
    assert any(n.attributes.get("ocr") for n in recovered.nodes)
    assert recovered.meta["ocr"]["status"] == "applied"


def test_ocr_can_be_disabled_by_env(monkeypatch):
    easy = _FakeEngine(
        "easyocr",
        [OCRRun(engine_id="easyocr", use_case="whatsapp chat", spans=[OCRSpan(text="X", confidence=0.9)])],
    )
    monkeypatch.setattr("plugin.perception.ocr.recovery.available_ocr_engines", lambda: [easy])
    monkeypatch.setenv("HERMES_PERCEPTION_OCR", "0")
    from plugin.perception.macos.fusion.coverage import maybe_recover_with_ocr

    obs = _whatsapp_obs(coverage=0.05)
    recovered = maybe_recover_with_ocr(obs, use_case="whatsapp chat", force=True)

    assert recovered is obs
    assert "ocr" not in recovered.meta


def test_vision_interpreter_uses_ocr_confidence():
    from plugin.perception.interpreters.vision import VisionInterpreter
    from plugin.perception.sources.base import ObservationBundle

    obs = Observation(
        timestamp=0.0,
        app_name="WhatsApp",
        window_name="WhatsApp",
        nodes=[
            AxNode(
                role="AXStaticText",
                name="Zarooratwala",
                bbox=(10.0, 20.0, 80.0, 16.0),
                attributes={"ocr": True, "ocr_confidence": 0.43},
            )
        ],
        source="screen2ax:paddleocr",
    )
    bundle = ObservationBundle(source_id="screen2ax", observation=obs, coverage_self=0.5, degraded=True)
    hyps = VisionInterpreter().interpret(bundle)

    assert len(hyps) == 1
    assert math.isclose(hyps[0].confidence, 0.43, rel_tol=0.0, abs_tol=1e-6)


class _Box:
    """Stand-in for a Vision bounding box: normalized, bottom-left origin."""

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.origin = type("O", (), {"x": x, "y": y})()
        self.size = type("S", (), {"width": w, "height": h})()


def test_vision_boxes_are_converted_to_top_left_image_pixels():
    """Vision measures in fractions from the bottom; everything else counts
    pixels from the top.

    Neither half of that conversion announces itself when it is wrong. Skipping
    the scale yields boxes under a pixel wide, which read as an OCR that found
    nothing; skipping the flip mirrors every box about the horizontal midline,
    which reads as the perceptor naming one row and the click landing on
    another -- the failure this engine was added to fix, reintroduced by its
    own geometry.
    """
    from plugin.perception.ocr.engines import _bbox_from_vision

    # A band across the top of a 1000x500 image: Vision reports it near y=1.0.
    x, y, w, h = _bbox_from_vision(_Box(0.1, 0.9, 0.5, 0.05), 1000.0, 500.0)
    assert math.isclose(x, 100.0) and math.isclose(w, 500.0)
    assert math.isclose(y, 25.0), "a box near Vision's y=1.0 belongs at the top of the image"
    assert math.isclose(h, 25.0)

    # And a band across the bottom lands at the bottom.
    _, y_low, _, h_low = _bbox_from_vision(_Box(0.1, 0.0, 0.5, 0.05), 1000.0, 500.0)
    assert math.isclose(y_low + h_low, 500.0)

    # Junk in, empty box out, rather than an exception mid-observation.
    assert _bbox_from_vision(None, 1000.0, 500.0) == (0.0, 0.0, 0.0, 0.0)


def test_the_native_engine_leads_the_cold_start_order_for_ui_screens():
    """Before any success rate is measured, the fast engine should be first.

    Measured on the same window capture, easyocr took 14-16s and VisionKit
    0.7-1.0s for text at least as good. A live run spent 165s of a four-minute
    attempt inside easyocr; on a screen the agent is about to act on, a read
    that slow describes a screen that has moved on.
    """
    from plugin.perception.ocr.selector import OCRSelector

    class _Stub:
        def __init__(self, engine_id: str) -> None:
            self.engine_id = engine_id

    selector = OCRSelector()
    engines = [_Stub("easyocr"), _Stub("paddleocr"), _Stub("visionkit")]
    assert selector.rank(engines, use_case="whatsapp chat")[0].engine_id == "visionkit"
    # A document still prefers the layout-aware engine.
    assert selector.rank(engines, use_case="pdf invoice scan")[0].engine_id == "paddleocr"
