"""Factory for POI description generation backends."""

from __future__ import annotations

from .poi_description_generator import POIDescriptionGenerator


def build_description_generator(
    backend: str = "template",
    model_name: str | None = None,
    prompt_version: str = "v1",
    use_4bit: bool = False,
    max_new_tokens: int = 220,
    temperature: float = 0.2,
    debug_output: bool = False,
):
    """Build a POI description generator without loading unused backends."""

    backend_key = (backend or "template").strip().lower()
    if backend_key == "template":
        return POIDescriptionGenerator()

    if backend_key == "llama2":
        from .llama2_description_generator import Llama2POIDescriptionGenerator

        return Llama2POIDescriptionGenerator(
            model_name=model_name or "meta-llama/Llama-2-7b-chat-hf",
            prompt_version=prompt_version,
            use_4bit=use_4bit,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            debug_output=debug_output,
        )

    raise ValueError(f"Unsupported description backend: {backend}")
