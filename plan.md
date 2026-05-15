# Backend Logic For Interviewer Question Bank + Audit Coaching

## Summary
Use shared ADK session state as the communication layer between the interviewer and audit logic. The interviewer agent owns user-facing conversation and the question bank. The audit agent/audit engine owns quality checks from `audit_rules_v1.json` and `process_change_interview_criteria.md`. The audit does not select exact wording or speak to the user; it returns structured coaching that the interviewer converts into a friendly next question.

## Core Data Flow
```text
User answer
  -> interviewer_agent
  -> apply_user_updates()
      -> update template field state
      -> run light audit
      -> maybe run deep section audit
      -> store audit coaching in session state
  -> interviewer selects question from question bank
  -> interviewer asks user one friendly next question

User asks "show audit trace" or "show progress"
  -> show_audit_trace() / show_progress()
  -> return structured visible audit record
```

Backend communication is not hidden agent-to-agent magic. It is explicit:

- `tool_context.state[STATE_KEY]` stores shared working memory.
- `apply_user_updates()` writes field updates and audit results.
- `audit_state()` returns structured audit coaching.
- `select_next_question()` uses audit coaching plus question bank.
- `show_audit_trace()` exposes stored audit records only when requested.

## Key Changes
- Add `kt_consultant/questions/process_change_questions_v1.json`.
- Add question-bank loader and selector:
  - load questions by `section_id`, `field_id`, `question_type`, `intent`, `trigger_rule_ids`
  - select candidate questions from audit feedback
  - return intent/sample wording, not rigid script
- Extend session state with:
  - `current_section_id`
  - `last_question_id`
  - `question_history`
  - `audit_trace`
  - `audit_cadence_events`
  - `pending_audit_coaching`
- Extend audit output with interviewer-facing coaching:
```json
{
  "cadence": "light",
  "target_section_id": "situation_appraisal",
  "target_field_id": "concerns",
  "failed_rule_ids": ["SA-CONCERN-CLEAR"],
  "evidence_gap": "Concerns are broad and not separated into distinct issues.",
  "recommended_question_intent": "separate_overlapping_concerns",
  "question_type": "separation",
  "priority": "high"
}
```
- Keep `prompt_hint` as fallback only when no question-bank item matches.
- Keep `audit_rules_v1.json` and `process_change_interview_criteria.md` audit-only.

## Hybrid Audit Cadence
- Light audit runs after every user answer inside `apply_user_updates()`.
  - Checks updated fields.
  - Finds missing/partial/conflicted mandatory fields.
  - Returns next gap and question intent.
- Deep section audit runs before moving to the next KT section.
  - Trigger when current section mandatory fields look complete or interviewer is about to change sections.
  - Checks all fields in the section against audit rules and criteria.
  - May block section transition by returning `section_ready: false`.
- The interviewer can move forward only when deep audit says the section is ready, or if user explicitly chooses to skip.

## Question Selection Logic
- Audit chooses the **gap**, not the exact question.
- Interviewer chooses wording from question bank.

Selection order:
1. Match `target_field_id`.
2. Prefer questions whose `trigger_rule_ids` include failed audit rule IDs.
3. Prefer `question_type` matching audit coaching.
4. Avoid repeating `last_question_id`.
5. If no match exists, use field `prompt_hint`.

Example:
```text
Audit says:
field = concerns
failed rule = SA-CONCERN-CLEAR
intent = separate_overlapping_concerns

Question selector finds:
SA-CONCERNS-SEPARATE-ISSUES

Interviewer asks naturally:
"Can we break those concerns into separate issues first, so we do not treat one big overlapping problem as if it has only one cause?"
```


## Assumptions
- Interviewer question bank is for interviewer behavior only.
- Audit rules and criteria are for audit quality control only.
- Audit feedback is inspectable on request, not shown after every turn.
- V1 keeps the existing process-change template schema unchanged.



1. User answers a question
   ↓
2. Interviewer extracts information into template fields
   ↓
3. Audit engine checks those fields against audit_rules_v1.json
   ↓
4. Audit engine uses criteria markdown to explain quality gaps
   ↓
5. Audit returns structured feedback:
      - target section
      - target field
      - failed rule
      - evidence gap
      - recommended question intent
   ↓
6. Interviewer looks in question bank for the best matching question
   ↓
7. Interviewer asks the next friendly question

