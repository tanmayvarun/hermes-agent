from plugin.agent.controller import target_app_obscured
from plugin.agent.features import StateFeatures


def test_target_app_obscured_from_screen_type():
    features = StateFeatures(
        extras={
            "perception_llm": {
                "screen_type": "desktop_obscured_target",
                "active_surface": "terminal (foreground), whatsapp (background)",
                "likely_next_family": "window_management",
            }
        }
    )
    assert target_app_obscured(features) is True


def test_target_app_not_obscured_on_chat_list():
    features = StateFeatures(
        extras={
            "perception_summary": {
                "screen_type": "chat_list",
                "active_surface": "main_window",
                "likely_next_family": "search",
            }
        }
    )
    assert target_app_obscured(features) is False
