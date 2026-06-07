from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import Any, Callable, Protocol

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import ExplanationCache as ExplanationCacheRow
from schemas import BriefingExplanation


logger = logging.getLogger(__name__)
NUMBER_PATTERN = re.compile(r"(?<![\w])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
EXPLANATION_FIELDS = (
    "cost_explanation",
    "health_explanation",
    "wastage_explanation",
    "profit_explanation",
    "per_size_explanation",
)
CACHE_TTL_SECONDS = int(os.getenv("LLM_EXPLAIN_CACHE_TTL_SECONDS", "86400"))
PII_TYPES = ("customer", "supplier", "worker")
PII_PREFIXES = {
    "customer": "Customer",
    "supplier": "Supplier",
    "worker": "Worker",
}


class ExplanationRedisCache(Protocol):
    def get(self, key: str) -> str | bytes | None: ...

    def setex(self, key: str, ttl_seconds: int, value: str) -> Any: ...


@dataclass(frozen=True)
class ExplanationOutcome:
    explanation: BriefingExplanation | None
    tier: str
    rejected_reason: str | None = None


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _pii_type_for_key(key: Any, context: str | None = None) -> str | None:
    normalized = _normalized_key(key)
    for pii_type in PII_TYPES:
        if pii_type in normalized:
            return pii_type
    if normalized in {"label", "name", "full_name", "display_name"}:
        return context
    return None


def _owner_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return normalized in {
        "owner",
        "owner_name",
        "owner_full_name",
        "factory_owner",
        "factory_owner_name",
    }


def to_llm_input(snapshot: dict) -> dict:
    """Return a redacted deep copy suitable for an external LLM provider."""
    aliases: dict[str, dict[str, str]] = {pii_type: {} for pii_type in PII_TYPES}

    def alias(value: str, pii_type: str) -> str:
        clean = value.strip()
        if not clean:
            return clean
        existing = aliases[pii_type].get(clean)
        if existing is not None:
            return existing
        replacement = f"{PII_PREFIXES[pii_type]} {len(aliases[pii_type]) + 1}"
        aliases[pii_type][clean] = replacement
        return replacement

    def discover(value: Any, *, key: Any = "", context: str | None = None) -> None:
        if isinstance(value, dict):
            item_context = context
            type_value = value.get("type")
            if isinstance(type_value, str):
                normalized_type = _normalized_key(type_value)
                if normalized_type in {"customer", "outstanding", "customer_outstanding"}:
                    item_context = "customer"
                elif normalized_type in PII_TYPES:
                    item_context = normalized_type
            for child_key, child_value in value.items():
                discover(
                    child_value,
                    key=child_key,
                    context=_pii_type_for_key(child_key, item_context) or item_context,
                )
        elif isinstance(value, (list, tuple)):
            for child in value:
                discover(child, key=key, context=context)
        elif isinstance(value, str) and not _owner_key(key):
            pii_type = _pii_type_for_key(key, context)
            if pii_type is not None:
                alias(value, pii_type)

    discover(snapshot)

    def redact(value: Any, *, key: Any = "", context: str | None = None) -> Any:
        if isinstance(value, dict):
            item_context = context
            type_value = value.get("type")
            if isinstance(type_value, str):
                normalized_type = _normalized_key(type_value)
                if normalized_type in {"customer", "outstanding", "customer_outstanding"}:
                    item_context = "customer"
                elif normalized_type in PII_TYPES:
                    item_context = normalized_type
            return {
                child_key: redact(
                    child_value,
                    key=child_key,
                    context=_pii_type_for_key(child_key, item_context) or item_context,
                )
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [redact(child, key=key, context=context) for child in value]
        if isinstance(value, tuple):
            return [redact(child, key=key, context=context) for child in value]
        if isinstance(value, str):
            if _owner_key(key):
                return "Factory Owner"
            pii_type = _pii_type_for_key(key, context)
            if pii_type is not None:
                return alias(value, pii_type)
            redacted = value
            for names in aliases.values():
                for original, replacement in names.items():
                    redacted = redacted.replace(original, replacement)
            return redacted
        return value

    return redact(snapshot)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)).normalize()
        except InvalidOperation:
            return None
    return None


