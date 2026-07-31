"""Import guard helpers — worldmodel must stay LLM-free."""

from __future__ import annotations

FORBIDDEN = (
    "openai",
    "anthropic",
    "litellm",
    "google.generativeai",
    "transformers",
    "langchain",
)


def assert_no_llm_imports(module_file_text: str) -> None:
    lower = module_file_text.lower()
    for name in FORBIDDEN:
        # crude but effective for CI
        needle = f"import {name}" if "." not in name else f"import {name.split('.')[0]}"
        if f"import {name}" in lower or f"from {name}" in lower:
            raise AssertionError(f"LLM-related import forbidden in worldmodel: {name}")
