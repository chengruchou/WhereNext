"""Llama-2 based POI natural-language description generation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from .poi_description_generator import POIDescriptionGenerator
except ImportError:  # Allows direct smoke-test execution of this file.
    BACKEND_DIR = Path(__file__).resolve().parents[1]
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from semantic.poi_description_generator import POIDescriptionGenerator


REQUIRED_DESCRIPTION_KEYS = ("visit_pattern", "location", "category_context")
LLAMA_MODEL_PATH = os.getenv("LLAMA_MODEL_PATH", "C:/models/llama2-7b")
METADATA_FIELDS = [
    "raw_poi_id",
    "item_id",
    "category_name",
    "raw_categories",
    "latitude",
    "longitude",
    "checkins_count",
    "users_count",
    "checkins_count_from_events",
    "users_count_from_events",
    "photos_count",
    "highlights_count",
    "items_count",
    "radius_meters",
]


class Llama2POIDescriptionGenerator:
    """Generate POI descriptions with a local Hugging Face Llama-2 model."""

    _MODEL_CACHE: dict[tuple[str, str | None, bool], tuple[Any, Any, Any, Any]] = {}
    _PRINTED_LOAD_MESSAGES: set[tuple[str, str | None, bool]] = set()

    def __init__(
        self,
        model_name: str = "meta-llama/Llama-2-7b-chat-hf",
        device: str | None = None,
        torch_dtype: str = "float16",
        max_new_tokens: int = 320,
        temperature: float = 0.2,
        top_p: float = 0.9,
        use_4bit: bool = False,
        prompt_version: str = "v1",
        debug_output: bool = False,
        json_prefill: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.torch_dtype = torch_dtype
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.use_4bit = use_4bit
        self.prompt_version = prompt_version
        self.debug_output = debug_output
        self.json_prefill = json_prefill
        self.template_fallback = POIDescriptionGenerator()
        self._current_fallback_metadata: dict[str, Any] = {}
        self._last_parse_used_fallback = False
        self.model_path = Path(os.getenv("LLAMA_MODEL_PATH", LLAMA_MODEL_PATH)).expanduser()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Llama-2 description generation requires torch and transformers."
            ) from exc

        self.torch = torch
        cache_key = (str(self.model_path.resolve()) if self.model_path.exists() else str(self.model_path), device, use_4bit)
        cached = self._MODEL_CACHE.get(cache_key)
        if cached is not None:
            self.tokenizer, self.model, self.runtime_device, self.torch = cached
            return

        if not self.model_path.exists():
            raise RuntimeError(
                f"Llama model not found at LLAMA_MODEL_PATH: {self.model_path}. "
                "Set LLAMA_MODEL_PATH to a local Llama-2 model directory."
            )

        if cache_key not in self._PRINTED_LOAD_MESSAGES:
            print(f"[Llama2] Loading model from local path: {self.model_path}")
            self._PRINTED_LOAD_MESSAGES.add(cache_key)

        self.tokenizer = AutoTokenizer.from_pretrained(
            str(self.model_path),
            use_fast=True,
            local_files_only=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        cuda_available = torch.cuda.is_available()
        model_kwargs: dict[str, Any] = {
            "local_files_only": True,
            "torch_dtype": "auto",
        }
        if device is None and cuda_available:
            self.runtime_device = torch.device("cuda")
        elif device is None:
            print(
                "[Llama2] Warning: CUDA is not available. "
                "Loading the local Llama-2 POI description generator on CPU may be very slow."
            )
            self.runtime_device = torch.device("cpu")
        else:
            self.runtime_device = torch.device(device)

        if cuda_available and not use_4bit:
            print(
                "[Llama2] Warning: loading Llama-2 without 4-bit quantization can require "
                "substantial GPU memory and may cause CUDA OOM. Consider use_4bit=True."
            )

        if use_4bit:
            try:
                from transformers import BitsAndBytesConfig
                import accelerate  # noqa: F401
                import bitsandbytes  # noqa: F401
            except ImportError as exc:
                raise RuntimeError(
                    "Llama-2 4-bit loading requires bitsandbytes and accelerate."
                ) from exc

            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )

        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                str(self.model_path),
                **model_kwargs,
            )
            if self.runtime_device is not None:
                self.model.to(self.runtime_device)
            self.model.eval()
        except torch.cuda.OutOfMemoryError as exc:
            raise RuntimeError(
                "CUDA out of memory while loading Llama-2. Retry with use_4bit=True "
                "or set LLAMA_MODEL_PATH to a smaller local model."
            ) from exc
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise RuntimeError(
                    "Out of memory while loading Llama-2. Retry with use_4bit=True "
                    "or use a smaller local model path."
                ) from exc
            raise

        self._MODEL_CACHE[cache_key] = (
            self.tokenizer,
            self.model,
            self.runtime_device,
            self.torch,
        )

    def build_generation_prompt(self, poi_metadata: dict[str, Any]) -> str:
        return self.build_chat_prompt(poi_metadata)

    def build_chat_prompt(self, poi_metadata: dict[str, Any]) -> str:
        """Build a Llama-2-chat formatted prompt for recommendation-oriented POI semantics."""

        def value(field: str) -> Any:
            raw_value = poi_metadata.get(field)
            return raw_value if raw_value not in (None, "") else "unknown"

        system_message = (
            "You are an expert in location-based recommendation systems. "
            "Your job is to generate compact semantic features that help predict a user's next POI. "
            "You must output only valid JSON."
        )

        user_message = (
            "You will be given structured metadata about one POI.\n"
            "Your goal is NOT to write a generic description.\n"
            "Your goal is to encode decision-useful semantic signals for next-POI recommendation.\n\n"

            "Use the POI category and activity statistics to infer:\n"
            "- user intent\n"
            "- visit pattern\n"
            "- functional role in a trajectory\n"
            "- recommendation relevance\n\n"

            "---\n\n"

            "POI Metadata:\n"
            f"- raw_poi_id: {value('raw_poi_id')}\n"
            f"- category_name: {value('category_name')}\n"
            f"- raw_categories: {value('raw_categories')}\n"
            f"- latitude: {value('latitude')}\n"
            f"- longitude: {value('longitude')}\n"
            f"- checkins_count: {value('checkins_count')}\n"
            f"- users_count: {value('users_count')}\n"
            f"- photos_count: {value('photos_count')}\n\n"

            "---\n\n"

            "Generate exactly three fields:\n\n"

            "1. visit_pattern:\n"
            "- Encode the likely user intent and visit behavior.\n"
            "- Mention whether this POI is likely routine, occasional, social, quick-stop, long-stay, destination-oriented, or supporting-stop.\n"
            "- Use category and popularity signals, not exact unsupported facts.\n"
            "- Example style: \"routine coffee stop for short visits and work breaks\".\n\n"

            "2. location:\n"
            "- Encode only coarse spatial usefulness for recommendation.\n"
            "- Use latitude/longitude only as coarse geographic signal.\n"
            "- Mention coarse region or dense-POI tendency only if supported by activity level.\n"
            "- Do NOT invent city names, streets, neighborhoods, transit, parking, nearby buildings, or exact surrounding POIs.\n\n"

            "3. category_context:\n"
            "- Encode what recommendation role this POI plays.\n"
            "- Mention intent class such as food, coffee, shopping, nightlife, leisure, study, work, travel, daily-routine, or service.\n"
            "- Explain how it may follow from previous visits in a trajectory.\n\n"

            "---\n\n"

            "Important rules:\n"
            "- Do NOT use template phrases such as \"Visit pattern:\" or \"Category context:\".\n"
            "- Do NOT simply restate metadata.\n"
            "- Do NOT over-describe the place.\n"
            "- Prefer short recommendation-oriented phrases over natural travel-guide descriptions.\n"
            "- Each field must be 1 concise sentence.\n"
            "- Output valid JSON only.\n\n"

            "Return ONLY this JSON object:\n\n"
            "{\n"
            '  "visit_pattern": "...",\n'
            '  "location": "...",\n'
            '  "category_context": "..."\n'
            "}\n\n"

            "No markdown. No explanation. No text before or after JSON."
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        if hasattr(self.tokenizer, "apply_chat_template"):
            try:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            except Exception:
                pass

        return (
            "<s>[INST] <<SYS>>\n"
            f"{system_message}\n"
            "<</SYS>>\n\n"
            f"{user_message}\n"
            "[/INST]"
        )

    def generate_descriptions(self, poi_metadata: dict[str, Any]) -> dict[str, str]:
        """Generate descriptions, falling back to template text on failure."""

        self._current_fallback_metadata = poi_metadata
        try:
            prompt = self.build_generation_prompt(poi_metadata)
            if self.json_prefill:
                prompt = f"{prompt}\n{{"
            inputs = self.tokenizer(prompt, return_tensors="pt")
            if self.runtime_device is not None:
                inputs = {key: value.to(self.runtime_device) for key, value in inputs.items()}

            do_sample = False
            generation_kwargs = {
                "max_new_tokens": self.max_new_tokens,
                "do_sample": do_sample,
                "pad_token_id": self.tokenizer.pad_token_id,
                "eos_token_id": self.tokenizer.eos_token_id,
            }
            if do_sample:
                generation_kwargs["temperature"] = self.temperature
                generation_kwargs["top_p"] = self.top_p
            with self.torch.no_grad():
                output_ids = self.model.generate(
                    **inputs,
                    **generation_kwargs,
                )

            generated_ids = output_ids[0][inputs["input_ids"].shape[-1] :]
            decoded_generated_text = self.tokenizer.decode(
                generated_ids,
                skip_special_tokens=True,
            )
            output_text = (
                "{" + decoded_generated_text.lstrip()
                if self.json_prefill
                else decoded_generated_text
            )
            if self.debug_output:
                self._print_debug_generation(
                    prompt=prompt,
                    decoded_generated_text=decoded_generated_text,
                    output_text=output_text,
                    json_prefill=self.json_prefill,
                )

            self._last_parse_used_fallback = False
            descriptions = self.parse_generation_output(output_text)
            if self.debug_output:
                status = "fallback" if self._last_parse_used_fallback else "success"
                print(f"[Llama2] parsing={status}")
            return descriptions
        except Exception as exc:
            if self.debug_output and "prompt" in locals():
                self._print_debug_generation(
                    prompt=prompt,
                    decoded_generated_text="",
                    output_text="",
                    json_prefill=self.json_prefill,
                )
                print(f"[Llama2] generation failed before parsing: {exc}")
            return self._fallback_to_template(poi_metadata, exc)

    def parse_generation_output(self, output_text: str) -> dict[str, str]:
        """Extract and validate description JSON from model output."""

        try:
            payload = self._load_json_object(output_text)
        except Exception as exc:
            return self._fallback_to_template(self._current_fallback_metadata, exc)

        descriptions: dict[str, str] = {}
        for key in REQUIRED_DESCRIPTION_KEYS:
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                return self._fallback_to_template(
                    self._current_fallback_metadata,
                    ValueError(f"Missing or invalid generated description key: {key}"),
                )
            descriptions[key] = value.strip()
        return descriptions

    def _fallback_to_template(
        self,
        poi_metadata: dict[str, Any] | None,
        error: Exception | str,
    ) -> dict[str, str]:
        metadata = poi_metadata or {}
        poi_id = (
            metadata.get("raw_poi_id")
            or metadata.get("raw_location_id")
            or metadata.get("item_id")
            or "unknown"
        )
        print(f"[Llama2] fallback to template for POI {poi_id}: {error}")
        self._last_parse_used_fallback = True
        return self.template_fallback.generate_descriptions(metadata)

    @staticmethod
    def _print_debug_generation(
        prompt: str,
        decoded_generated_text: str,
        output_text: str,
        json_prefill: bool,
    ) -> None:
        print("=== LLAMA PROMPT START ===")
        print(prompt)
        print("=== LLAMA PROMPT END ===")
        print("=== LLAMA RAW OUTPUT START ===")
        print(decoded_generated_text)
        print("=== LLAMA RAW OUTPUT END ===")
        if json_prefill:
            print("=== LLAMA RECONSTRUCTED JSON START ===")
            print(output_text)
            print("=== LLAMA RECONSTRUCTED JSON END ===")

    @staticmethod
    def _load_json_object(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end < start:
                raise ValueError("No JSON object found in generated output.")
            payload = json.loads(cleaned[start : end + 1])

        if not isinstance(payload, dict):
            raise ValueError("Generated output JSON must be an object.")
        return payload


def run_parser_smoke_test() -> dict[str, Any]:
    """Parser smoke test that does not load Llama-2."""

    parser = object.__new__(Llama2POIDescriptionGenerator)
    parser.template_fallback = POIDescriptionGenerator()
    parser._current_fallback_metadata = {"raw_poi_id": 1, "category_name": "Coffee Shop"}

    cases = {
        "valid_json": (
            '{"visit_pattern":"A.","location":"B.","category_context":"C."}'
        ),
        "fenced_json": (
            '```json\n{"visit_pattern":"A.","location":"B.","category_context":"C."}\n```'
        ),
        "extra_text": (
            'Here is JSON: {"visit_pattern":"A.","location":"B.","category_context":"C."} done.'
        ),
    }
    parsed = {
        name: parser.parse_generation_output(text)
        for name, text in cases.items()
    }

    parsed["malformed_fallback_example"] = parser.parse_generation_output("not json")

    return parsed


if __name__ == "__main__":
    print(json.dumps(run_parser_smoke_test(), indent=2, ensure_ascii=False))
