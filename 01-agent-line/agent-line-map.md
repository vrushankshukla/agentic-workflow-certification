# Agent Line Map: Cortex PM Chief-of-Staff Agent

> Module 1 · The Agent Line
>
> ✅ **What this validates:** every risky action has a clear owner, by the end you'll have proven an above/below-the-line map with HITL checkpoints, scored on reversibility, blast radius, and measurability.

## The workflow, decision by decision

List every discrete decision or action in your agent's workflow, then score each one and place it **above** the line (a human owns it) or **below** (the agent owns it). Borderline calls get an HITL checkpoint.

| Decision / action | Reversibility (H/M/L) | Blast radius (H/M/L) | Measurability (H/M/L) | Above / Below | HITL? |
|---|---|---|---|---|---|
| Pull project state + activity | H | L | H | Below | · |
| Decide relevant context | H | L | M | Below | · |
| Draft the update | H | L | H | Below | · |
| Decide tone / commitment level | M | M | M | Below | required |
| Flag at-risk / escalation | H | M | H | Below | required |
| Choose what to escalate | M | H | L | Above | required |
| Propose a story batch (capped) | H | L | H | Below | · |
| Post an update / approve a company-wide one | L | H | L | Above | required |

## Agent anatomy (sketch)

- **Model:** `gpt-4o-mini` as the default fast model for drafting and tool-calling; escalate to a frontier model only when the critic keeps rejecting on nuanced judgment (e.g. contested Green/Yellow/Red calls) or when a company-wide-facing draft needs stronger reasoning — the cost cap ($0.50/run) keeps that safe to try.
- **Tools:** `get_project` + `get_activity` (read) · `search_past_updates` (format matching) · `get_roadmap` (confidential-aware) · `get_team_norms` · story proposal (capped). **No publish tool — by design.**
- **Memory:** persists across runs — roadmap, team norms, past-update format, decision log; purged / not-persisted — the raw draft text of each run (held in `run-output/`, reviewed then discarded).
- **Loop:** _placeholder, defined in M2 loop-spec.md_
- **Bounds:** _placeholder, defined in M5 bounds-and-evals.md_
- **Evals:** _placeholder, defined in M5 bounds-and-evals.md_

## The golden rule, applied

- **Pull project state + activity** sits below the line because it's easy to reverse, has a low blast radius, and is highly verifiable — deciding factor: all three green (read-only).
- **Decide relevant context** sits below the line because it's easy to reverse, has a low blast radius, and is medium to verify — deciding factor: reversibility (a human reviews the draft downstream).
- **Draft the update** sits below the line because it's easy to reverse, has a low blast radius, and is highly verifiable — deciding factor: reversibility (text only, nothing sent).
- **Decide tone / commitment level** sits below the line with HITL because it's medium to reverse, has a medium blast radius, and is medium to verify — deciding factor: blast radius (over-promising is hard to walk back, so a human approves).
- **Flag at-risk / escalation** sits below the line with HITL because it's easy to reverse, has a medium blast radius, and is highly verifiable — deciding factor: blast radius (safe to raise, but a human confirms the call).
- **Choose what to escalate** sits above the line because it's medium to reverse, has a high blast radius, and is low to verify — deciding factor: measurability (you can't see what was withheld).
- **Propose a story batch (capped)** sits below the line because it's easy to reverse, has a low blast radius, and is highly verifiable — deciding factor: reversibility (proposed + capped, human approves).
- **Post an update / approve a company-wide one** sits above the line because it's hard to reverse, has a high blast radius, and is low to verify — deciding factor: reversibility (irreversible publish, no tool by design).

## Hardest call

**"Choose what to escalate" (#6).** On the surface this felt like an easy *above* — but I went back and forth because escalation is mostly Cortex judging what's *not* worth raising, and that's a decision I couldn't check after the fact. The axis that settled it was **measurability**: raising a false flag is cheap and visible, but a real issue that Cortex silently decides isn't escalation-worthy leaves no trace — nobody sees what was withheld. Low measurability on a high-blast-radius action means a human has to own the final escalation list. Capability is not permission: even if Cortex picks well most of the time, the one silent omission is the one that hurts.
