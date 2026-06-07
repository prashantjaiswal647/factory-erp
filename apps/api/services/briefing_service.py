from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models import ActivityLog, MorningBriefingLog, User
from services.briefing_aggregation import collect_yesterday_factory_snapshot
from services.briefing_translations import translations_for
from services.cost_engine import compute_cost_for_briefing
from services.cost_variance import compute_variance_summary
from services.factory_health import compute_factory_health
from services.wastage_intelligence import compute_wastage_snapshot
from services.profit_intelligence import compute_per_size_profit, compute_profit_snapshot
from typing import Callable
from services.llm_explain import explain_briefing, run_default_llm_provider
from schemas import BriefingExplanation


MISSING = "Data not available"


def _display(value, money: bool = False, missing: str = MISSING) -> str:
    if value is None or value == "" or Decimal(str(value)) <= 0:
        return missing
    numeric = Decimal(str(value))
    rendered = f"{numeric:,.2f}" if money else f"{numeric:,.0f}"
    return f"₹{rendered}" if money else rendered


def render_morning_briefing_message(
    snapshot: dict,
    owner_name: str,
    language: str = "hinglish",
    *,
    summary_mode: bool = False,
    explanation: BriefingExplanation | None = None,
) -> str:
    _, labels = translations_for(language)
    production = snapshot["production"]
    workers = snapshot["workers"]
    sales = snapshot["sales"]
    cost = snapshot.get("cost")
    variance = snapshot.get("variance_summary")
    health = snapshot.get("factory_health")
    wastage = snapshot.get("wastage")
    profit = snapshot.get("profit")
    per_size = snapshot.get("per_size_profit")
    if summary_mode:
        return render_morning_briefing_summary(snapshot, owner_name, language, explanation=explanation)
    lines = [
            labels["greeting"].format(owner=owner_name),
            "",
            labels["production_yesterday"],
            f"{labels['produced']}: {_display(production['produced'], missing=labels['missing'])}",
            f"{labels['target']}: {_display(production['target'], missing=labels['missing'])}",
            f"{labels['gap']}: {_display(production['gap'], missing=labels['missing'])}",
            "",
            labels["workers"],
            f"{labels['present']}: {_display(workers['present'], missing=labels['missing'])}",
            f"{labels['absent']}: {_display(workers['absent'], missing=labels['missing'])}",
            "",
            labels["sales_yesterday"],
            f"{labels['invoices']}: {_display(sales['invoice_count'], missing=labels['missing'])}",
            f"{labels['sales']}: {_display(sales['amount'], money=True, missing=labels['missing'])}",
            f"{labels['collections']}: {_display(sales['collections_received'], money=True, missing=labels['missing'])}",
            f"{labels['outstanding']}: {_display(sales['outstanding_amount'], money=True, missing=labels['missing'])}",
            "",
        ]
    if variance and variance.get("today_cpc") != MISSING:
        lines.extend(
            [
                labels["cost_intelligence"],
                f"{labels['cost_per_cup']}: {_display_cost(variance['today_cpc'], labels['missing'])}",
                f"{labels['seven_day_average']}: {_display_cost(variance['seven_day_cpc'], labels['missing'])}",
                f"{labels['change']}: {_display_percent(variance['variance_percent'], labels['missing'])}",
                f"{labels['primary_driver']}: {variance['primary_driver']}",
                "",
            ]
        )
    elif cost and cost.get("has_cost_data"):
        lines.extend(
            [
                labels["cost_intelligence"],
                f"{labels['cost_per_cup']}: {_display_cost(cost['cost_per_cup'], labels['missing'])}",
                f"{labels['loaded_cost_per_cup']}: {_display_cost(cost['loaded_cost_per_cup'], labels['missing'])}",
                f"{labels['data_quality']}: {labels[cost['source_quality']]}",
                "",
            ]
        )
    if health:
        lines.extend(
            [
                labels["factory_health"],
                f"{labels['health_score']}: {health['overall_score']:.0f}/100",
                f"{labels['health_status']}: {health['health_status']}",
                f"{labels['biggest_strength']}: {health['largest_strength']}",
                f"{labels['biggest_risk']}: {health['largest_risk']}",
                "",
            ]
        )
    if wastage and (wastage["blank_used_kg"] + wastage["bottom_used_kg"]) > 0:
        lines.extend(
            [
                labels["wastage"],
                f"{labels['yesterday']}: {wastage['wastage_percentage']:.1f}%",
                f"{labels['expected']}: {wastage['expected_wastage_percentage']:.1f}%",
                f"{labels['extra']}: {wastage['extra_wastage_percentage']:+.1f}%",
                f"{labels['estimated_loss']}: ₹{wastage['estimated_loss']:,.0f}",
                f"{labels['source']}: {labels.get('source_' + wastage['primary_wastage_source'].lower(), wastage['primary_wastage_source'])}",
                "",
            ]
        )
    if profit and profit["data_available"]:
        lines.extend(
            [
                labels["profit_intelligence"],
                f"{labels['revenue']}: ₹{profit['revenue']:,.0f}",
                f"{labels['profit_cost']}: ₹{profit['total_cost']:,.0f}",
                f"{labels['profit']}: ₹{profit['gross_profit']:,.0f}",
                f"{labels['margin']}: {profit['profit_margin_percent']:.1f}%",
                f"{labels['profit_risk']}: {profit['largest_profit_risk']}",
                "",
            ]
        )
    if per_size and per_size.get("data_available"):
        lines.append(labels["per_size_profit"])
        lines.extend([
            f"{labels['best_size']}: {per_size['best_size']['size_ml']} ml",
            f"Margin: {per_size['best_size']['margin_percent']:.1f}%",
            f"{labels['worst_size']}: {per_size['worst_size']['size_ml']} ml",
            f"Margin: {per_size['worst_size']['margin_percent']:.1f}%",
        ])
        lines.append("")
    risk_items = snapshot["risk_items"]
    if risk_items:
        lines.extend([labels["risks"], ""])
        for item in risk_items:
            lines.append(f"{labels[item['severity']]}:")
            if item["type"] == "low_stock":
                stock_label = labels["bottom_roll"] if item["label"] == "Bottom Roll" else labels["blank_stock"]
                lines.extend(
                    [
                        f"{labels['low_stock']}: {stock_label}",
                        labels["days_left"].format(
                            days=item["days_left"],
                            suffix="s" if item["days_left"] != 1 else "",
                        ),
                    ]
                )
            else:
                lines.extend(
                    [
                        f"{labels['outstanding_alert']}: {item['label']}",
                        _display(item["pending_amount"], money=True, missing=labels["missing"]),
                    ]
                )
            lines.append("")
    lines.append("* Munshi AI")
    return "\n".join(lines)


