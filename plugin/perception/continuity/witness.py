"""Cheap reads of the live screen, used to check that perception has not gone stale.

The agent perceives, thinks, and only then acts. Measured on live runs the screen
is photographed, ~30s go into perception and judgement, ~25s more into the
decision, and only then does the click land — 35 to 76 seconds after the pixels
that justify it were read. A chat list reorders many times in a minute, so a
coordinate resolved from that photograph is a guess by the time it is used.

Two kinds of read live here, and they answer different questions.

**Surface** (:func:`take_surface`) — who is frontmost, which window, where it sits.
Pure window-server metadata, microseconds, no pixels. Compared between perception
time and actuation time it catches the coarse catastrophes: the user switched
app, the window closed, the window moved and took every resolved coordinate with
it.

**Read-back** (:func:`read_back`) — what text is *actually* in the target
rectangle, right now. This is the check that matters, and it is deliberately not
a before/after comparison: since the "before" picture is itself a minute old,
diffing two stale stamps proves nothing. Instead the live rectangle is compared
against what the decision *expected* to be there. "Am I about to click the thing
I meant to click?" is answerable in 30ms and is exactly the question.

A note on an approach that was tried and rejected, because it looks obviously
right and is not. The first version hashed the target rectangle perceptually
(difference hash) and compared frames. Measured against rendered chat rows, two
*different contacts* differed by 8 bits out of 256 while a 2px shift differed by
7 and a blinking caret by 5 — signal and noise the same size, at every grid size
tried. The reason is structural rather than a tuning miss: a perceptual hash is
built to be invariant to small visual changes, and "different text in an
identical layout" is precisely that. The avatar and the two-line layout dominate
the bits; the glyphs carrying the meaning are a rounding error. Pixel hashing
survives here only for targets with no text at all (icon buttons), where there is
no same-layout-different-glyphs trap and structure really is the content.
"""

from __future__ import annotations

import io
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Coarse grid for the icon-target fallback. Icons are structural, so this is the
# one case a perceptual hash is the right instrument.
ICON_GRID = 8

# Rectangles below this are too small to read or hash meaningfully.
MIN_REGION_PX = 6

# Grown around the target before reading. A control that shifted a few pixels is
# still the same control, but something arriving *next to* it — a menu opening
# over it, a row inserted above — moves into this margin and gets caught.
READ_MARGIN_PX = 6

# The band read back around an *estimated* point (see TargetExpectation.estimated).
# Sized to a list row rather than to the estimate: wide enough to contain a whole
# label and its preview text, shallow enough that the row above or below does not
# bleed in and let a neighbour satisfy the match.
ESTIMATE_BAND_W = 340.0
ESTIMATE_BAND_H = 44.0

_STOPWORDS = frozenset({"the", "a", "an", "to", "from", "for", "of", "on", "in", "and", "with", "chat", "message"})


def norm_app(name: Any) -> str:
    """App name with invisible format marks dropped, lowercased.

    macOS reports WhatsApp as ``"\u200eWhatsApp"``; raw equality silently misses it.
    """
    text = str(name or "")
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(cleaned.strip().lower().split())


def norm_text(value: Any) -> str:
    """Lowercased text with punctuation and symbols reduced to single spaces.

    OCR renders emoji as garbage ("Mum ❤️" comes back as "Mum EIEI") and WhatsApp
    truncates long names with an ellipsis, so comparison has to happen on the
    alphanumeric skeleton rather than the literal string.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def significant_tokens(value: Any) -> List[str]:
    """Distinctive words of a label — what a match should actually turn on."""
    return [t for t in norm_text(value).split() if len(t) >= 3 and t not in _STOPWORDS]


@dataclass(frozen=True)
class Surface:
    """Window-server facts about the task app's surface at one instant."""

    taken_at: float = 0.0
    frontmost_app: str = ""
    window_id: Optional[int] = None
    window_bounds: Optional[Tuple[float, float, float, float]] = None
    window_title: str = ""
    readable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"frontmost_app": self.frontmost_app, "window_id": self.window_id}
        if self.window_bounds:
            out["window_bounds"] = [round(float(v), 1) for v in self.window_bounds]
        if self.window_title:
            out["window_title"] = self.window_title[:80]
        if not self.readable:
            out["readable"] = False
        return out


