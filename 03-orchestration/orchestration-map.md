# Orchestration Map: Cortex PM Chief-of-Staff Agent

> Module 3 · Orchestration & Subagents, ★ Deliverable 3
>
> ✅ **What this validates:** nothing advances unchecked, by the end you'll have proven a justified topology, a roster, and a validator with a defined fail action.
>
> Builds on your M2 Loop Spec. Only split one agent into a team when there's a real reason, coordination has a cost.

## 1. Why split? (or why not)

**Verdict: split, for exactly one reason — independent validation. The other three don't apply.**

Cortex today is a single goal-loop agent: cron-triggered Monday 07:00 ET, pulls one
project's activity, drafts the weekly update plus a story batch, runs it against seven
deterministic gates, and stops at my review checkpoint. No publish tool.

| Reason | Applies? | Why / why not |
|---|---|---|
| Separation of concerns | **No** | Pulling activity, drafting, and calling status are one coherent job over one project's context. Splitting them adds hand-offs, not clarity. |
| Parallelism | **No** | One run = one project = one draft. Nothing to fan out, no wall-clock saved. |
| **Independent validator** | **Yes** | Cortex cannot grade its own draft. Self-review re-runs the same context that produced the error, so it confirms rather than catches. |
| Context-window pressure | **No** | One project's activity + norms + last week's update fits comfortably. The §4 isolation in my Loop Spec is about leakage, not window size. |

**Why the validator reason is real, not theoretical:** in an M2 run the agent exited SUCCESS
on a message that was a refusal, not an update — every content gate passed *vacuously* on
missing content, because the drafter can't see what isn't there. That's the blind-spot
failure mode: the reader has to be someone who never watched the draft get written. My Loop
Spec §2 already concedes this ("a separate model call that never sees itself as the author")
and §5 parks it as M3 work. This module formalises it — and fixes the flip side I also hit
live: an over-strict critic that escalated a *correct* Green by inventing a rule the team
norms don't contain.

## 2. Topology

**Pattern: `single + subagents`** — one orchestrating agent (Cortex) plus exactly one
validating subagent. No fan-out, because nothing in Field 1 justified one.

```
[PM task brief]
      │
      ▼
[Cortex, M2 goal loop]  pulls project · activity · roadmap · norms · past updates
      │  drafts update + story batch
      ▼
[7 deterministic gates, in code, outside the model]  ──fail 3/5/6──► [ESCALATE, no retry]
      │ pass                                          ──fail 0/1/2/4─► revise ──┐
      ▼                                                                         │
[Critic subagent, independent context]                                          │
      │                                                                         │
      ├── fail rule 3 (soft commitment, roadmap unconfirmed) ──► [ESCALATE, no retry]
      ├── fail rules 1/2/4/5 ──► revise, back to Cortex ───────────────────────┤
      │                                        shared counter, max 2 ──────────┘
      │                                        exhausted ──► [ESCALATE with gate state + critic reasons]
      ▼ pass
[PM review checkpoint]  ──► queued for me.  Nothing posted. No publish tool.
```

## 3. Roster

| Agent / subagent | Responsibility | Runs which Loop Spec |
|---|---|---|
| **Cortex** (chief-of-staff) | Pulls project context, drafts the update + story batch, revises on failure | M2 goal loop (`00-build/agent.py`) |
| **Deterministic gates** (not an agent — code) | Blocking rule layer; runs before the critic ever sees the draft | No model call; M2 §2 |
| **Critic** (validator subagent) | Judges the 5 things code can't; returns verdict + failing rule + quoted line + reasons | Validation pass, single stateless call (`00-build/critic.py`) |

The gates are listed even though they aren't an agent. Leaving them out would imply the critic
is the only check, which understates the design: the blocking layer is code, the critic is judgment.

## 4. Communication & hand-offs

