"""API-driven algorithm generation for the AutoSolver agent.

This layer is intentionally provider-agnostic and dependency-free. It can call
an OpenAI-compatible chat-completions API, parse JSON heuristic specs, and turn
them into safe generated solvers. No Codex runtime generation is required.
"""

from __future__ import annotations

import json
import os
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from autosolver.features import extract_instance_features
from autosolver.generated_solver import HeuristicSpec
from autosolver.model import Instance


class AlgorithmGenerator(Protocol):
    def generate(self, instance: Instance, count: int = 4) -> list[HeuristicSpec]:
        ...


@dataclass(frozen=True)
class TemplateAlgorithmGenerator:
    """Deterministic fallback generator used when no external API is configured."""

    def generate(self, instance: Instance, count: int = 4) -> list[HeuristicSpec]:
        features = extract_instance_features(instance)
        specs = [
            HeuristicSpec(
                name="api_like_probability",
                description="Probability-first generated baseline.",
                order_priority="best_probability",
                edge_accept_weight=1.0,
                edge_cost_weight=0.02,
                edge_value_weight=0.20,
                multi_offer=features.max_riders_per_order > 1,
                max_offers_per_order=min(3, features.max_riders_per_order),
            ),
            HeuristicSpec(
                name="api_like_regret",
                description="Prioritize fragile orders, then high probability per cost.",
                order_priority="highest_regret",
                edge_accept_weight=0.8,
                edge_cost_weight=0.01,
                edge_value_weight=0.75,
                order_candidate_penalty=0.01,
                multi_offer=False,
            ),
            HeuristicSpec(
                name="api_like_sparse_value",
                description="Cost-aware generated heuristic for sparse or capacity-constrained graphs.",
                order_priority="fewest_candidates",
                edge_accept_weight=0.45,
                edge_cost_weight=0.04,
                edge_value_weight=1.50,
                rider_load_penalty=0.10,
                multi_offer=features.max_riders_per_order > 1 and features.capacity_ratio > 1.0,
                max_offers_per_order=min(2, features.max_riders_per_order),
            ),
            HeuristicSpec(
                name="api_like_priority",
                description="Priority-first generated heuristic.",
                order_priority="priority",
                edge_accept_weight=1.15,
                edge_cost_weight=0.015,
                edge_value_weight=0.30,
                rider_load_penalty=0.20,
                multi_offer=features.max_riders_per_order > 1,
                max_offers_per_order=min(2, features.max_riders_per_order),
            ),
        ]
        return specs[: max(0, count)]


@dataclass(frozen=True)
class OpenAICompatibleAlgorithmGenerator:
    endpoint: str
    model: str
    api_key_env: str = "AUTOSOLVER_LLM_API_KEY"
    timeout_sec: float = 20.0

    def generate(self, instance: Instance, count: int = 4) -> list[HeuristicSpec]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key env var {self.api_key_env!r}")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate bounded JSON heuristic specifications for a delivery assignment solver.",
                },
                {
                    "role": "user",
                    "content": build_generation_prompt(instance, count),
                },
            ],
            "temperature": 0.6,
        }
        request = urllib.request.Request(
            _chat_completions_url(self.endpoint),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"algorithm generation API request failed: {exc}") from exc

        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        return parse_specs(content, count=count)


def build_generation_prompt(instance: Instance, count: int = 4) -> str:
    features = extract_instance_features(instance).to_dict()
    return textwrap.dedent(
        f"""
        Generate {count} diverse heuristic specs for this delivery assignment instance.

        Problem features JSON:
        {json.dumps(features, ensure_ascii=False, indent=2)}

        Return JSON only, with this schema:
        {{
          "heuristics": [
            {{
              "name": "short_snake_case",
              "description": "why this heuristic may work",
              "order_priority": "best_probability|fewest_candidates|highest_regret|lowest_cost|priority",
              "edge_accept_weight": number,
              "edge_cost_weight": number,
              "edge_value_weight": number,
              "rider_load_penalty": number,
              "order_candidate_penalty": number,
              "multi_offer": true_or_false,
              "max_offers_per_order": integer,
              "min_edge_score": number
            }}
          ]
        }}

        Constraints:
        - Do not output code.
        - Edge scores are computed as:
          edge_accept_weight * accept_prob - edge_cost_weight * cost + edge_value_weight * accept_prob / cost
          + rider_load_penalty * remaining_capacity_ratio - order_candidate_penalty * candidate_count.
        - Positive edge_cost_weight penalizes high cost; negative edge_cost_weight rewards high cost.
        - Use min_edge_score sparingly because score units depend on cost scale; -10000 disables filtering.
        - Keep weights between -10 and 10.
        - Prefer diverse strategies, not near-duplicates.
        - The solver objective is lexicographic: maximize expected accepted orders, then minimize cost.
        """
    ).strip()


def parse_specs(text: str, count: int = 4) -> list[HeuristicSpec]:
    cleaned = _extract_json(text)
    data = json.loads(cleaned)
    raw_specs = data["heuristics"] if isinstance(data, dict) else data
    if not isinstance(raw_specs, list):
        raise ValueError("generated algorithm response must contain a heuristics list")
    specs = []
    for index, item in enumerate(raw_specs[:count]):
        if isinstance(item, dict):
            specs.append(HeuristicSpec.from_dict(item, fallback_name=f"generated_{index + 1}"))
    return specs


def make_algorithm_generator(
    provider: str,
    endpoint: str | None = None,
    model: str | None = None,
    api_key_env: str = "AUTOSOLVER_LLM_API_KEY",
    timeout_sec: float = 20.0,
) -> AlgorithmGenerator:
    if provider == "template":
        return TemplateAlgorithmGenerator()
    if provider == "openai-compatible":
        resolved_model = model or os.getenv("AUTOSOLVER_LLM_MODEL")
        if not resolved_model:
            raise ValueError("--llm-model or AUTOSOLVER_LLM_MODEL is required for openai-compatible generation")
        return OpenAICompatibleAlgorithmGenerator(
            endpoint=endpoint or "https://api.openai.com/v1",
            model=resolved_model,
            api_key_env=api_key_env,
            timeout_sec=timeout_sec,
        )
    raise ValueError(f"unknown algorithm generator provider {provider!r}")


def _chat_completions_url(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return normalized + "/chat/completions"


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = min([pos for pos in (stripped.find("{"), stripped.find("[")) if pos >= 0], default=0)
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    return stripped[start : end + 1] if end >= start else stripped
