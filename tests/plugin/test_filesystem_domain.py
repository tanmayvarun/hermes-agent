"""The filesystem domain proves the executive machinery is domain-general.

These tests drive a Finder goal through the same executive pieces the WhatsApp
loop uses -- overlay resolution, workspace, sufficiency, meta-actions, questions,
capability registry -- without any WhatsApp vocabulary.
"""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.apps.filesystem import FilesystemOverlay
from plugin.agent.apps.generic import GenericOverlay
from plugin.agent.apps.registry import get_overlay
from plugin.agent.goal import Goal


class _Ent:
    def __init__(self, id_, label, visible=True, role="file"):
        self.id = id_
        self.label = label
        self.visible = visible
        self.semantic_role = role
        self.kind = role


class _World:
    def __init__(self, entities, app="Finder", opened=""):
        self.entities = {e.id: e for e in entities}
        self.active_app = app
        self.current_screen = SimpleNamespace(id="s", label="window", kind="list", signature="sig")
        self.overlay_hints = {"fs_opened_file": opened}


def _fs_goal(kind="fs_locate_file", name="report.pdf"):
    return Goal(kind=kind, app="Finder", link_query=name)


# ------------------------------------------------------------ registry fix


def test_finder_resolves_to_the_filesystem_overlay_not_whatsapp():
    assert isinstance(get_overlay("Finder"), FilesystemOverlay)


def test_unknown_app_falls_back_to_generic_not_whatsapp():
    assert isinstance(get_overlay("SomeUnknownApp"), GenericOverlay)


# ---------------------------------------------------------- goal evaluation


def test_locate_goal_succeeds_when_file_is_reachable():
    overlay = FilesystemOverlay()
    world = _World([_Ent(1, "report.pdf"), _Ent(2, "notes.txt")])
    status = overlay.evaluate_goal(_fs_goal("fs_locate_file", "report.pdf"), world)
    assert status.succeeded is True


def test_locate_goal_pending_when_file_absent():
    overlay = FilesystemOverlay()
    world = _World([_Ent(1, "notes.txt")])
    status = overlay.evaluate_goal(_fs_goal("fs_locate_file", "report.pdf"), world)
    assert status.succeeded is False


def test_open_goal_needs_the_file_open_not_just_visible():
    overlay = FilesystemOverlay()
    reachable = _World([_Ent(1, "report.pdf")])
    assert overlay.evaluate_goal(_fs_goal("fs_open_file", "report.pdf"), reachable).succeeded is False
    opened = _World([_Ent(1, "report.pdf")], opened="report.pdf")
    assert overlay.evaluate_goal(_fs_goal("fs_open_file", "report.pdf"), opened).succeeded is True


def test_features_report_progress_from_reachability():
    overlay = FilesystemOverlay()
    world = _World([_Ent(1, "report.pdf")])
    feats = overlay.features(world, _fs_goal("fs_open_file", "report.pdf"))
    assert feats.has_named_entity is True
    assert feats.goal_progress == 0.6


def test_resolve_target_matches_by_filename():
    overlay = FilesystemOverlay()
    world = _World([_Ent(1, "report.pdf"), _Ent(2, "summary.pdf")])
    ent = overlay.resolve_target(world, "summary", action="open_entity")
    assert ent is not None and ent.label == "summary.pdf"


def test_filesystem_declares_a_gated_delete_prior_like_the_picker_send():
    overlay = FilesystemOverlay()
    assert overlay.affordance_priors("list") == []
    priors = overlay.affordance_priors("confirm_delete")
    assert priors and priors[0]["family"] == "commit_irreversible"


# ---------------------------------------------- executive machinery reuse


def test_the_same_workspace_and_sufficiency_run_a_finder_goal():
    from plugin.agent.executive import (
        ExecutiveWorkspace,
        GoalState,
        SufficiencyInputs,
        WorkspaceProposal,
        assess_sufficiency,
    )
    from plugin.agent.executive.meta_action import MetaContext, select_meta_action

    workspace = ExecutiveWorkspace(goal=GoalState(kind="fs_open_file", query="report.pdf"))
    # A gap: which of two similar files is the target? Exploration is keyed on it.
    workspace.commit(
        WorkspaceProposal(source="perception", frame=1, surface="list", phase="locate")
    )
    ledger = workspace.questions
    ledger.declare_gap("which report.pdf is the target?", question_id="which report?")
    ledger.ask("which report?", frame=1)

    suff = assess_sufficiency(
        SufficiencyInputs(blocking_uncertainties=workspace.questions.blocking_uncertainties())
    )
    choice = select_meta_action(MetaContext(sufficiency=suff))
    assert choice.action.value == "perceive"  # blocked → look, not act

    ledger.answer("which report?", "the one in Downloads")
    suff2 = assess_sufficiency(
        SufficiencyInputs(
            blocking_uncertainties=workspace.questions.blocking_uncertainties(),
            has_grounded_action=True,
        )
    )
    choice2 = select_meta_action(MetaContext(sufficiency=suff2, has_grounded_action=True))
    assert choice2.action.value == "act"  # resolved → commit


def test_capability_registry_serves_a_filesystem_shortlist():
    from plugin.agent.executive.capabilities import default_registry

    registry = default_registry()
    # Finder has a searchable window: locate_content should be retrievable.
    verbs = {d.verb for d in registry.retrieve(facts=["searchable_surface"], limit=9)}
    assert "locate_content" in verbs
