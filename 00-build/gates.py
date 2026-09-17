"""Deterministic done-gates for Cortex (M2 Loop Spec, section 2: "two-tier done").

These are the CHECKABLE half of "done": plain Python, no model call, so passing them
is a fact rather than an opinion. They are enforced OUTSIDE the model, the same way
the cost cap and the queue cap already are. The critic's judgment (tone, emphasis,
framing) runs afterwards and is ADVISORY, it cannot block a run.

Why the split: in a real run the critic failed a *correct* Green update by inventing a
stricter rule than team-norms.md contains (the norms bar Green only on an open Sev-1 or
a launch_hold flag; the open issue was severity "normal"). An over-strict judge burns
human attention as surely as a missing one. Rules live here, taste lives in the critic.

Each gate returns (ok, reason). Gates named in AGENT_LINE_GATES are above-the-line
violations from the M1 agent-line map: they ESCALATE immediately with no retry, because
retrying would just be the agent arguing with the line. The rest are fixable, they
consume the revision budget and then halt as STUCK.

Known limit (stated in the spec): "does this story genuinely serve an in-scope PRD item"
is prose judgement and is NOT mechanically checkable. What is checkable is the
out-of-scope half, the PRD names those explicitly, so that is the gate. The in-scope
question is left to the critic's advisory notes.
"""

from __future__ import annotations

import json
import re

import tools

# Above-the-line failures: escalate to a human immediately, do not spend a retry.
AGENT_LINE_GATES = {"confidentiality", "no_commitment", "story_cap"}

STATUS_RE = re.compile(r"status\W{0,40}?\b(green|yellow|red)\b", re.I)
DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|Q[1-4]\b"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}"
    r"|(?:January|February|March|April|June|July|August|September|October"
    r"|November|December)\b)", re.I)


def _all_projects() -> dict:
    """Read the project store directly. Read-only, adds no capability to the agent."""
    return json.loads((tools.FIXTURES / "projects.json").read_text())


def _short_name(project: dict) -> str:
    """"Northstar (self-serve onboarding)" -> "Northstar"."""
    return project.get("name", "").split(" ")[0]


def _roadmap_sections() -> dict[str, str]:
    """Split roadmap.md into {heading: body} so a lookup can't read across projects.

    The first version matched "<project>.{0,400}unconfirmed" over the whole file. That
    character window spilled out of the Northstar section into Vega's, where the word
    "unconfirmed" lives, and escalated a perfectly good Northstar update. A false
    ESCALATE from a deterministic gate is the same disease as an over-strict critic.
    """
    sections: dict[str, str] = {}
    heading = None
    for line in (tools.FIXTURES / "roadmap.md").read_text().splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            sections[heading] = ""
        elif heading is not None:
            sections[heading] += line + "\n"
    return sections


def gate_is_update(draft: str, project_id: str, source_log: str):
    """The draft must actually BE a status update.

    Added after a real run exposed the hole: every other gate looks for bad *content*,
    so all of them passed vacuously on a message that contained no update at all, and the
    run exited SUCCESS on nothing. Absence needs its own gate.
    """
    if not STATUS_RE.search(draft):
        return False, "no colour status asserted, so this is not a status update"
    if project_id:
        project = tools.get_project(project_id)
        name = _short_name(project) if "error" not in project else ""
        named = project_id.lower() in draft.lower() or (
            bool(name) and bool(re.search(rf"\b{re.escape(name)}\b", draft, re.I)))
        if not named:
            return False, f"never names the subject project ({project_id})"
    return True, "asserts a colour status and names the subject project"


def gate_grounded(draft: str, project_id: str, source_log: str):
    """Every issue/PR ID and every metric in the draft must appear in pulled data."""
    claims = set(re.findall(r"#\d+", draft)) | set(re.findall(r"\d+%", draft))
    missing = sorted(c for c in claims if c not in source_log)
    if missing:
        return False, ("ungrounded claim(s) that appear nowhere in the pulled data: "
                       + ", ".join(missing))
    return True, f"all {len(claims)} ID(s)/metric(s) trace to pulled data"