def _source_numbers(value: Any) -> set[Decimal]:
    numbers: set[Decimal] = set()
    if isinstance(value, dict):
        for child in value.values():
            numbers.update(_source_numbers(child))
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            numbers.update(_source_numbers(child))
    else:
        numeric = _decimal(value)
        if numeric is not None:
            numbers.add(numeric)
    return numbers


def _explanation_text(explanation: BriefingExplanation) -> str:
    parts = [getattr(explanation, field) for field in EXPLANATION_FIELDS]
    parts.extend(explanation.action_items)
    return "\n".join(part for part in parts if part)


def extract_numeric_values(text: str) -> list[Decimal]:
    values = []
    for match in NUMBER_PATTERN.finditer(text or ""):
        raw = match.group(0).replace(",", "").rstrip("%")
        try:
            values.append(Decimal(raw).normalize())
        except InvalidOperation:
            continue
    return values


def validate_explanation_numbers(explanation: BriefingExplanation, snapshot: dict) -> tuple[bool, list[str]]:
    allowed = _source_numbers(snapshot)
    rejected = [
        str(value)
        for value in extract_numeric_values(_explanation_text(explanation))
        if value not in allowed
    ]
    return not rejected, rejected


def get_pii_names(snapshot: dict) -> set[str]:
    names = set()

    def discover(value: Any, *, key: Any = "", context: str | None = None) -> None:
        if isinstance(value, dict):
            item_context = context
            type_value = value.get("type")
            if isinstance(type_value, str):
                normalized_type = _normalized_key(type_value)
                if normalized_type in {"customer", "outstanding", "customer_outstanding"}:
                    item_context = "customer"
                elif normalized_type in PII_TYPES:
                    item_context = normalized_type
            for child_key, child_value in value.items():
                discover(
                    child_value,
                    key=child_key,
                    context=_pii_type_for_key(child_key, item_context) or item_context,
                )
        elif isinstance(value, (list, tuple)):
            for child in value:
                discover(child, key=key, context=context)
        elif isinstance(value, str):
            if _owner_key(key):
                names.add(value.strip())
            else:
                pii_type = _pii_type_for_key(key, context)
                if pii_type is not None:
                    names.add(value.strip())

    discover(snapshot)
    return {n for n in names if n}


def validate_no_pii_leak(explanation: BriefingExplanation, snapshot: dict) -> tuple[bool, list[str]]:
    original_names = get_pii_names(snapshot)
    text = _explanation_text(explanation).lower()
    leaked = [name for name in original_names if name.lower() in text]
    return not leaked, leaked



HASH_COMPONENTS = (
    "factory_health",
    "profit",
    "cost",
    "wastage",
    "per_size_profit",
)


def generate_snapshot_hash(snapshot: dict) -> str:
    components = {key: snapshot.get(key) for key in HASH_COMPONENTS}
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot_cache_key(factory_id: int, briefing_date: str, snapshot_hash: str, language: str) -> str:
    return f"llm-explain:{factory_id}:{briefing_date}:{language}:{snapshot_hash}"


def _default_cache() -> ExplanationRedisCache | None:
    try:
        import redis

        return redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0"),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    except Exception:
        logger.warning("LLM explanation cache initialization failed", exc_info=True)
        return None


def _parse_explanation(value: Any) -> BriefingExplanation:
    if isinstance(value, BriefingExplanation):
        return value
    if isinstance(value, (str, bytes)):
        return BriefingExplanation.model_validate_json(value)
    return BriefingExplanation.model_validate(value)


