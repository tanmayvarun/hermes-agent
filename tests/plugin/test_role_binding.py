"""Typed role-binding: domain evidence in, generic identity out."""

from plugin.agent.procedures.forward_message import forward_role_specs
from plugin.agent.role_binding import (
    REFERENT_MISMATCH,
    BindingRecord,
    EntityObservation,
    IdentityEvidence,
    RoleBinder,
    apply_referent_mismatch,
    assess_candidate_for_role,
    assess_observation_for_role,
    is_negatively_evidenced,
    propose_binding,
)


class _Goal:
    contact = "Pallavi"
    link_query = "zarooratwala"
    target_contact = "Tanmay"


def _specs():
    return forward_role_specs(_Goal())


def test_core_has_no_whatsapp_row_extraction():
    import inspect
    import plugin.agent.role_binding as rb

    src = inspect.getsource(rb)
    for banned in (
        "_row_contact_name",
        "chat_row",
        "whatsapp_view",
        "open_matches_referent",
        "source_query_binding",
        "extract_contact_name",
    ):
        assert banned not in src, f"core still contains {banned!r}"


def test_container_title_vs_preview_content_via_typed_evidence():
    """Descendant preview must not redefine container identity."""
    specs = _specs()
    obs = EntityObservation(
        entity_kind="conversation",
        entity_id="c1",
        label="Pallavi",
        identity_evidence=[
            IdentityEvidence(kind="display_name", value="Pallavi", confidence=0.96)
        ],
        content_evidence=[
            IdentityEvidence(
                kind="preview_text",
                value="https://youtu.be/rHJdc-jkxys",
                identity_bearing=False,
            )
        ],
    )
    a = assess_observation_for_role(
        spec=specs["source_container"],
        observation=obs,
        goal=_Goal(),
        task_relevance=0.4,
    )
    assert a.binding_eligible is True
    # Same entity as source_object: container kind is invalid for object role.
    obj = assess_observation_for_role(
        spec=specs["source_object"],
        observation=obs,
        goal=_Goal(),
        task_relevance=0.9,
        bindings={"source_container": {"resolved_label": "Pallavi"}},
    )
    assert obj.binding_eligible is False


def test_whatsapp_adapter_splits_preview_before_core_sees_it():
    """Adapter may know rows; core only sees display_name vs preview_text."""
    from plugin.agent.composition import compose_domain_adapters
    from plugin.agent.identity_evidence.whatsapp import WhatsAppUIEvidenceProvider

    compose_domain_adapters()
    obs = WhatsAppUIEvidenceProvider().observe(
        {
            "label": "Pallavi - You: https://youtu.be/rHJdc-jkxys",
            "kind": "chat_row",
            "domain": "whatsapp",
        }
    )
    assert any(
        e.kind == "display_name" and e.value == "Pallavi" for e in obs.identity_evidence
    )
    assert any(
        e.kind == "preview_text" and "youtu" in str(e.value).lower()
        for e in obs.content_evidence
    )
    a = assess_candidate_for_role(
        spec=_specs()["source_container"],
        candidate={
            "label": "Pallavi - You: https://youtu.be/rHJdc-jkxys",
            "kind": "chat_row",
            "domain": "whatsapp",
        },
        goal=_Goal(),
        task_relevance=0.4,
    )
    assert a.binding_eligible is True


def test_brand_search_row_fails_container_despite_high_relevance():
    a = assess_candidate_for_role(
        spec=_specs()["source_container"],
        candidate={
            "label": "ZarooratWala – Fresh Groceries Delivery",
            "kind": "search_result_row",
            "domain": "whatsapp",
            "text": "ZarooratWala zarooratwala.com",
        },
        goal=_Goal(),
        task_relevance=0.99,
    )
    assert a.task_relevance == 0.99
    assert a.binding_eligible is False


def test_adversarial_mashup_with_participants_fails_container():
    a = assess_candidate_for_role(
        spec=_specs()["source_container"],
        candidate={
            "label": "Pallavi ZarooratWala",
            "kind": "search_result_row",
            "domain": "whatsapp",
            "participants": ["Other Contact"],
        },
        goal=_Goal(),
        task_relevance=0.95,
    )
    assert a.binding_eligible is False


def test_source_object_requires_container_then_query():
    msg = {
        "label": "https://www.zarooratwala.com/fresh",
        "text": "https://www.zarooratwala.com/fresh",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Pallavi",
        "sender": "Pallavi",
    }
    before = assess_candidate_for_role(
        spec=_specs()["source_object"],
        candidate=msg,
        goal=_Goal(),
        task_relevance=0.95,
        bindings={},
    )
    assert before.binding_eligible is False
    after = assess_candidate_for_role(
        spec=_specs()["source_object"],
        candidate=msg,
        goal=_Goal(),
        task_relevance=0.95,
        bindings={"source_container": {"resolved_label": "Pallavi"}},
    )
    assert after.binding_eligible is True


