from __future__ import annotations

import re
from typing import Any


def value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {val}" for key, val in value.items())
    return str(value)


def value_detail_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, list):
        return len([item for item in value if str(item).strip()])
    if isinstance(value, dict):
        return len([key for key, val in value.items() if str(key).strip() and str(val).strip()])
    return len(str(value).strip())


def has_specificity_signal(text: str, signal: str) -> bool:
    normalized = text.lower()
    if signal == "number_or_metric":
        return bool(re.search(r"\d|%|\bkpi\b|\bmetric\b|\bhours?\b|\bdays?\b", normalized))
    if signal == "cause_language":
        return any(token in normalized for token in ["because", "due to", "caused by", "root cause", "driven by"])
    if signal == "risk_language":
        return any(token in normalized for token in ["risk", "fail", "delay", "impact", "safety", "quality", "outage"])
    if signal == "comparison_or_alternative":
        return any(token in normalized for token in ["option", "alternative", "versus", "vs", "pro", "con", "tradeoff"])
    if signal == "time_or_schedule":
        return any(token in normalized for token in ["hour", "day", "week", "month", "schedule", "rollout", "phase"])
    if signal == "owner_or_location":
        return any(token in normalized for token in ["owner", "team", "facility", "site", "line", "area", "plant"])
    if signal == "explicit_none_allowed":
        return any(token in normalized for token in ["not applicable", "n/a", "none", "no impact", "no risk"])
    return False


def validate_rule_evidence(item: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    validators = rule.get("validators") or [{"type": "non_empty"}]
    value = item.get("value")
    evidence = item.get("evidence") or []
    text = value_text(value)
    combined_text = " ".join([text, *[str(entry) for entry in evidence]])
    checks = []

    for validator in validators:
        validator_type = validator.get("type")
        passed = True
        reason = "Passed."

        if validator_type == "non_empty":
            passed = bool(value_detail_size(value))
            reason = "Field has a non-empty value." if passed else "Field has no usable value."
        elif validator_type == "evidence_present":
            passed = bool(evidence)
            reason = "Field has captured evidence." if passed else "No source evidence is attached to this field."
        elif validator_type == "min_detail":
            minimum = int(validator.get("min", 20))
            size = value_detail_size(value)
            if isinstance(value, (list, dict)):
                passed = size >= int(validator.get("min_items", 1))
                reason = (
                    f"Field has {size} structured item(s)."
                    if passed
                    else f"Field needs at least {validator.get('min_items', 1)} structured item(s)."
                )
            else:
                passed = size >= minimum
                reason = (
                    f"Field has {size} characters of detail."
                    if passed
                    else f"Field needs at least {minimum} characters of detail."
                )
        elif validator_type == "specificity_signal":
            signals = validator.get("signals") or []
            minimum_matches = int(validator.get("min_matches", 1))
            matches = [signal for signal in signals if has_specificity_signal(combined_text, signal)]
            passed = len(matches) >= minimum_matches
            reason = (
                f"Specificity signals found: {', '.join(matches)}."
                if passed
                else f"Needs specificity signal(s): {', '.join(signals)}."
            )

        checks.append(
            {
                "validator": validator_type,
                "passed": passed,
                "reason": reason,
            }
        )

    passed_count = len([check for check in checks if check["passed"]])
    score = round(passed_count / len(checks), 2) if checks else 1.0
    return {
        "passed": all(check["passed"] for check in checks),
        "score": score,
        "checks": checks,
    }

