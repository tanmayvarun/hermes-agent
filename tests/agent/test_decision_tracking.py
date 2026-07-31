from agent.decision_tracking import DecisionComponent, decision_tracker


class _FakeComponent(DecisionComponent):
    component_name = "tests.fake_component"


def test_decision_tracker_records_and_adjudicates_accuracy():
    decision_tracker.reset()
    comp = _FakeComponent()
    first = comp.record_decision("research", context={"message": "find latest link"})
    second = comp.record_decision("filesystem", context={"message": "find pdf"})

    comp.adjudicate_decision(first, outcome="research")
    comp.adjudicate_decision(second, outcome="research")

    stats = comp.stats()
    assert stats["attempts"] == 2
    assert stats["adjudicated"] == 2
    assert stats["successes"] == 1
    assert stats["failures"] == 1
    assert stats["pending"] == 0
    assert stats["accuracy"] == 0.5


def test_decision_tracker_leaves_pending_until_adjudicated():
    decision_tracker.reset()
    comp = _FakeComponent()
    decision_id = comp.record_decision("coding")
    stats = comp.stats()
    assert stats["attempts"] == 1
    assert stats["pending"] == 1
    assert stats["adjudicated"] == 0
    assert stats["accuracy"] is None

    record = decision_tracker.get_record(decision_id)
    assert record is not None
    assert record.predicted == "coding"
    assert record.success is None
