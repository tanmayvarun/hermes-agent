#!/bin/bash
set -u
cd /Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent || exit 1
export PATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent/.venv/bin:$PATH"
export PYTHONPATH="/Users/tanmayvarun/tanmay/ai/hermes-agent-dir/hermes-agent"
RUN_DIR="plugin/experiments/runs"
STAMP=$(date +%Y%m%d_%H%M%S)
CONSOLE="$RUN_DIR/terminal_observe_diag_${STAMP}_console.txt"
STATUS="$RUN_DIR/terminal_observe_diag_${STAMP}_status.txt"
{
  python - <<'PY'
from ApplicationServices import AXIsProcessTrusted
print("AX", AXIsProcessTrusted())
if not AXIsProcessTrusted():
    raise SystemExit(42)

from plugin.perception.macos.accessibility.observer import get_observer
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.entities.normalize import entities_from_observation
from plugin.worldmodel.scene.reconstruct import reconstruct_world_graph
from plugin.worldmodel.screens.detect import guess_screen_label
from plugin.worldmodel.pragmatic_role import (
    get_pragmatic_role, is_active_call_evidence, entity_display_text,
    apply_app_vocabulary_hints, WA_NAV_LABELS, WA_CTA_LABELS, WA_STATUS_LABELS,
    infer_pragmatic_role_stage2,
)
from plugin.agent.whatsapp_view import WhatsAppWorldView

obs = get_observer(with_screenshot=False).observe(app="WhatsApp")
ents = entities_from_observation(obs)
for e in ents:
    infer_pragmatic_role_stage2(e)
graph = reconstruct_world_graph(ents, app="WhatsApp")
apply_app_vocabulary_hints(ents, nav_labels=WA_NAV_LABELS, cta_labels=WA_CTA_LABELS, status_labels=WA_STATUS_LABELS)

wm = WorldModel()
wm.active_app = "WhatsApp"
wm.entities = {e.id: e for e in ents}
wm.tracker._entities = dict(wm.entities)

print("n_entities", len(ents))
print("guess_screen", repr(guess_screen_label(ents)))
print("regions", sorted({r.kind.value for r in graph.regions}))
view = WhatsAppWorldView.from_world_model(wm)
print("view.screen", view.screen, "call_state", view.call_state, "voice", view.voice_call_available, "composer", view.composer_visible)
print("open", view.open_conversation)

print("=== active_call_evidence ===")
for e in ents:
    if e.visible and is_active_call_evidence(e):
        print({
            "id": e.id, "type": e.entity_type, "label": (e.label or "")[:60],
            "sem": (e.semantic_role or "")[:40], "role": get_pragmatic_role(e).value,
            "bounds": e.bounds, "actions": e.actions, "display": entity_display_text(e)[:100],
        })

print("=== call-ish labels ===")
for e in ents:
    if not e.visible:
        continue
    lab = entity_display_text(e).lower()
    if any(x in lab for x in ("call", "voice", "ring", "end call", "decline")):
        print({
            "id": e.id, "type": e.entity_type, "label": (e.label or "")[:70],
            "role": get_pragmatic_role(e).value, "bounds": e.bounds,
            "active": is_active_call_evidence(e),
        })
PY
  echo $? > "$STATUS"
} 2>&1 | tee "$CONSOLE"
exit "$(cat "$STATUS")"
