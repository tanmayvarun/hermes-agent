"""A 402 on one model must not disable the whole provider.

Providers bill per model. Quarantining the backend because a single
unpurchased model returned "extra usage only ... balance is empty" took every
other model on that backend down with it, which is what stalled the live
forward runs at startup.
"""

import agent.auxiliary_client as aux


def _clear() -> None:
    aux._aux_unhealthy_until.clear()
    aux._aux_unhealthy_logged_at.clear()


def test_payment_error_on_one_model_leaves_siblings_usable():
    _clear()
    try:
        aux._mark_provider_unhealthy("ollama-cloud", model="kimi-k3")

        assert aux._is_provider_unhealthy("ollama-cloud", "kimi-k3") is True
        # The models the plan does cover must stay reachable.
        assert aux._is_provider_unhealthy("ollama-cloud", "qwen3.5:397b") is False
        assert aux._is_provider_unhealthy("ollama-cloud", "gemma4:31b") is False
        assert aux._is_provider_unhealthy("ollama-cloud") is False
    finally:
        _clear()


def test_provider_scoped_quarantine_still_hides_every_model():
    """Without a model we cannot attribute the failure, so quarantine broadly."""
    _clear()
    try:
        aux._mark_provider_unhealthy("ollama-cloud")

        assert aux._is_provider_unhealthy("ollama-cloud") is True
        assert aux._is_provider_unhealthy("ollama-cloud", "qwen3.5:397b") is True
    finally:
        _clear()


def test_model_quarantine_expires():
    _clear()
    try:
        aux._mark_provider_unhealthy("ollama-cloud", ttl=-1, model="kimi-k3")
        assert aux._is_provider_unhealthy("ollama-cloud", "kimi-k3") is False
    finally:
        _clear()
