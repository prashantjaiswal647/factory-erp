import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable

from sqlalchemy.orm import Session

from models import MachineTemplate


@dataclass(frozen=True)
class TemplateVerificationResult:
    confidence_score: float
    decision: str
    reasons: list[str]


def _normalized_keys(payload: Dict[str, Any]) -> set[str]:
    return {str(key).strip().lower() for key in payload.keys() if str(key).strip()}


def _has_duplicate_template(db: Session, template: MachineTemplate) -> bool:
    existing_templates: Iterable[MachineTemplate] = (
        db.query(MachineTemplate)
        .filter(MachineTemplate.id != template.id)
        .filter(MachineTemplate.status == "approved")
        .filter(MachineTemplate.machine_type == template.machine_type)
        .all()
    )
    template_keys = _normalized_keys(template.base_config) | _normalized_keys(template.custom_fields)
    for existing in existing_templates:
        existing_keys = _normalized_keys(existing.base_config) | _normalized_keys(existing.custom_fields)
        if existing_keys == template_keys:
            return True
    return False


def _local_sanity_check(template: MachineTemplate, duplicate_found: bool) -> TemplateVerificationResult:
    reasons: list[str] = []
    score = 0.95

    if len(template.machine_type.strip()) < 3:
        score -= 0.35
        reasons.append("Machine type is too short.")

    if not template.base_config and not template.custom_fields:
        score -= 0.45
        reasons.append("Template does not define any configuration fields.")

    merged_fields = {**template.base_config, **template.custom_fields}
    empty_values = [key for key, value in merged_fields.items() if value in ("", None)]
    if empty_values:
        score -= 0.2
        reasons.append(f"Empty values found for: {', '.join(map(str, empty_values[:5]))}.")

    numeric_keys = ["speed", "capacity", "size", "width", "height", "voltage", "mould", "mold", "press"]
    for key, value in merged_fields.items():
        key_text = str(key).lower()
        if any(token in key_text for token in numeric_keys):
            if isinstance(value, (int, float)) and value < 0:
                score -= 0.3
                reasons.append(f"{key} cannot be negative.")

    if duplicate_found:
        score -= 0.4
        reasons.append("An approved template with the same machine type and field structure already exists.")

    score = max(0.0, min(1.0, score))
    return TemplateVerificationResult(
        confidence_score=score,
        decision="approved" if score > 0.9 else "pending",
        reasons=reasons or ["Template passed deterministic sanity checks."],
    )


def _llm_check(template: MachineTemplate, duplicate_found: bool) -> TemplateVerificationResult | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = {
            "machine_type": template.machine_type,
            "base_config": template.base_config,
            "custom_fields": template.custom_fields,
            "duplicate_found": duplicate_found,
            "instructions": (
                "Evaluate machine template sanity, duplicate risk, and logical consistency. "
                "Return strict JSON with confidence_score from 0 to 1 and reasons as a string array."
            ),
        }
        response = client.chat.completions.create(
            model=os.getenv("MACHINE_TEMPLATE_LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
            messages=[
                {"role": "system", "content": "You are a manufacturing ERP data-quality reviewer. Return only JSON."},
                {"role": "user", "content": json.dumps(prompt, default=str)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        confidence = float(parsed.get("confidence_score", 0))
        reasons = parsed.get("reasons") if isinstance(parsed.get("reasons"), list) else ["LLM returned no reasons."]
        return TemplateVerificationResult(
            confidence_score=max(0.0, min(1.0, confidence)),
            decision="approved" if confidence > 0.9 and not duplicate_found else "pending",
            reasons=[str(reason) for reason in reasons],
        )
    except Exception as exc:
        return TemplateVerificationResult(
            confidence_score=0.0,
            decision="pending",
            reasons=[f"AI verification failed and requires manual review: {exc}"],
        )


def verify_machine_template_submission(db: Session, template: MachineTemplate) -> TemplateVerificationResult:
    duplicate_found = _has_duplicate_template(db, template)
    return _llm_check(template, duplicate_found) or _local_sanity_check(template, duplicate_found)