**Plain in-process function call. No MCP, no A2A** — noted deliberately, not omitted. One
orchestrator and one subagent in the same process need no transport; adding a protocol here
would be coordination cost with nothing bought. (If the critic ever moved out-of-process, or a
second consumer needed its verdicts, that's when a protocol earns its place.)

| Direction | What passes | Form |
|---|---|---|
| Cortex → critic | the draft text, and the source data Cortex pulled | two arguments to `review()` — nothing else |
| Critic → Cortex | pass/fail, the failing rule number, the offending line quoted, reasons | structured verdict |

**Routing is the orchestrator's job, not the critic's.** The critic reports a verdict; the loop
decides revise vs. escalate vs. advance. A critic that also decided the consequence would be
able to escalate on its own judgment — which is exactly the M2 failure where it escalated a
correct Green.

## 5. The validator

**Role:** one subagent, an independent critic. It reviews a draft it did not write, and it
checks what code cannot. The seven deterministic gates (M2 §2) stay the blocking layer and
run *before* the critic ever sees the draft — the critic does not re-litigate them. That
division is the fix for a real M3 starting condition: the shipped critic spent a model call
restating gates that had already passed, which is how it ended up inventing a stricter rule
than the team norms contain and escalating a correct Green.

**What the critic checks (5 rules, all checkable, none coded):**

| # | Check | Why code can't do it |
|---|---|---|
| 1 | **Sentence-level grounding** — every figure and ID is attached to the claim it actually supports | The gate checks a number *appears* in pulled data; it can't see a real number bolted to the wrong claim |
| 2 | **Colour justified on the page** — the update cites the evidence for its Green/Yellow/Red, not just asserts a legal colour | The gate checks the colour is *permitted*; it can't check it was *argued* |
| 3 | **No soft commitment** — "on track for Q1," "should ship next sprint" — **and only when the roadmap marks that launch unconfirmed** | The gate matches dates; soft commitment has no date to match. The roadmap condition keeps this tied to data, not to taste |
| 4 | **Each proposed story names its in-scope PRD item** | The gate checks scope is not *violated*; it can't require traceability be *stated* |
| 5 | **Answers the brief** — the draft addresses what was actually asked | The hard version of my M2 vacuous-pass bug: a refusal passed every content gate because there was no bad content to find |

**Fail-action, tiered — same vocabulary as my M2 gates, deliberately:**

| Failed rule | Action |
|---|---|
| 1, 2, 4, 5 | **Revise** — bounce back to Cortex with the failing rule and the offending line quoted. Drafting errors; Cortex has the data to fix them. |
| 3 | **Escalate to me, no retry** — commitment is above the agent line on my M1 map. Letting Cortex re-word its way past it is the workaround I don't want. |
| any | **Log** as well, so I can see what the critic caught even on drafts that passed on retry. |

**Revision cap: 2 — shared with the gate-revision counter, not a second budget.**
Two bounces per run from any cause, then escalate to me with the gate state *and* the critic's
reasons attached. Same number already in `00-build/agent.py` (`MAX_REVISIONS = 2`): enough rope
to self-correct, not enough to spiral. One counter means one number to enforce as a bound in M5,
instead of a 2 × N worst case I'd have to reason about.

**Pass-action:** a passing draft advances to my **PM review checkpoint** with the critic's
judgment notes attached. It is not sent, posted, or queued to anyone else. There is no publish tool.

## 6. State: shared vs isolated

Carried from M2 §4 (per-project isolation + a small global layer), extended to the fleet.

| Scope | What | Why |
|---|---|---|
| **Shared, Cortex → critic** | the source data Cortex pulled, and the draft | The critic can't check grounding or PRD traceability against data it doesn't have (rules 1 and 4 would be unverifiable) |
| **Isolated, never crosses** | Cortex's reasoning transcript | Seeing *why* Cortex wrote it is precisely how the critic would inherit Cortex's blind spot — which would collapse the Field 1 argument for having a critic at all |
| **Isolated, one-way** | the critic's own reasoning | Only the structured verdict returns to Cortex (failing rule + quoted line + reason). The critic's deliberation never becomes Cortex's context |
| **Per-project (from M2)** | activity history, last week's update, decision log | A Northstar run loads only Northstar state. Structural, not a filter — the fixtures include an embargoed project (Orbit) and one under `launch_hold` (Vega) |
| **Global (safe by construction)** | team norms, past-update format, the run-key ledger | No project-specific content |
| **Never persisted** | the draft text, and the critic's notes | Both land in `run-output/` as my review queue and are discarded once I've read them |

**Already true in code, not aspirational:** `00-build/critic.py:13` — `review(client, model,
proposed_output, source_data)` builds a fresh `messages` array with its own system prompt and
receives only those two arguments. Independence is enforced by the call signature, not by a
promise in a prompt.

## 7. Cost & latency budget

Measured from my own runs, not estimated.

| | Single agent (gates only) | With the critic |
|---|---|---|
| Model calls per validation pass | 0 (gates are code, free) | **+1** |
| Worst case at the cap | 3 drafting passes | 3 drafting passes **+ 3 critic calls** |
| Measured marginal cost | — | **~$0.0005 per critic pass** |
| Added latency | 0 | **+1 sequential round-trip per pass** (~2–4s each; ~15–30s worst case) |

The critic cannot run in parallel — it needs a finished draft — so its latency is strictly
additive, not hidden.

**Actual run costs to date:** happy path $0.0026 · missing-data (stuck) $0.0014 · jailbreak
(escalate) $0.0048 · this M3 soft-commitment run (escalate on rule 3) $0.0011. Against a
`COST_CAP_USD` of $0.50, every run sits at **0.2–1% of the cap**.

**The honest conclusion: coordination is nearly free here, and that's a consequence of the
trigger I chose in M2.** A Monday 07:00 ET cron ahead of a VP sync has hours of slack, so
30 seconds of added latency costs nothing; at 1% of the cap, the tokens cost nothing either.
I am not going to pretend a $0.0005 line item is a budget problem.

**→ M5:** the scarce resource is **my attention**, not tokens. Every escalation buys a human
interrupt, and my fail-action sends rule-3 failures straight to me with no retry — so the
bound worth enforcing in M5 is the **escalation rate** (how many of N runs reach me as a
decision request), not the dollar cost. A critic that escalates 80% of runs is a failure even
at $0.001 a run. That is the M2 over-strictness bug restated as a measurable bound.
