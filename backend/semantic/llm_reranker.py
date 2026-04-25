"""Listwise LLM reranking for POI recommendations.

This module is provider-isolated and only performs API calls when call_llm() is
used. The parsing and smoke-test paths do not require network access.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from .score_fusion import fuse_scores, min_max_normalize, rank_to_score
except ImportError:  # Allows direct smoke-test execution of this file.
    from score_fusion import fuse_scores, min_max_normalize, rank_to_score


class LLMReranker:
    """Build prompts, call an LLM, and parse listwise POI rankings."""

    def __init__(
        self,
        model_name: str = "gpt-4.1-mini",
        api_key: str | None = None,
        prompt_version: str = "v1",
        max_candidates: int = 10,
        temperature: float = 0.0,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.prompt_version = prompt_version
        self.max_candidates = max_candidates
        self.temperature = temperature
        self.last_parse_failed = False

    def build_listwise_prompt(
        self,
        history_descriptions: list[dict],
        candidate_predictions: list[dict],
    ) -> str:
        """Build a strict-JSON listwise reranking prompt."""

        history_lines = []
        for index, history in enumerate(history_descriptions, start=1):
            descriptions = history.get("descriptions") or {}
            history_lines.append(
                "\n".join(
                    [
                        f"{index}. raw_location_id={history.get('raw_location_id')}",
                        f"   timestamp: {history.get('timestamp') or 'unknown'}",
                        f"   visit_pattern: {descriptions.get('visit_pattern', '')}",
                        f"   location: {descriptions.get('location', '')}",
                        f"   category_context: {descriptions.get('category_context', '')}",
                    ]
                )
            )

        candidate_lines = []
        for candidate in candidate_predictions[: self.max_candidates]:
            descriptions = candidate.get("descriptions") or {}
            candidate_lines.append(
                "\n".join(
                    [
                        f"- raw_location_id: {candidate.get('raw_location_id')}",
                        f"  original_sbr_rank: {candidate.get('rank')}",
                        f"  original_sbr_score: {candidate.get('score')}",
                        f"  visit_pattern: {descriptions.get('visit_pattern', '')}",
                        f"  location: {descriptions.get('location', '')}",
                        f"  category_context: {descriptions.get('category_context', '')}",
                    ]
                )
            )

        return (
            "You are a professional itinerary planner and a next-POI recommendation expert.\n"
            "Your task is to predict the user's most plausible next visit from the candidate POIs.\n\n"

            "You must reason like a trajectory-aware travel planner, not a generic text similarity model.\n"
            "Use the ordered visit history to infer the user's movement evolution, intent transition, and likely next need.\n\n"

            "Available information:\n"
            "- The user history is ordered from oldest to newest.\n"
            "- Each POI has semantic descriptions generated from metadata.\n"
            "- Original SBR rank and score are model priors, not final answers.\n"
            "- Exact timestamps, dwell time, transportation mode, and real addresses may be unavailable.\n"
            "- If time information is unavailable, do NOT invent morning/night/weekend behavior.\n\n"

            "Planning and recommendation criteria:\n"
            "1. Trajectory evolution:\n"
            "   - Identify how the user's intent changes across the history.\n"
            "   - Examples: coffee → food, work/service → food, shopping → food, leisure → nightlife, travel → transit.\n"
            "2. Visit intent:\n"
            "   - Infer whether the user is likely continuing the same intent or switching to a complementary intent.\n"
            "   - Prefer candidates that naturally follow the latest history, not merely candidates with similar category names.\n"
            "3. Functional role:\n"
            "   - Decide whether each candidate is a main destination, quick stop, supporting stop, routine stop, social/leisure stop, or transit-like stop.\n"
            "4. Spatial continuity:\n"
            "   - Prefer candidates with compatible coarse spatial context when available.\n"
            "   - Do NOT invent exact distance, city names, neighborhoods, public transit, parking, or nearby buildings.\n"
            "5. SBR prior:\n"
            "   - Use original_sbr_rank and original_sbr_score as useful priors.\n"
            "   - You may override SBR only when trajectory reasoning strongly supports another candidate.\n\n"

            "Avoid these mistakes:\n"
            "- Do not blindly follow original SBR rank.\n"
            "- Do not rank only by semantic similarity.\n"
            "- Do not rank only by popularity.\n"
            "- Do not over-prefer generic categories unless they fit the trajectory.\n"
            "- Do not invent unavailable temporal or geographic details.\n\n"

            f"Prompt version: {self.prompt_version}\n\n"

            "=== Ordered User History (oldest → newest) ===\n"
            f"{chr(10).join(history_lines) if history_lines else 'No history available.'}\n\n"

            "=== Candidate POIs ===\n"
            f"{chr(10).join(candidate_lines)}\n\n"

            "=== Required reasoning process ===\n"
            "First infer the user's current trajectory intent from the ordered history.\n"
            "Then rank every candidate by how well it satisfies the most plausible next intent.\n"
            "Balance trajectory fit with the SBR prior.\n\n"

            "=== Output format: STRICT JSON ONLY ===\n"
            "{\n"
            '  "trajectory_intent": "brief summary of inferred user intent transition",\n'
            '  "ranking": [\n'
            '    {\n'
            '      "raw_location_id": 123,\n'
            '      "reason": "brief reason based on trajectory fit, functional role, and SBR prior"\n'
            '    },\n'
            '    {\n'
            '      "raw_location_id": 456,\n'
            '      "reason": "brief reason based on trajectory fit, functional role, and SBR prior"\n'
            '    }\n'
            "  ]\n"
            "}\n\n"

            "Output rules:\n"
            "- Include every candidate raw_location_id exactly once in ranking.\n"
            "- Use only raw_location_id values from Candidate POIs.\n"
            "- No markdown.\n"
            "- No explanation outside JSON.\n"
            "- Keep each reason short.\n"
        )

    def call_llm(self, prompt: str) -> str:
        """Call the configured OpenAI model and return text."""

        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Provide api_key or set the environment variable."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The official OpenAI Python client is not installed. Install the openai package."
            ) from exc

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You return strict JSON for POI recommendation reranking.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
        )
        content = response.choices[0].message.content
        return content or ""

    def parse_ranking_response(
        self,
        response_text: str,
        valid_raw_ids: list[int],
    ) -> list[int]:
        """Parse LLM JSON ranking and repair invalid, duplicate, or missing IDs."""

        original_order = [int(raw_id) for raw_id in valid_raw_ids]
        valid_set = set(original_order)
        self.last_parse_failed = False

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError:
            try:
                payload = json.loads(self._extract_json_object(response_text))
            except Exception:
                self.last_parse_failed = True
                return original_order

        ranking_rows = payload.get("ranking") if isinstance(payload, dict) else None
        if not isinstance(ranking_rows, list):
            self.last_parse_failed = True
            return original_order

        ranked: list[int] = []
        seen: set[int] = set()
        for row in ranking_rows:
            raw_id = self._coerce_raw_id(row)
            if raw_id is None or raw_id not in valid_set or raw_id in seen:
                continue
            ranked.append(raw_id)
            seen.add(raw_id)

        ranked.extend(raw_id for raw_id in original_order if raw_id not in seen)
        return ranked

    def rerank(
        self,
        history_descriptions: list[dict],
        candidate_predictions: list[dict],
    ) -> list[int]:
        """Run listwise LLM reranking and return raw_location_id order."""

        limited_candidates = candidate_predictions[: self.max_candidates]
        valid_raw_ids = [
            int(candidate["raw_location_id"])
            for candidate in limited_candidates
            if "raw_location_id" in candidate
        ]
        prompt = self.build_listwise_prompt(history_descriptions, limited_candidates)
        response_text = self.call_llm(prompt)
        return self.parse_ranking_response(response_text, valid_raw_ids)

    @staticmethod
    def _extract_json_object(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("No JSON object found in response.")
        return text[start : end + 1]

    @staticmethod
    def _coerce_raw_id(row: Any) -> int | None:
        value = row.get("raw_location_id") if isinstance(row, dict) else row
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def run_llm_reranker_smoke_test() -> dict[str, Any]:
    """No-API smoke test for parsing repair and score fusion."""

    reranker = LLMReranker()
    response = """
    extra text
    {
      "ranking": [
        {"raw_location_id": 300, "reason": "best semantic match"},
        {"raw_location_id": 999, "reason": "invalid id"},
        {"raw_location_id": 300, "reason": "duplicate"},
        {"raw_location_id": 100, "reason": "next best"}
      ]
    }
    """
    parsed = reranker.parse_ranking_response(response, [100, 200, 300, 400])
    normalized = min_max_normalize([0.2, 0.5, 0.9, 0.1])
    fused = [
        fuse_scores(normalized_sbr=score, llm_rank_score=rank_to_score(index, 4), alpha=0.7)
        for index, score in enumerate(normalized, start=1)
    ]
    return {
        "parsed_ranking": parsed,
        "normalized_sbr_scores": normalized,
        "fused_scores": fused,
    }


if __name__ == "__main__":
    print(json.dumps(run_llm_reranker_smoke_test(), indent=2))