def gate_status_call(draft: str, project_id: str, source_log: str):
    """Green is barred ONLY by an open Sev-1 or a launch_hold flag (team-norms.md)."""
    match = STATUS_RE.search(draft)
    if not match:
        return True, "no colour status asserted"
    colour = match.group(1).lower()
    if colour != "green":
        return True, f"asserts {colour}; a more conservative call is always allowed"
    if not project_id:
        return False, "asserts Green but no project was resolved, so it cannot be checked"
    project = tools.get_project(project_id)
    if "error" in project:
        return False, f"asserts Green but the project could not be read ({project['error']})"
    if "launch_hold" in (project.get("flags") or []):
        return False, "asserts Green but the project carries a launch_hold flag"
    activity = tools.get_activity(project_id).get("activity", [])
    sev1 = [a for a in activity
            if a.get("type") == "issue_open"
            and str(a.get("severity", "")).lower().replace("_", "-") in {"sev-1", "sev1"}]
    if sev1:
        return False, f"asserts Green but a Sev-1 is open: {sev1[0].get('id')}"
    return True, "Green is permitted: no open Sev-1 and no launch_hold (norms rule)"


def gate_story_cap(draft: str, project_id: str, source_log: str):
    """The queue cap is enforced by tools.propose_stories; this catches the aftermath."""
    if "batch_exceeds_queue_cap" in source_log:
        return False, ("story batch exceeded the queue cap; norms say escalate to sprint "
                       "planning, do not split the batch to dodge the cap")
    return True, "no story batch over the queue cap"


def gate_out_of_scope(draft: str, project_id: str, source_log: str):
    """No proposed work may touch something the PRD marks out of scope."""
    if not project_id:
        return True, "no project resolved, nothing to scope-check"
    project = tools.get_project(project_id)
    summary = project.get("prd_summary", "")
    match = re.search(r"out of scope:\s*(.+?)(?:\.|$)", summary, re.I)
    if not match:
        return True, "the PRD lists no out-of-scope items"
    terms = [t.strip().lower() for t in re.split(r",|\band\b", match.group(1)) if t.strip()]
    hits = [t for t in terms if t in draft.lower()]
    if hits:
        return False, "draft touches PRD out-of-scope item(s): " + ", ".join(hits)
    return True, f"clear of {len(terms)} out-of-scope item(s)"


def gate_confidentiality(draft: str, project_id: str, source_log: str):
    """No CONFIDENTIAL/embargoed project may be named in a shareable update."""
    subject = (project_id or "").strip().upper()
    leaks = []
    for pid, project in _all_projects().items():
        if pid == subject or "confidential" not in (project.get("flags") or []):
            continue
        name = _short_name(project)
        if (name and re.search(rf"\b{re.escape(name)}\b", draft, re.I)) \
                or pid.lower() in draft.lower():
            leaks.append(f"{name} ({pid})")
    if leaks:
        return False, "names a CONFIDENTIAL/embargoed project: " + ", ".join(leaks)
    return True, "no confidential project named"


def gate_no_commitment(draft: str, project_id: str, source_log: str):
    """No date on a launch the roadmap or the project flags mark as gated."""
    sections = _roadmap_sections()
    committed = []
    for project in _all_projects().values():
        name = _short_name(project)
        if not name:
            continue
        # Only this project's own roadmap section may mark it gated.
        own = "\n".join(body for heading, body in sections.items()
                        if re.search(rf"\b{re.escape(name)}\b", heading, re.I))
        gated = "launch_hold" in (project.get("flags") or []) or "unconfirmed" in own.lower()
        if not gated or not re.search(rf"\b{re.escape(name)}\b", draft, re.I):
            continue
        # A date in the same paragraph as a gated project reads as a commitment.
        for para in re.split(r"\n\s*\n", draft):
            if re.search(rf"\b{re.escape(name)}\b", para, re.I) and DATE_RE.search(para):
                committed.append(name)
                break
    if committed:
        return False, "commits or implies a date on a gated launch: " + ", ".join(committed)
    return True, "no date committed on a gated launch"


ALL_GATES = [
    ("is_update", gate_is_update),
    ("grounded", gate_grounded),
    ("status_call", gate_status_call),
    ("story_cap", gate_story_cap),
    ("out_of_scope", gate_out_of_scope),
    ("confidentiality", gate_confidentiality),
    ("no_commitment", gate_no_commitment),
]


def check_all(draft: str, project_id: str, source_log: str) -> list[dict]:
    """Run every gate. Returns one result dict per gate, in spec order."""
    results = []
    for name, fn in ALL_GATES:
        try:
            ok, reason = fn(draft, project_id, source_log)
        except Exception as exc:  # a broken gate must fail loudly, never pass silently
            ok, reason = False, f"gate raised {type(exc).__name__}: {exc}"
        results.append({"gate": name, "ok": ok, "reason": reason,
                        "agent_line": name in AGENT_LINE_GATES})
    return results
