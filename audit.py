from __future__ import annotations

from typing import Any

from ..schema import ProcessTemplate
from .loaders import load_audit_rules, load_interview_criteria
from .validators import validate_rule_evidence


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if value == []:
        return True
    if value == {}:
        return True
    return False


def status_for_value(value: Any, requested_status: str | None = None) -> str:
    if requested_status == "conflicted":
        return "conflicted"
    if is_empty_value(value):
        return "missing"
    if requested_status == "complete":
        return "complete"
    if isinstance(value, str) and len(value.strip()) >= 20:
        return "complete"
    if isinstance(value, list) and len(value) >= 2:
        return "complete"
    if isinstance(value, dict) and len(value) >= 2:
        return "complete"
    return "partial"


def _section_rules() -> dict[str, Any]:
    return load_audit_rules().get("section_rules", {})


def _rule_lookup() -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for section_id, section in _section_rules().items():
        for rule in section.get("rules", []):
            for field_id in rule.get("field_ids", []):
                lookup.setdefault(field_id, []).append(
                    {
                        "rule_id": rule["rule_id"],
                        "section_id": section_id,
                        "criteria_reference": section.get("criteria_reference"),
                        "severity": rule.get("severity", "medium"),
                        "evidence_needed": rule.get("evidence_needed"),
                        "validators": rule.get("validators", []),
                    }
                )
    return lookup


def _field_rule_results(item: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for rule in _rule_lookup().get(item["field_id"], []):
        validation = validate_rule_evidence(item, rule)
        passed = item["status"] == "complete" and validation["passed"]
        failed_checks = [
            check["reason"] for check in validation["checks"] if not check["passed"]
        ]
        results.append(
            {
                "rule_id": rule["rule_id"],
                "field_id": item["field_id"],
                "section_id": rule["section_id"],
                "criteria_reference": rule["criteria_reference"],
                "severity": rule["severity"],
                "passed": passed,
                "evidence_score": validation["score"],
                "validator_checks": validation["checks"],
                "reason": (
                    "Field has complete, rule-validated evidence."
                    if passed
                    else "; ".join(failed_checks) or f"Field status is {item['status']}."
                ),
                "evidence_needed": rule["evidence_needed"],
            }
        )
    return results


def _section_quality(section_id: str) -> dict[str, Any] | None:
    section = _section_rules().get(section_id)
    if not section:
        return None
    return {
        "criteria_reference": section.get("criteria_reference"),
        "required_quality": section.get("required_quality"),
    }


def choose_next_field(template: ProcessTemplate, state: dict[str, Any]) -> tuple[str | None, str]:
    field_state = state["fields"]

    for field in template.fields:
        item = field_state[field.id]
        if field.is_mandatory and item["status"] in {"missing", "conflicted"}:
            return field.id, "mandatory field is not yet usable"

    for field in template.fields:
        item = field_state[field.id]
        failed_rules = [result for result in _field_rule_results(item) if not result["passed"]]
        if field.is_mandatory and failed_rules:
            rule = failed_rules[0]
            return (
                field.id,
                f"mandatory field fails {rule['rule_id']}: {rule['evidence_needed']}",
            )

    for field in template.fields:
        item = field_state[field.id]
        if field.is_mandatory and item["status"] == "partial":
            return field.id, "mandatory field needs sharper evidence"

    for field in template.fields:
        item = field_state[field.id]
        if item["status"] == "conflicted":
            return field.id, "field contains conflicting information"

    for field in template.fields:
        item = field_state[field.id]
        if not field.is_mandatory and item["status"] == "missing":
            return field.id, "optional field may improve the consultant report"

    return None, "all template fields have at least partial coverage"


def make_question(field: dict[str, Any] | None, reason: str) -> str:
    if field is None:
        return (
            "We have enough structure for a first pass. Would you like me to generate "
            "the completed JSON and consultant report now, or should we refine any section?"
        )

    label = field["label"]
    hint = field["prompt_hint"].rstrip("?")
    section = field["section_title"]

    if field["status"] == "partial":
        return (
            f"I have a start on {label.lower()}, but I want to make that part stronger. "
            f"In the {section} section, what details or evidence would make this clear?"
        )

    if field["status"] == "conflicted":
        return (
            f"I see mixed signals around {label.lower()}. Can you help me reconcile what "
            "is true right now versus what is planned?"
        )

    return f"Let us fill in {label.lower()} next. {hint}, in your own words?"


def audit_state(template: ProcessTemplate, state: dict[str, Any]) -> dict[str, Any]:
    fields = state["fields"]
    criteria_text = load_interview_criteria()
    mandatory = [fields[field.id] for field in template.mandatory_fields]
    complete_mandatory = [
        item for item in mandatory if item["status"] == "complete"
    ]
    usable_mandatory = [
        item for item in mandatory if item["status"] in {"partial", "complete"}
    ]
    weak_fields = []
    triggered_rule_results = []
    for item in fields.values():
        field_results = _field_rule_results(item)
        if item["status"] in {"missing", "partial", "conflicted"}:
            quality = _section_quality(item["section_id"]) or {}
            weak_fields.append(
                {
                    "field_id": item["field_id"],
                    "label": item["label"],
                    "status": item["status"],
                    "section_title": item["section_title"],
                    "criteria_reference": quality.get("criteria_reference"),
                    "required_quality": quality.get("required_quality"),
                    "rule_results": [
                        result for result in field_results if not result["passed"]
                    ],
                }
            )
        triggered_rule_results.extend(
            result for result in field_results if not result["passed"]
        )

    next_field_id, reason = choose_next_field(template, state)
    next_field = fields.get(next_field_id) if next_field_id else None
    suggested_question = make_question(next_field, reason)
    next_quality = (
        _section_quality(next_field["section_id"])
        if next_field
        else None
    ) or {}
    next_rules = (
        [result for result in _field_rule_results(next_field) if not result["passed"]]
        if next_field
        else []
    )

    mandatory_total = len(mandatory)
    completeness = round(
        len(complete_mandatory) / mandatory_total,
        2,
    ) if mandatory_total else 1.0
    usable_completeness = round(
        len(usable_mandatory) / mandatory_total,
        2,
    ) if mandatory_total else 1.0

    return {
        "turn": state["turn_count"],
        "latest_user_evidence": state.get("latest_user_evidence", ""),
        "fields_updated": state.get("latest_updated_fields", []),
        "mandatory_field_completeness": completeness,
        "mandatory_field_usable_coverage": usable_completeness,
        "weak_or_missing_fields": weak_fields[:8],
        "triggered_rule_results": triggered_rule_results[:12],
        "next_target_field": next_field_id,
        "next_target_label": next_field["label"] if next_field else None,
        "next_target_criteria_reference": next_quality.get("criteria_reference"),
        "next_target_required_quality": next_quality.get("required_quality"),
        "next_target_rule_results": next_rules,
        "reason_for_next_question": reason,
        "suggested_interviewer_wording": suggested_question,
        "criteria_source": "kt_consultant/audit/process_change_interview_criteria.md",
        "criteria_reference_available": bool(criteria_text.strip()),
        "trace_note": (
            "Structured audit rationale only; hidden model chain-of-thought is not exposed."
        ),
    }