def render_morning_briefing_summary(
    snapshot: dict,
    owner_name: str,
    language: str = "hinglish",
    explanation: BriefingExplanation | None = None,
) -> str:
    _, labels = translations_for(language)
    health = snapshot.get("factory_health") or {}
    profit = snapshot.get("profit") or {}
    per_size = snapshot.get("per_size_profit") or {}
    best = per_size.get("best_size")
    worst = per_size.get("worst_size")
    score = health.get("overall_score")
    risk = health.get("largest_risk") or labels["missing"]
    profit_value = profit.get("gross_profit") if profit.get("data_available") else None
    lines = [
        labels["greeting"].format(owner=owner_name),
        "",
        labels["factory_health"],
        f"{labels['health_score']}: {score:.0f}/100" if score is not None else f"{labels['health_score']}: {labels['missing']}",
        f"{labels['biggest_risk']}: {risk}",
        "",
        labels["profit_intelligence"],
        f"{labels['profit']}: {_display(profit_value, money=True, missing=labels['missing'])}",
        "",
        labels["per_size_profit"],
        f"{labels['best_size']}: {best['size_ml']} ml" if best else f"{labels['best_size']}: {labels['missing']}",
        f"{labels['worst_size']}: {worst['size_ml']} ml" if worst else f"{labels['worst_size']}: {labels['missing']}",
        "",
    ]
    if explanation:
        explanations = [
            getattr(explanation, f)
            for f in ("cost_explanation", "health_explanation", "wastage_explanation", "profit_explanation", "per_size_explanation")
        ]
        short_explanation = " ".join(e for e in explanations if e).strip()
        lines.extend([
            "✨ Munshi Insight",
            short_explanation,
            "",
            "✅ Action Items",
        ])
        for idx, item in enumerate(explanation.action_items[:3], 1):
            lines.append(f"{idx}. {item}")
        lines.append("")
    lines.append("* Munshi AI")
    return "\n".join(lines)