def test_you_message_high_relevance_not_binding_eligible_as_from_pallavi():
    """Container+content match with sender=You must not bind as from Pallavi."""
    from plugin.agent.composition import compose_domain_adapters

    compose_domain_adapters()
    you_msg = {
        "label": "You: https://www.zarooratwala.com/?x=1",
        "text": "You: https://www.zarooratwala.com/?x=1",
        "kind": "search_result_row",
        "domain": "whatsapp",
        "container": "Pallavi",
    }
    a = assess_candidate_for_role(
        spec=_specs()["source_object"],
        candidate=you_msg,
        goal=_Goal(),
        task_relevance=0.99,
        bindings={"source_container": {"resolved_label": "Pallavi"}},
    )
    assert a.task_relevance == 0.99
    assert a.binding_eligible is False
    assert "same_originator" in a.missing_required

    peer = {
        "label": "Pallavi: https://www.zarooratwala.com/?x=1",
        "text": "Pallavi: https://www.zarooratwala.com/?x=1",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Pallavi",
        "sender": "Pallavi",
    }
    b = assess_candidate_for_role(
        spec=_specs()["source_object"],
        candidate=peer,
        goal=_Goal(),
        task_relevance=0.9,
        bindings={"source_container": {"resolved_label": "Pallavi"}},
    )
    assert b.binding_eligible is True


def test_i_sent_originator_reverses_eligibility():
    class G:
        contact = "Pallavi"
        link_query = "zarooratwala"
        target_contact = "Tanmay"
        originator = "self"

    you_msg = {
        "label": "You: https://www.zarooratwala.com/x",
        "text": "You: https://www.zarooratwala.com/x",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Pallavi",
    }
    peer = {
        "label": "https://www.zarooratwala.com/x",
        "text": "https://www.zarooratwala.com/x",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Pallavi",
        "sender": "Pallavi",
    }
    bindings = {"source_container": {"resolved_label": "Pallavi"}}
    assert assess_candidate_for_role(
        spec=forward_role_specs(G())["source_object"],
        candidate=you_msg,
        goal=G(),
        bindings=bindings,
        task_relevance=0.9,
    ).binding_eligible
    assert not assess_candidate_for_role(
        spec=forward_role_specs(G())["source_object"],
        candidate=peer,
        goal=G(),
        bindings=bindings,
        task_relevance=0.9,
    ).binding_eligible


def test_youtube_message_never_binds_source_object():
    a = assess_candidate_for_role(
        spec=_specs()["source_object"],
        candidate={
            "label": "https://youtu.be/rHJdc-jkxys",
            "text": "https://youtu.be/rHJdc-jkxys",
            "kind": "message_with_link",
            "domain": "whatsapp",
            "container": "Pallavi",
            "source_query": "zarooratwala",
        },
        goal=_Goal(),
        task_relevance=0.92,
        bindings={"source_container": {"resolved_label": "Pallavi"}},
    )
    assert a.binding_eligible is False


def test_cross_domain_email_thread_vs_latest_message():
    specs = _specs()
    thread = EntityObservation(
        entity_kind="thread",
        label="Q3 Roadmap",
        identity_evidence=[
            IdentityEvidence(kind="title", value="Q3 Roadmap"),
            IdentityEvidence(kind="email_thread_id", value="thread_9"),
        ],
        content_evidence=[
            IdentityEvidence(
                kind="latest_message",
                value="see zarooratwala pricing",
                identity_bearing=False,
            )
        ],
    )
    # Thread identity is title — not latest message text.
    class G:
        contact = "Q3 Roadmap"
        link_query = "zarooratwala"
        target_contact = "Tanmay"

    assert assess_observation_for_role(
        spec=forward_role_specs(G())["source_container"],
        observation=thread,
        goal=G(),
    ).binding_eligible
    # Content role needs message-shaped entity + originator evidence.
    msg = EntityObservation(
        entity_kind="message",
        label="pricing",
        identity_evidence=[
            IdentityEvidence(kind="sender", value="Q3 Roadmap", identity_bearing=True)
        ],
        content_evidence=[
            IdentityEvidence(kind="body", value="see zarooratwala pricing")
        ],
        relations={"container": "Q3 Roadmap"},
    )
    assert assess_observation_for_role(
        spec=forward_role_specs(G())["source_object"],
        observation=msg,
        goal=G(),
        bindings={"source_container": {"resolved_label": "Q3 Roadmap"}},
    ).binding_eligible


