"""Cortex, a minimal, explicit agent loop you (and your coding agent) can read end
to end. This is the agent you ship: your PM chief-of-staff. You build it by
directing your coding agent (Claude Code / Cursor / Codex) to shape this file. You
never have to hand-write it.

Every bound the course talks about is visible right here in code, not buried in a
framework: the max-iteration counter, the cost cap, the revision cap, the
stop/escalate conditions, the auto-queue cap, and the absence of any publish tool.

Usage (ask your coding agent to run these for you, or run them yourself):
    python agent.py                # runs the happy-path task (weekly status update)
    python agent.py missing-data   # the stuck/escalate case
    python agent.py jailbreak       # the prompt-injection refusal case

Every run ends by showing the drafted status update in a FINAL STATUS UPDATE block
(or LAST DRAFT, held, if a bound trips), and saves it to run-output/. That file is
always a draft held for a human, it is never posted, there is no publish tool.

Requires OPENAI_API_KEY in your environment (see .env.example). Model and bounds
are read from env so you can tune them, that tuning is your M5 deliverable.

The loop is deliberately transparent (hand-written tool-calling on the openai
client) so a grader can see the machinery. Keep the bounds explicit if you rework it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from openai import OpenAI

import gates
import tools
from critic import review
from prompts import CORTEX_SYSTEM

try:  # load .env if python-dotenv is installed; harmless if it isn't
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# --- Bounds (your M5 deliverable: tune these and justify them) ----------------
MODEL = os.environ.get("CORTEX_MODEL", "gpt-4o-mini")
MAX_ITERATIONS = int(os.environ.get("CORTEX_MAX_ITERATIONS", "8"))
MAX_REVISIONS = int(os.environ.get("CORTEX_MAX_REVISIONS", "2"))
COST_CAP_USD = float(os.environ.get("CORTEX_COST_CAP_USD", "0.50"))
MAX_QUEUE_ITEMS = int(os.environ.get("CORTEX_MAX_QUEUE_ITEMS", "10"))
# Rough $ per 1M tokens for your chosen model, set to match its pricing.
PRICE_IN = float(os.environ.get("CORTEX_PRICE_IN_PER_M", "0.15"))
PRICE_OUT = float(os.environ.get("CORTEX_PRICE_OUT_PER_M", "0.60"))

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_project", "description": "Look up a project by its ID (status, flags, linked PRD).",
        "parameters": {"type": "object", "properties": {
            "project_id": {"type": "string"}}, "required": ["project_id"]}}},
    {"type": "function", "function": {
        "name": "get_activity",
        "description": "Pull recent engineering activity for a project (merged PRs, open issues, Sev-1s).",
        "parameters": {"type": "object", "properties": {
            "project_id": {"type": "string"}}, "required": ["project_id"]}}},
    {"type": "function", "function": {
        "name": "search_past_updates",
        "description": "Search previous status updates and decisions for tone and precedent.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_roadmap",
        "description": "Return the roadmap. Some items are flagged confidential/embargoed.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_norms", "description": "Return the team norms / PM playbook the agent must follow.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "propose_stories",
        "description": "Queue a set of backlog stories for human approval (creates nothing; rejected above the item cap).",
        "parameters": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "stories": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"}}, "required": ["project_id", "stories"]}}},
]


class Bounds:
    """Tracks spend and trips the cost cap. This is enforced OUTSIDE the model."""

    def __init__(self):
        self.cost = 0.0

    def add(self, usage) -> None:
        self.cost += (usage.prompt_tokens * PRICE_IN
                      + usage.completion_tokens * PRICE_OUT) / 1_000_000

    def over_cap(self) -> bool:
        return self.cost >= COST_CAP_USD


OUTPUT_DIR = Path(__file__).parent / "run-output"
BUILD_LOG = OUTPUT_DIR / "build-log.jsonl"

# The three exits from the Loop Spec, section 3. SUCCESS and ESCALATE both land in my
# review queue (an escalate is a decision request); STUCK goes to a build log, because
# it means Cortex failed mechanically, which is a bug for me to fix, not a call to make.
OUTCOMES = {
    "success": "FINAL STATUS UPDATE (draft, all gates passed, NOT posted)",
    "escalate": "ESCALATED, decision request for a human (draft held, NOT posted)",
    "stuck": "STUCK, halted and logged as a build problem (nothing for me to decide)",
}


def banner(text: str) -> None:
    print(f"\n{'=' * 64}\n{text}\n{'=' * 64}")


def subject_project(brief: str) -> str | None:
    """The project this run is ABOUT, read from the task brief.

    Deliberately not inferred from which tools the agent happened to call: when a project
    didn't exist, Cortex swept get_project/get_activity across every other project while
    hunting for it, and the last successful call won. That mislabelled a build-log entry
    and, worse, keyed the output file to a project the run was never about, overwriting a
    good draft. The brief is the only authoritative source of the subject.
    """
    match = re.search(r"\bP-[A-Z][A-Z0-9]+\b", brief)
    return match.group(0) if match else None


def run_key(which: str, project_id: str | None) -> str:
    """Idempotency key from the Loop Spec, section 1. A cron run keys on project + ISO
    week, so firing twice in the same week UPDATES that week's draft in place instead of
    creating a second one. Falls back to the fixture name when no project resolved.
    """
    if project_id:
        year, week, _ = date.today().isocalendar()
        return f"{project_id}-{year}-W{week:02d}"
    return f"task-{which}"


def emit_deliverable(which: str, draft: str, *, outcome: str, reason: str, cost: float,
                     project_id: str | None = None, notes=None) -> None:
    """Surface AND persist the run's exit so it can't get lost in the scroll-back.

    Every exit produces a DRAFT held for human review, never a post, there is no publish
    tool. The three outcomes go to different places on purpose (see OUTCOMES above).
    """
    banner(OUTCOMES[outcome])
    if draft.strip():
        print(draft.rstrip())
    else:
        print("(Cortex stopped before it produced a draft, nothing to show.)")
    if outcome != "success":
        print(f"\nWhy: {reason}")
    if notes:
        print("\nCritic findings (the 5 rules code cannot check; rule 3 escalates, "
              "1/2/4/5 revise):")
        for note in notes:
            print(f"  - {note}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    key = run_key(which, project_id)

    if outcome == "stuck":
        with BUILD_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"run_key": key, "fixture": which,
                                     "outcome": outcome, "reason": reason,
                                     "cost_usd": round(cost, 4)}) + "\n")
        print(f"\nLogged build problem -> {BUILD_LOG.relative_to(Path(__file__).parent)}"
              "  (no decision needed from me, go look at the code)")

    if draft.strip():
        out = OUTPUT_DIR / f"{key}.md"
        existed = out.exists()
        state = {"success": "all gates passed, queued for review",
                 "escalate": "HELD, escalated as a decision request",
                 "stuck": "HELD, run halted as STUCK"}[outcome]
        header = [f"<!-- Cortex draft, {state}; NOT posted. Run cost ~ ${cost:.4f}. -->",
                  f"<!-- run key: {key} -->",
                  f"<!-- {reason} -->"]
        if notes:
            header.append("<!-- critic findings: "
                          + " | ".join(str(n) for n in notes) + " -->")
        out.write_text("\n".join(header) + f"\n\n{draft.rstrip()}\n", encoding="utf-8")
        print(f"\n{'Updated existing' if existed else 'Saved new'} draft for run key "
              f"{key} -> {out.relative_to(Path(__file__).parent)}  "
              "(for your review, nothing was posted)")


def run(which: str = "happy") -> None:
    client = OpenAI()
    bounds = Bounds()
    task = tools.get_task(which)
    if "error" in task:
        print(task)
        return

    banner(f"CORTEX RUN, fixture: task-{which}  (auto-queue cap {MAX_QUEUE_ITEMS} items)")
    print(task["body"])

    messages = [
        {"role": "system", "content": CORTEX_SYSTEM},
        {"role": "user", "content": f"PM task brief:\n\n{task['body']}"},
    ]
    source_log: list[str] = [task["body"]]
    revisions = 0
    last_draft = ""
    project_id: str | None = subject_project(task["body"])
    tool_errors = 0
    print(f"\nSubject project (from the brief): {project_id or 'none named'}")

    for step in range(1, MAX_ITERATIONS + 1):
        if bounds.over_cap():
            reason = f"cost cap ${COST_CAP_USD} hit at ${bounds.cost:.4f}"
            banner(f"BOUND TRIPPED, {reason}. Halting as STUCK.")
            emit_deliverable(which, last_draft, outcome="stuck", reason=reason,
                             cost=bounds.cost, project_id=project_id)
            return

        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOL_SCHEMAS)
        bounds.add(resp.usage)
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                fn = call.function.name
                args = json.loads(call.function.arguments or "{}")
                result = tools.TOOLS[fn](**args)
                source_log.append(f"{fn}({args}) -> {json.dumps(result)}")
                print(f"\n[step {step}] TOOL {fn}({args})")
                print(f"          -> {json.dumps(result)[:300]}")
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result)})
                # Count broken reads. A rejected cap is NOT an error, it's a bound
                # working as designed. (The subject project comes from the brief, not
                # from here, see subject_project().)
                if isinstance(result, dict) and "error" in result:
                    tool_errors += 1

            if tool_errors >= 3:
                reason = (f"a tool returned an error {tool_errors}x; the data cannot be "
                          "pulled, so this is a broken pipe, not a judgement call")
                banner(f"STUCK, {reason}. Halting and logging as a build problem.")
                emit_deliverable(which, last_draft, outcome="stuck", reason=reason,
                                 cost=bounds.cost, project_id=project_id)
                return
            continue

        # No tool calls => Cortex produced a proposed output. Gate it.
        proposed = msg.content or ""
        last_draft = proposed
        print(f"\n[step {step}] PROPOSED OUTPUT:\n{proposed}")

        # Cortex declining is a valid end state, but WHICH exit depends on why: a broken
        # read is my bug (stuck), a call above the agent line is my decision (escalate).
        # Search anywhere, not just position zero: Cortex often explains itself first and
        # puts ESCALATE: on the last line. Matching only the start let one such run fall
        # through to the gates and exit SUCCESS on a message that was a refusal.
        if re.search(r"^\s*ESCALATE\b", proposed, re.I | re.M):
            outcome = "stuck" if tool_errors else "escalate"
            reason = ("Cortex escalated after a failed read, so the pipe is the problem"
                      if tool_errors else "Cortex escalated a call that sits above the agent line")
            banner(f"{outcome.upper()}, {reason}. Run cost ≈ ${bounds.cost:.4f}")
            emit_deliverable(which, proposed, outcome=outcome, reason=reason,
                             cost=bounds.cost, project_id=project_id)
            return

        # Tier 1: the deterministic gates. No model call, so they're free and they're
        # facts, not opinions. These are what "done" means (Loop Spec section 2).
        banner("DETERMINISTIC GATES (enforced in code, outside the model)")
        results = gates.check_all(proposed, project_id, "\n".join(source_log))
        for result in results:
            print(f"  [{'PASS' if result['ok'] else 'FAIL'}] {result['gate']}: "
                  f"{result['reason']}")
        failures = [r for r in results if not r["ok"]]
        above_line = [r for r in failures if r["agent_line"]]

        if above_line:
            reason = "above-the-line gate(s) failed: " + "; ".join(
                f"{r['gate']} ({r['reason']})" for r in above_line)
            banner(f"ESCALATE, {reason}. A human owns this call, no retry. "
                   f"Run cost ≈ ${bounds.cost:.4f}")
            emit_deliverable(which, proposed, outcome="escalate", reason=reason,
                             cost=bounds.cost, project_id=project_id)
            return

        if failures:
            if revisions >= MAX_REVISIONS:
                reason = (f"fixable gate(s) still failing after {MAX_REVISIONS} "
                          "revisions: " + ", ".join(r["gate"] for r in failures))
                banner(f"STUCK, {reason}. Halting and logging as a build problem. "
                       f"Run cost ≈ ${bounds.cost:.4f}")
                emit_deliverable(which, proposed, outcome="stuck", reason=reason,
                                 cost=bounds.cost, project_id=project_id)
                return
            revisions += 1
            print(f"\n-> gates failed; revision {revisions}/{MAX_REVISIONS} "
                  "(enough rope to self-correct, not enough to spiral)")
            messages.append(msg)
            messages.append({"role": "user", "content":
                             "These deterministic gates failed: "
                             + "; ".join(f"{r['gate']}: {r['reason']}" for r in failures)
                             + ". Fix the draft. Do not argue with the gates, they are "
                               "enforced outside you."})
            continue

        # Tier 2: the independent critic. It checks the five things code cannot (M3
        # Field 5). Its verdict is REPORTED here and routed by the loop, the critic never
        # decides the consequence, that's what let it escalate a correct Green in M2.
        banner("CRITIC, independent validator (the 5 rules code cannot check)")
        verdict = review(client, MODEL, proposed, "\n".join(source_log))
        # Estimate critic spend too.
        bounds.cost += (verdict["_usage"]["prompt"] * PRICE_IN
                        + verdict["_usage"]["completion"] * PRICE_OUT) / 1_000_000
        print(json.dumps({k: v for k, v in verdict.items() if k != "_usage"}, indent=2))

        critic_reasons = list(verdict.get("reasons") or [])
        failed_rules = [int(n) for n in (verdict.get("failed_rules") or [])
                        if str(n).isdigit()]

        if verdict.get("verdict") == "fail":
            if 3 in failed_rules:            # commitment is above my agent line (M1)
                reason = ("critic rule 3, soft commitment on a launch the roadmap marks "
                          "unconfirmed: " + "; ".join(critic_reasons))
                banner(f"ESCALATE, {reason} A human owns commitment, no retry. "
                       f"Run cost ≈ ${bounds.cost:.4f}")
                emit_deliverable(which, proposed, outcome="escalate", reason=reason,
                                 cost=bounds.cost, project_id=project_id,
                                 notes=critic_reasons)
                return
            if revisions >= MAX_REVISIONS:   # shared counter with the gates, cap 2
                reason = (f"critic rule(s) {failed_rules or 'unspecified'} still failing "
                          f"after {MAX_REVISIONS} revisions: " + "; ".join(critic_reasons))
                banner(f"ESCALATE, {reason} Gate state and critic reasons attached. "
                       f"Run cost ≈ ${bounds.cost:.4f}")
                emit_deliverable(which, proposed, outcome="escalate", reason=reason,
                                 cost=bounds.cost, project_id=project_id,
                                 notes=critic_reasons)
                return
            revisions += 1
            print(f"\n-> critic failed rule(s) {failed_rules or 'unspecified'}; revision "
                  f"{revisions}/{MAX_REVISIONS} (shared counter with the gates)")
            messages.append(msg)
            messages.append({"role": "user", "content":
                             "An independent reviewer failed your draft: "
                             + "; ".join(critic_reasons)
                             + ". Fix exactly those points. Do not re-argue the "
                               "deterministic gates, they already passed."})
            continue

        notes = critic_reasons or ["critic had no objections"]

        banner(f"HITL CHECKPOINT, status update + any proposed stories queued for "
               f"your review. Nothing posted, no commitments made. "
               f"Run cost ≈ ${bounds.cost:.4f}")
        emit_deliverable(which, proposed, outcome="success",
                         reason="all deterministic gates passed",
                         cost=bounds.cost, project_id=project_id, notes=notes)
        return

    banner(f"MAX ITERATIONS ({MAX_ITERATIONS}) reached without finishing. "
           f"Halting as STUCK. Run cost ≈ ${bounds.cost:.4f}")
    emit_deliverable(which, last_draft, outcome="stuck",
                     reason=f"max iterations ({MAX_ITERATIONS}) reached",
                     cost=bounds.cost, project_id=project_id)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "happy")
