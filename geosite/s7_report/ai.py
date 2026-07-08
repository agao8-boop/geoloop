"""s7 — AI design review via the Claude API.

Non-streaming messages.create on claude-haiku-4-5 with a JSON-schema
structured output. Every failure path degrades gracefully: the caller gets
(None, reason) and renders the report without the AI section.
"""

import json
import os

import anthropic

MODEL = "claude-haiku-4-5"

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "concerns": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "strengths", "concerns", "risks", "next_steps"],
    "additionalProperties": False,
}

REVIEW_SYSTEM = """\
You are a senior geothermal (GSHP) design reviewer critiquing a PRE-FEASIBILITY
borefield estimate produced by an automated screening tool — not an engineering
design. The user message is a JSON summary of the estimate.

Rules:
1. The caveat "this tool is a pre-feasibility estimator; a licensed engineer
   and a thermal response test are required before installation" MUST appear
   verbatim or closely paraphrased in `risks` or `next_steps`.
2. Be critical AND encouraging: include at least two genuine strengths and at
   least two genuine concerns.
3. Use ONLY the numbers provided in the JSON. Never invent site data,
   measurements, or costs that are not present.
4. Specifically evaluate, when the data shows them:
   - nb_source of "depth_fallback" (small load) or "expert_override"
   - thermal imbalance (imbalance_m) and the solar_flag recommendation
   - GSHP energy coverage below ~85%
   - simple payback above ~15 years
   - capacity_warning = true (load may exceed the footprint)
5. Always name the three standing pipeline caveats among concerns or risks:
   (a) ground loads are zone loads with no heat-pump COP correction,
   (b) soil conductivity is a county-median estimate with unquantified
       in-county spread (saturation effects on k are ignored),
   (c) the borehole-count range comes from a simplified rectangular
       footprint model.
6. `verdict` is a single sentence.
Respond with JSON matching the required schema.
"""


def generate_review(report: dict) -> tuple[dict | None, str | None]:
    """Return (review_dict, None) on success or (None, reason) on any failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "not configured (ANTHROPIC_API_KEY is not set)"

    review_input = report.get("review_input", report)

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=30.0)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=REVIEW_SYSTEM,
            output_config={"format": {"type": "json_schema",
                                      "schema": REVIEW_SCHEMA}},
            messages=[{"role": "user",
                       "content": json.dumps(review_input, sort_keys=True)}],
        )
    except anthropic.AuthenticationError:
        return None, "authentication failed (check ANTHROPIC_API_KEY)"
    except anthropic.APITimeoutError:
        return None, "the review request timed out"
    except anthropic.APIConnectionError:
        return None, "could not reach the Claude API"
    except anthropic.APIStatusError as exc:
        return None, f"Claude API error (HTTP {exc.status_code})"

    try:
        text = next(b.text for b in response.content if b.type == "text")
        review = json.loads(text)
        if not isinstance(review, dict):
            raise ValueError("review is not an object")
        missing = set(REVIEW_SCHEMA["required"]) - set(review)
        if missing:
            raise ValueError(f"missing keys: {missing}")
    except (StopIteration, ValueError, TypeError):
        return None, "the AI response could not be parsed"

    return review, None