def _read_cached(
    cache: ExplanationRedisCache | None,
    key: str,
    llm_input: dict,
    snapshot: dict,
) -> BriefingExplanation | None:
    if cache is None:
        return None
    try:
        raw = cache.get(key)
        if not raw:
            return None
        explanation = _parse_explanation(raw)
        valid_nums, rejected_nums = validate_explanation_numbers(explanation, llm_input)
        valid_pii, leaked_pii = validate_no_pii_leak(explanation, snapshot)
        if not (valid_nums and valid_pii):
            logger.warning("Rejected cached LLM explanation: nums=%s, pii=%s", valid_nums, valid_pii)
            return None
        return explanation
    except Exception:
        logger.warning("LLM explanation cache read failed", exc_info=True)
        return None


def _read_db_cache(
    db: Session,
    *,
    factory_id: int,
    snapshot_hash: str,
    language: str,
    llm_input: dict,
    snapshot: dict,
) -> tuple[ExplanationCacheRow | None, BriefingExplanation | None]:
    row = (
        db.query(ExplanationCacheRow)
        .filter(
            ExplanationCacheRow.factory_id == factory_id,
            ExplanationCacheRow.snapshot_hash == snapshot_hash,
            ExplanationCacheRow.language == language,
        )
        .first()
    )
    if row is None:
        return None, None
    try:
        explanation = _parse_explanation(row.explanation_json)
        valid_nums, rejected_nums = validate_explanation_numbers(explanation, llm_input)
        valid_pii, leaked_pii = validate_no_pii_leak(explanation, snapshot)
        if not (valid_nums and valid_pii):
            logger.warning(
                "Rejected database explanation cache cache_id=%s: nums=%s, pii=%s",
                row.id,
                valid_nums,
                valid_pii,
            )
            return row, None
        row.hit_count += 1
        db.flush()
        return row, explanation
    except (ValidationError, ValueError, TypeError):
        logger.warning("Invalid database explanation cache cache_id=%s", row.id, exc_info=True)
        return row, None