@dataclass(frozen=True)
class TargetExpectation:
    """What the decision believes sits at the point it is about to act on.

    ``label`` is the decision's own semantic target, which is what makes the
    read-back a check on *intent* rather than on pixels. ``irreversible`` marks
    the steps where being wrong cannot be undone — sending to the wrong contact —
    and flips an unreadable screen from "proceed" to "stop".
    """

    bounds: Optional[Tuple[float, float, float, float]] = None
    label: str = ""
    needs_foreground: bool = True
    irreversible: bool = False
    # True when the rectangle is a fixed-size box synthesised around a point the
    # vision model estimated, rather than a measured extent of a real control.
    # The distinction changes what the read-back can honestly conclude: a
    # measured rectangle either holds the target or does not, while an estimated
    # one is a guess whose error is the size of the guess. Judging the latter as
    # strictly as the former refuses correct clicks -- observed live, where a
    # point landing on the right chat row read back the fragment 'ala' from
    # "zarooratwala" and was rejected for not being the whole label.
    estimated: bool = False

    @property
    def grounded(self) -> bool:
        if not self.bounds or len(self.bounds) < 4:
            return False
        return float(self.bounds[2]) >= MIN_REGION_PX and float(self.bounds[3]) >= MIN_REGION_PX

    @property
    def has_text(self) -> bool:
        return bool(significant_tokens(self.label))

    def padded(self, margin: float = READ_MARGIN_PX) -> Optional[Tuple[float, float, float, float]]:
        if not self.grounded:
            return None
        x, y, w, h = (float(v) for v in self.bounds[:4])  # type: ignore[index]
        if self.estimated:
            # Read the band the target plausibly occupies, not the guess box. A
            # list row spans the pane's width while the estimate is a small
            # square, so a tight read catches a few characters mid-word and
            # decides the row is something else. The question worth asking of an
            # estimate is "is my work area still here", and that is a question
            # about the row.
            cx, cy = x + w / 2.0, y + h / 2.0
            return (
                cx - ESTIMATE_BAND_W / 2.0,
                cy - ESTIMATE_BAND_H / 2.0,
                ESTIMATE_BAND_W,
                ESTIMATE_BAND_H,
            )
        return (x - margin, y - margin, w + 2 * margin, h + 2 * margin)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"grounded": self.grounded, "has_text": self.has_text}
        if self.label:
            out["label"] = self.label[:120]
        if self.bounds:
            out["bounds"] = [round(float(v), 1) for v in self.bounds[:4]]
        if self.irreversible:
            out["irreversible"] = True
        return out


@dataclass(frozen=True)
class ReadBack:
    """What was actually found in the target rectangle, live."""

    lines: Tuple[str, ...] = ()
    matched: bool = False
    method: str = ""       # ocr | icon_hash | none
    detail: str = ""
    icon_hash: str = ""
    took_ms: float = 0.0

    @property
    def saw_text(self) -> bool:
        return bool(self.lines)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"matched": bool(self.matched), "method": self.method}
        if self.lines:
            out["lines"] = [l[:80] for l in self.lines[:6]]
        if self.detail:
            out["detail"] = self.detail
        if self.icon_hash:
            out["icon_hash"] = self.icon_hash
        if self.took_ms:
            out["took_ms"] = round(self.took_ms, 1)
        return out


# --- window server (microseconds) --------------------------------------------


def frontmost_app_name() -> str:
    """Frontmost application per ``NSWorkspace``, or "" when undeterminable.

    Ground truth about who owns the keyboard, as opposed to what the vision model
    inferred from pixels. Returns "" rather than raising, so a missing signal
    degrades the check instead of breaking actuation.
    """
    try:
        from AppKit import NSWorkspace  # type: ignore
    except Exception:
        return ""
    try:
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication() if workspace is not None else None
        return str(app.localizedName() or "") if app is not None else ""
    except Exception:
        return ""