def test_cross_domain_folder_vs_child_filename():
    class G:
        contact = "Specs"
        link_query = "charger"
        target_contact = "X"

    folder = EntityObservation(
        entity_kind="container",
        label="Specs",
        identity_evidence=[
            IdentityEvidence(kind="directory_name", value="Specs")
        ],
        content_evidence=[
            IdentityEvidence(
                kind="filename", value="charger-v3.pdf", identity_bearing=False
            )
        ],
    )
    assert assess_observation_for_role(
        spec=forward_role_specs(G())["source_container"],
        observation=folder,
        goal=G(),
        task_relevance=0.2,
    ).binding_eligible
    # Child filename must not make a random folder bind as source_object content
    # without being a content entity.
    assert not assess_observation_for_role(
        spec=forward_role_specs(G())["source_object"],
        observation=folder,
        goal=G(),
        bindings={"source_container": {"resolved_label": "Specs"}},
        task_relevance=0.99,
    ).binding_eligible


def test_cross_domain_browser_tab_vs_page_content():
    class G:
        contact = "Docs Home"
        link_query = "zarooratwala"
        target_contact = "X"

    tab = EntityObservation(
        entity_kind="container",
        label="Docs Home",
        identity_evidence=[IdentityEvidence(kind="tab_title", value="Docs Home")],
        content_evidence=[
            IdentityEvidence(
                kind="page_text",
                value="Advertisement: ZarooratWala groceries",
                identity_bearing=False,
            )
        ],
    )
    assert assess_observation_for_role(
        spec=forward_role_specs(G())["source_container"],
        observation=tab,
        goal=G(),
    ).binding_eligible
    # Page ad text is content, not tab identity — a different tab title fails.
    other = EntityObservation(
        entity_kind="container",
        label="Shopping",
        identity_evidence=[IdentityEvidence(kind="tab_title", value="Shopping")],
        content_evidence=[
            IdentityEvidence(
                kind="page_text",
                value="Pallavi ZarooratWala",
                identity_bearing=False,
            )
        ],
    )
    assert not assess_observation_for_role(
        spec=forward_role_specs(G())["source_container"],
        observation=other,
        goal=G(),
        task_relevance=0.99,
    ).binding_eligible


def test_act_consumes_valid_binding_without_re_resolving():
    binder = RoleBinder()
    binding = BindingRecord(
        role="source_container",
        entity_id="42",
        label="Pallavi",
        status="confirmed",
        confidence=0.96,
    )
    ok, why, prop = binder.action_allowed(
        role="source_container",
        target="Pallavi",
        binding=binding,
        allow_propose=False,
    )
    assert ok and why == "binding_valid" and prop is None
    ok2, why2, _ = binder.action_allowed(
        role="source_container",
        target="ZarooratWala – Fresh Groceries",
        binding=binding,
        allow_propose=False,
    )
    assert not ok2 and why2 == "target_does_not_match_valid_binding"


def test_referent_mismatch_records_negative_evidence_and_search_flag():
    class ES:
        binding_negative_evidence = None
        last_effect_closure = {}

    es = ES()
    apply_referent_mismatch(
        es,
        role="source_container",
        candidate_label="ZarooratWala – Fresh Groceries",
        forward_task=None,
    )
    assert is_negatively_evidenced(
        es, role="source_container", candidate_label="ZarooratWala – Fresh Groceries"
    )
    modes = es.last_effect_closure.get("modes") or []
    assert "referent_mismatch" in modes or REFERENT_MISMATCH in modes
    assert es.last_effect_closure.get("referent_search_needed") is True
    assert es.last_effect_closure.get("referent_repair_owed") is False


def test_sanitize_rejects_brand_row_for_open_entity():
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        TaskState,
        sanitize_decision,
    )

    brief = DecisionBrief(
        goal={
            "operation": "forward_message",
            "source_conversation": "Pallavi",
            "contact": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        world={"surface": "search_results"},
        capabilities=["open_entity", "resolve_entity", "observe"],
        meta_action="act",
        candidates=["ZarooratWala – Fresh Groceries Delivery", "Pallavi"],
        task_state=TaskState(
            phase="reach_source",
            source_chat_open=False,
            search_query="Pallavi zarooratwala",
        ),
    )
    bad = sanitize_decision(
        {
            "capability": "open_entity",
            "target": "ZarooratWala – Fresh Groceries Delivery",
            "why": "matches zarooratwala",
            "confidence": 0.95,
        },
        brief,
    )
    assert bad.ok is False
    good = sanitize_decision(
        {
            "capability": "open_entity",
            "target": "Pallavi",
            "why": "source contact",
            "confidence": 0.9,
        },
        brief,
    )
    assert good.ok is True


def test_meta_forces_search_on_role_identity_mismatch():
    from plugin.agent.executive.meta_action import MetaAction, MetaContext
    from plugin.agent.executive.meta_consultation import sanitize_meta_choice

    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "retry open", "confidence": 0.9},
        MetaContext(
            role_identity_search_owed=True,
            referent_search_needed=True,
            retrieve_ready=False,
            has_grounded_action=True,
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.SEARCH