def _store_db_cache(
    db: Session,
    *,
    factory_id: int,
    snapshot_hash: str,
    briefing_date: date,
    language: str,
    explanation: BriefingExplanation,
) -> ExplanationCacheRow:
    row = ExplanationCacheRow(
        factory_id=factory_id,
        snapshot_hash=snapshot_hash,
        briefing_date=briefing_date,
        language=language,
        explanation_json=explanation.model_dump(mode="json"),
        model_name=explanation.model_version,
        token_usage=explanation.tokens_used,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        return (
            db.query(ExplanationCacheRow)
            .filter(
                ExplanationCacheRow.factory_id == factory_id,
                ExplanationCacheRow.snapshot_hash == snapshot_hash,
                ExplanationCacheRow.language == language,
            )
            .one()
        )


def explanation_cache_stats(db: Session) -> dict:
    stored, hits = db.query(
        func.count(ExplanationCacheRow.id),
        func.coalesce(func.sum(ExplanationCacheRow.hit_count), 0),
    ).one()
    misses = int(stored or 0)
    hits = int(hits or 0)
    total = hits + misses
    return {
        "cache_hits": hits,
        "cache_misses": misses,
        "hit_rate": round((hits / total * 100), 2) if total else 0.0,
        "stored_explanations": misses,
    }


def explain_briefing(
    *,
    factory_id: int,
    briefing_date: str,
    snapshot: dict,
    provider: Callable[[dict], Any] | None = None,
    cache: ExplanationRedisCache | None = None,
    db: Session | None = None,
    language: str = "hinglish",
) -> ExplanationOutcome:
    snapshot_hash = generate_snapshot_hash(snapshot)
    cache_client = cache if cache is not None else (_default_cache() if db is None else None)
    cache_key = _snapshot_cache_key(factory_id, briefing_date, snapshot_hash, language)
    llm_input = to_llm_input(snapshot)
    rejection = None

    if db is not None:
        _, stored = _read_db_cache(
            db,
            factory_id=factory_id,
            snapshot_hash=snapshot_hash,
            language=language,
            llm_input=llm_input,
            snapshot=snapshot,
        )
        if stored is not None:
            return ExplanationOutcome(explanation=stored, tier="cache")

    if provider is not None:
        try:
            explanation = _parse_explanation(provider(llm_input))
            valid_nums, rejected_nums = validate_explanation_numbers(explanation, llm_input)
            valid_pii, leaked_pii = validate_no_pii_leak(explanation, snapshot)
            if valid_nums and valid_pii:
                if db is not None:
                    _store_db_cache(
                        db,
                        factory_id=factory_id,
                        snapshot_hash=snapshot_hash,
                        briefing_date=date.fromisoformat(briefing_date),
                        language=language,
                        explanation=explanation,
                    )
                if cache_client is not None:
                    try:
                        cache_client.setex(cache_key, CACHE_TTL_SECONDS, explanation.model_dump_json())
                    except Exception:
                        logger.warning("LLM explanation cache write failed", exc_info=True)
                return ExplanationOutcome(explanation=explanation, tier="ai")

            rejections = []
            if not valid_nums:
                rejections.append(f"unsupported numeric values: {', '.join(rejected_nums)}")
            if not valid_pii:
                rejections.append(f"leaked PII: {', '.join(leaked_pii)}")
            rejection = "; ".join(rejections)
            logger.warning("Rejected LLM explanation: %s", rejection)
        except TimeoutError:
            rejection = "provider timeout"
            logger.warning("LLM explanation provider timed out")
        except (ValidationError, ValueError, TypeError):
            rejection = "invalid provider response"
            logger.warning("LLM explanation provider returned invalid data", exc_info=True)
        except Exception:
            rejection = "provider failure"
            logger.warning("LLM explanation provider failed", exc_info=True)

    cached = _read_cached(cache_client, cache_key, llm_input, snapshot)
    if cached is not None:
        return ExplanationOutcome(explanation=cached, tier="cache", rejected_reason=rejection)
    return ExplanationOutcome(explanation=None, tier="deterministic", rejected_reason=rejection)


def run_default_llm_provider(snapshot: dict) -> dict:
    from ai_agent import initialize_groq_llm
    llm = initialize_groq_llm()
    if llm is None:
        raise ValueError("Groq LLM is not configured")

    system_prompt = (
        "You are Munshi AI, a loyal, sharp, and traditional Indian accountant for a paper cup factory.\n"
        "Your task is to analyze the daily factory snapshot and explain each section.\n"
        "You MUST return a JSON object matching the following structure:\n"
        "{\n"
        "  \"cost_explanation\": \"Cost explanation (max 2 sentences)\",\n"
        "  \"health_explanation\": \"Health score explanation (max 2 sentences)\",\n"
        "  \"wastage_explanation\": \"Wastage explanation (max 2 sentences)\",\n"
        "  \"profit_explanation\": \"Profit and margin explanation (max 2 sentences)\",\n"
        "  \"per_size_explanation\": \"Per-size profit performance explanation (max 2 sentences)\",\n"
        "  \"action_items\": [\"Up to 3 short actionable business steps to take today\"]\n"
        "}\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. Never invent or hallucinate any numbers. All numbers in your explanations MUST be extracted directly from the provided snapshot JSON.\n"
        "2. Never mention real customer names, supplier names, worker names, or the owner's name. Use the redacted placeholders if present (e.g. 'Customer 1', 'Supplier 1', 'Worker 1').\n"
        "3. Your output must be a single, valid JSON object and nothing else. No markdown formatting blocks around JSON."
    )
    user_prompt = f"Snapshot:\n{json.dumps(snapshot, default=str)}"

    response = llm.invoke(f"{system_prompt}\n\n{user_prompt}")
    text = str(getattr(response, "content", response)).strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    parsed = json.loads(text)
    parsed["model_version"] = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "llama-3.3-70b-versatile"
    parsed["tokens_used"] = 0
    return parsed