def window_snapshot(app_name: str) -> Tuple[Optional[int], Optional[Tuple[float, float, float, float]], str]:
    """The app's largest normal window as ``(id, bounds, title)``.

    One pass yields all three; the witness needs the geometry as well as the id,
    because a window that moved has invalidated every coordinate resolved against
    it even though its identity is unchanged.
    """
    target = norm_app(app_name)
    if not target:
        return None, None, ""
    try:
        from Quartz import (  # type: ignore
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None, None, ""
    try:
        infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    except Exception:
        return None, None, ""

    best_id: Optional[int] = None
    best_bounds: Optional[Tuple[float, float, float, float]] = None
    best_title = ""
    best_area = 0.0
    for info in infos:
        owner = norm_app(info.get("kCGWindowOwnerName"))
        if owner != target and target not in owner and owner not in target:
            continue
        # Layer 0 is a normal application window; menubar extras, overlays and
        # shadows live elsewhere and must not win the size comparison.
        if info.get("kCGWindowLayer") not in (0, None):
            continue
        raw = info.get("kCGWindowBounds") or {}
        try:
            x, y = float(raw.get("X", 0.0)), float(raw.get("Y", 0.0))
            w, h = float(raw.get("Width", 0.0)), float(raw.get("Height", 0.0))
        except (TypeError, ValueError):
            continue
        if w * h <= best_area:
            continue
        best_area = w * h
        best_bounds = (x, y, w, h)
        num = info.get("kCGWindowNumber")
        best_id = int(num) if num is not None else None
        best_title = str(info.get("kCGWindowName") or "")
    return best_id, best_bounds, best_title


def take_surface(app_name: str) -> Surface:
    """Stamp the app's surface now. Never raises."""
    frontmost = frontmost_app_name()
    window_id, bounds, title = window_snapshot(app_name)
    return Surface(
        taken_at=time.time(),
        frontmost_app=frontmost,
        window_id=window_id,
        window_bounds=bounds,
        window_title=title,
        readable=bool(frontmost) or window_id is not None,
    )


# --- pixels (milliseconds) ----------------------------------------------------


def capture_rect(rect: Tuple[float, float, float, float]) -> Optional[Any]:
    """Grab a screen rectangle as a PIL image, in-process.

    ``CGWindowListCreateImage`` composites straight from the window server. A
    subprocess ``screencapture`` would cost more in spawn time alone than this
    entire check is allowed to take.
    """
    try:
        x, y, w, h = (float(v) for v in rect)
    except (TypeError, ValueError):
        return None
    if w < MIN_REGION_PX or h < MIN_REGION_PX:
        return None
    try:
        from PIL import Image  # type: ignore
        from Quartz import (  # type: ignore
            CGDataProviderCopyData,
            CGImageGetBytesPerRow,
            CGImageGetDataProvider,
            CGImageGetHeight,
            CGImageGetWidth,
            CGRectMake,
            CGWindowListCreateImage,
            kCGNullWindowID,
            kCGWindowImageBoundsIgnoreFraming,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None
    try:
        image = CGWindowListCreateImage(
            CGRectMake(x, y, w, h),
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
            kCGWindowImageBoundsIgnoreFraming,
        )
        if image is None:
            return None
        width, height = int(CGImageGetWidth(image)), int(CGImageGetHeight(image))
        if width <= 0 or height <= 0:
            return None
        raw = CGDataProviderCopyData(CGImageGetDataProvider(image))
        if raw is None:
            return None
        stride = int(CGImageGetBytesPerRow(image))
        # Premultiplied BGRA at the display's backing scale; downstream resizes,
        # so Retina needs no special case.
        return Image.frombuffer("RGBA", (width, height), bytes(raw), "raw", "BGRA", stride, 1)
    except Exception as exc:
        logger.debug("continuity capture failed for rect=%s: %s", rect, exc)
        return None


def ocr_image(image: Any, *, accurate: bool = True) -> List[str]:
    """Recognised text lines via the macOS Vision framework.

    Native, no model download, ~30ms accurate / ~7ms fast for a small rectangle —
    trivial next to the ~60s staleness it guards against. Language correction is
    off because contact names are proper nouns that correction actively harms.
    """
    try:
        import Quartz  # type: ignore
        import Vision  # type: ignore
        from Foundation import NSData  # type: ignore
    except Exception:
        return []
    try:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        payload = buf.getvalue()
        data = NSData.dataWithBytes_length_(payload, len(payload))
        source = Quartz.CGImageSourceCreateWithData(data, None)
        if source is None:
            return []
        cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
        if cg_image is None:
            return []
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(
            Vision.VNRequestTextRecognitionLevelAccurate
            if accurate
            else Vision.VNRequestTextRecognitionLevelFast
        )
        request.setUsesLanguageCorrection_(False)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        handler.performRequests_error_([request], None)
        lines: List[str] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates and len(candidates):
                lines.append(str(candidates[0].string()))
        return lines
    except Exception as exc:
        logger.debug("continuity OCR failed: %s", exc)
        return []


def dhash(image: Any, grid: int = ICON_GRID) -> str:
    """Difference hash: each pixel compared to its right-hand neighbour.

    Used only for text-free targets. Difference rather than average hashing so
    that the uniform dimming macOS applies to a window that loses key status does
    not read as a change.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return ""
    try:
        small = image.convert("L").resize((grid + 1, grid), Image.BILINEAR)
    except Exception:
        return ""
    pixels = list(small.getdata())
    bits = [
        "1" if pixels[r * (grid + 1) + c] < pixels[r * (grid + 1) + c + 1] else "0"
        for r in range(grid)
        for c in range(grid)
    ]
    return f"{int(''.join(bits) or '0', 2):0{(grid * grid) // 4}x}"


def hamming(a: str, b: str) -> int:
    """Differing bits between two hex hashes; ``-1`` when incomparable."""
    if not a or not b or len(a) != len(b):
        return -1
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return -1


def label_present(expected: str, lines: Sequence[str]) -> Tuple[bool, str]:
    """Whether the expected label is still among the text found in the rectangle.

    Deliberately lenient about form and strict about identity. WhatsApp truncates
    long names with an ellipsis and OCR mangles emoji, so an exact string test
    would reject the right row constantly; but a match still has to rest on a
    distinctive word, so a *different* contact cannot satisfy it. Single-token
    labels are additionally allowed to match as a prefix, which is how a
    truncated "Zaroorat…" is recognised as "Zarooratwala Orders".
    """
    wanted = significant_tokens(expected)
    if not wanted:
        return False, "no distinctive tokens in expected label"
    haystack = norm_text(" ".join(lines))
    if not haystack:
        return False, "no text found"
    hits = [t for t in wanted if t in haystack]
    if hits:
        return True, f"matched {', '.join(hits[:3])}"
    # Truncation: the rendered row may hold only the first few characters.
    for token in wanted:
        for found in haystack.split():
            if len(found) >= 4 and (token.startswith(found) or found.startswith(token)):
                return True, f"prefix match {found!r}~{token!r}"
    # Clipping: the read rectangle can cut a word, so OCR returns its middle or
    # tail — 'ala' out of "zarooratwala". A fragment that only occurs inside a
    # word the target is expected to contain is evidence the target is there,
    # not evidence against it. Rejecting it refuses correct clicks, which is the
    # costlier error: the run stalls, whereas a slightly-wrong click is caught
    # by the ordinary transition machinery.
    for token in wanted:
        for found in haystack.split():
            if len(found) >= 3 and found in token:
                return True, f"fragment match {found!r} within {token!r}"
    return False, f"expected {'/'.join(wanted[:3])}, found {haystack[:60]!r}"


def read_back(expectation: TargetExpectation) -> ReadBack:
    """Read the target rectangle live and judge it against the decision's intent.

    Text targets are read with OCR and matched on the label. Text-free targets
    (icon buttons) fall back to a structural hash, which the caller compares
    against the hash recorded when the target was resolved.
    """
    started = time.perf_counter()
    rect = expectation.padded()
    if rect is None:
        return ReadBack(method="none", detail="target has no usable bounds")

    image = capture_rect(rect)
    if image is None:
        return ReadBack(
            method="none",
            detail="could not capture the target rectangle",
            took_ms=(time.perf_counter() - started) * 1000.0,
        )

    if not expectation.has_text:
        return ReadBack(
            method="icon_hash",
            icon_hash=dhash(image),
            detail="text-free target; structural hash only",
            took_ms=(time.perf_counter() - started) * 1000.0,
        )

    lines = ocr_image(image)
    matched, detail = label_present(expectation.label, lines)
    return ReadBack(
        lines=tuple(lines),
        matched=matched,
        method="ocr",
        detail=detail,
        took_ms=(time.perf_counter() - started) * 1000.0,
    )


def expectation_from(
    bounds: Optional[Sequence[float]],
    *,
    label: str = "",
    needs_foreground: bool = True,
    irreversible: bool = False,
    estimated: bool = False,
) -> TargetExpectation:
    """Build an expectation from any ``(x, y, w, h)`` sequence, tolerating junk."""
    coerced: Optional[Tuple[float, float, float, float]] = None
    if bounds and len(bounds) >= 4:
        try:
            coerced = tuple(float(v) for v in list(bounds)[:4])  # type: ignore[assignment]
        except (TypeError, ValueError):
            coerced = None
    return TargetExpectation(
        bounds=coerced,
        label=str(label or ""),
        needs_foreground=bool(needs_foreground),
        irreversible=bool(irreversible),
        estimated=bool(estimated),
    )