def _display_cost(value, missing: str) -> str:
    if value == MISSING:
        return missing
    return f"₹{Decimal(str(value)):,.4f}"


def _display_percent(value, missing: str) -> str:
    if value == MISSING:
        return missing
    return f"{Decimal(str(value)):+.1f}%"


def missing_data_fields(snapshot: dict) -> list[str]:
    return [
        f"{section}.{field}"
        for section in ("production", "workers", "sales")
        for field, value in snapshot[section].items()
        if value is None or value == "" or Decimal(str(value)) <= 0
    ]


def audit_briefing(db: Session, factory_id: int, user: User, action: str, briefing_date: date) -> None:
    summary = f"Morning briefing {action.lower()} for {briefing_date.isoformat()}"
    db.add(
        ActivityLog(
            factory_id=factory_id,
            event_type="morning_briefing",
            description=summary,
            log_date=date.today(),
            user_id=user.id,
            user_name=user.full_name or user.username,
            user_role=user.role,
            action_type=f"BRIEFING_{action.upper()}",
            action_summary=summary,
            entity_type="morning_briefing",
            short_statement=summary,
            committed_at=datetime.now(timezone.utc),
        )
    )


def build_briefing(
    db: Session,
    factory_id: int,
    briefing_date: date,
    owner_name: str,
    language: str = "hinglish",
    *,
    summary_mode: bool = False,
    provider: Callable[[dict], Any] | None = None,
) -> dict:
    snapshot = collect_yesterday_factory_snapshot(db, factory_id, briefing_date)
    snapshot["cost"] = compute_cost_for_briefing(db, factory_id, briefing_date)
    snapshot["variance_summary"] = compute_variance_summary(db, factory_id, briefing_date)
    snapshot["factory_health"] = compute_factory_health(db, factory_id, briefing_date)
    snapshot["wastage"] = compute_wastage_snapshot(db, factory_id, briefing_date)
    snapshot["profit"] = compute_profit_snapshot(db, factory_id, briefing_date)
    snapshot["per_size_profit"] = compute_per_size_profit(db, factory_id, briefing_date)
    resolved_language, _ = translations_for(language)

    import time
    start_time = time.time()
    outcome = explain_briefing(
        factory_id=factory_id,
        briefing_date=briefing_date.isoformat(),
        snapshot=snapshot,
        provider=provider or run_default_llm_provider,
        cache=None,
        db=db,
        language=resolved_language,
    )
    generation_time = time.time() - start_time

    message = render_morning_briefing_message(
        snapshot,
        owner_name,
        resolved_language,
        summary_mode=summary_mode,
        explanation=outcome.explanation,
    )
    return {
        "snapshot": snapshot,
        "message_text": message,
        "missing_data": missing_data_fields(snapshot),
        "risk_items": snapshot["risk_items"],
        "language": resolved_language,
        "ai_explanation": outcome.explanation.model_dump(mode="json") if outcome.explanation else None,
        "ai_observability": {
            "model_name": outcome.explanation.model_version if outcome.explanation else None,
            "token_usage": outcome.explanation.tokens_used if outcome.explanation else 0,
            "cache_hit": outcome.tier == "cache",
            "generation_time": round(generation_time, 3),
            "fallback_reason": outcome.rejected_reason,
        },
    }


def send_briefing(
    db: Session,
    factory_id: int,
    briefing_date: date,
    owner: User,
    *,
    sender=None,
) -> tuple[MorningBriefingLog, bool]:
    from models import Factory
    from services.briefing_scheduler import deliver_factory_briefing
    from services.telegram_delivery import send_telegram_message

    factory = db.query(Factory).filter(Factory.id == factory_id).one()
    return deliver_factory_briefing(
        db,
        factory,
        owner,
        briefing_date,
        sender=sender or send_telegram_message,
    )
