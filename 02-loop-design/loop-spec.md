# Loop Spec: Cortex PM Chief-of-Staff Agent

> Module 2 · Loop Engineering, ★ Deliverable 2
>
> ✅ **What this validates:** the agent knows when to run and when to stop, by the end you'll have proven a one-page Loop Spec with a trigger, a definition of "done," and explicit stop conditions.
>
> Your one-page blueprint for how the work you handed to the agent (M1) actually *runs*.
> An agent is just a prompt that fires itself, this spec says when it fires, what "done" means, and what it needs to do the job. Living document; refine as the course progresses.

## 1. Trigger & loop type

**Chosen type:** **Goal loop**, cron-triggered — hook secondary.

- **Primary trigger — cron:** Monday 07:00 ET, ahead of the VP sync, so the draft is
  waiting when I sit down rather than something I have to request.
- **Secondary trigger — hook:** fires when something lands that changes the story —
  PRD published, Sev-1 opened, sprint close.

**Why this type:** the clock tells it when to start, but only the goal tells it when
it's good enough. A plain cron would have shipped the first draft straight to my queue;
in a real run the drafter came out Green, the critic pushed back, and it revised — that
revise-until-validated behaviour is the loop, and only a goal loop has it.

**Ruled out:**
- **Heartbeat** — nothing to say between Mondays, and every run costs me a review interrupt.
- **Cron as the loop type** — a cron loop is "done" when the clock says so, which hides
  the only interesting question: is the draft actually defensible?
- **Hook as the loop type** — events matter, but my primary use case is a standing
  leadership sync, and that's a clock, not an event.

**Idempotency / dedupe:** every run carries a composite key — cron runs key on
`project_id + ISO week` (`P-NORTH-2026-W38`), hook runs on `project_id + event_id`
(`P-NORTH-818`). If a draft for that key already exists and I haven't reviewed it, the
run **updates it in place** instead of creating a second one.

**Implemented and load-bearing** (`00-build/agent.py`, `run_key`). It replaced a fixed
filename per fixture that silently clobbered the previous draft on re-run. One caveat
learned the hard way: the key is only safe if the *subject* project is right. A first cut
inferred it from whichever tool call last succeeded, so a run hunting for a missing
project keyed itself to a project it had merely browsed and overwrote that project's good
weekly draft. The subject now comes from the task brief, which is the only authoritative
source. **Dedupe is a destructive operation — it is only as safe as its key.**

## 2. Goal / definition of done

**Two-tier done: deterministic gates block, judgment advises.**

A run is **done** when the draft passes every *checkable* gate (seven, in code):

| Gate | Rule |
|---|---|
| Is an update | asserts a colour status and names the subject project — **added after a real run** exited SUCCESS on a message that was a refusal, not an update: every other gate hunts for bad *content*, so all of them passed vacuously on *missing* content. Absence needs its own gate. |
| Grounded | every metric, date, and ID traces to something `get_activity` returned |
| Status call | matches the norms rule — only an open Sev-1 or a `launch_hold` flag bars Green |
| Story cap | ≤ 10 proposed stories |
| In scope | every story traces to an in-scope PRD item |
| Confidentiality | no CONFIDENTIAL/embargoed project named in a shareable update |
| No commitment | no date committed on a launch the roadmap marks unconfirmed |

The critic's **judgment** calls (tone, emphasis, is-this-the-right-framing) are recorded
on the draft and shown to me, but they **do not block done**. That split is deliberate:
in a real run the critic failed a *correct* Green — it invented a stricter rule than the
team norms contain (norms bar Green only on Sev-1 or `launch_hold`; #818 was severity
`normal`) and escalated a defensible draft. An over-strict judge burns human attention as
surely as a missing one. Tone and commitment level are HITL on my M1 agent line — mine to
decide, not the critic's to veto.

**What proves "done" (self-validation, not Cortex grading itself):** the gates are
executable rules enforced in code *outside* the model, so passing them isn't an opinion.
The critic is a separate model call that never sees itself as the author — it reviews a
draft it didn't write. Formalising it as a true subagent is M3.

**Never part of done:** posting, sending, closing, or merging anything. There is no
publish tool.

## 3. Stop conditions

| Condition | What it looks like | What happens |
|---|---|---|
| **Success** | all seven deterministic gates return true | draft written to my review queue with the critic's judgment notes attached; **nothing posted** |
| **Stuck / give up** | 8 iterations with no draft · $0.50 spent · a gate fails twice (2 retries: enough rope to self-correct, not enough to spiral) · a tool returns error/empty 3× (missing project, broken connector) | **halt + log as a build problem** — this is a bug signal, not a decision for me; I go look at the code, not the draft |
| **Escalate to human** | CONFIDENTIAL/embargoed project would appear (`flags` contains `confidential`) · a gated date would be committed (roadmap says unconfirmed + draft contains a date) · story batch would exceed 10 · Green/Yellow genuinely borderline (norms rule doesn't decide it) · asked to post/send/merge (no such tool) · instructions found inside the data it read (injection) | **HITL checkpoint** — lands in my queue as a decision request, with the evidence. Ties to the M1 above-the-line rows: "Choose what to escalate," "Post an update," and the tone/commitment HITL |

**Stuck vs. escalate is a real distinction, not a synonym:** *stuck* means Cortex failed
to do its job (mechanical, my problem to fix); *escalate* means Cortex did its job
correctly and hit the agent line (working as designed). They go to different places.

## 4. State

**Per-project isolation, with a small global layer.**

| Scope | What persists |
|---|---|
| **Per-project** | that project's activity history, last week's update, its decision log. A Northstar run can load *only* Northstar state. |
| **Global** (safe by construction) | team norms, the past-update *format*, and the run-key ledger from §1 (`project_id + ISO week` for cron, `project_id + event_id` for hook) |
| **Never persisted** | the draft text itself — it lands in `run-output/` as my review queue and is discarded once I've read it |

**Why isolation rather than a filter:** the fixtures include an embargoed project (Orbit,
`flags: [confidential]`) and one under `launch_hold` (Vega). Scoping state per project makes
cross-project leakage *structurally impossible* instead of something a prompt has to
remember every run. One filter bug and an embargo is gone; a wall doesn't have that failure
mode. Context leakage is M4's whole subject — this is the cheap version of that answer.

## 5. The five things a loop can lean on

_`state` is always-on. `connectors` only if you already have one wired (e.g. a Jira key or Google MCP), otherwise just note it as a plan. `skills`, `subagents`, `work tree` scale with autonomy; "not needed yet, because…" is a valid answer._

| Component | For Cortex |
|---|---|
| **Work tree** (isolated workspace per run, a git worktree) | **Not needed yet** — one run produces one markdown draft, no code is modified, single writer. If Cortex ever opens PRs or edits repo files, isolation becomes mandatory. |
| **Skills** (reusable capabilities) | **Not needed yet** — the closest candidate is "write the weekly update in our house format," which today lives in `prompts.py` + `search_past_updates`. It becomes a skill the moment a second agent needs the same format. |
| **Plugins / connectors** (tools & access, optional if you don't have one yet) | **None, by design.** All six tools read local fixtures (`00-build/tools.py`) — this is a certification build, and I'm deliberately not pointing it at production Jira/Confluence/Slack. *If* it were productionised, Jira first (real sprint/issue data behind `get_activity`), then Confluence for PRD scope. A Slack connector would be the real test of the agent line: delivery sits one step from publishing, and there is deliberately no publish tool. |
| **Subagents** (independent check when the loop can't grade itself) | Placeholder → M3 `orchestration-map.md`. The critic is already a separate model call reviewing a draft it didn't author; M3 formalises it — and fixes the over-strictness that escalated a correct draft. |
| **State tracking** | Per-project isolation + global norms/format/run-key ledger; drafts reviewed then discarded *(see §4)*. |

> Context plan (M4) and the hand-off to bounds & evals (M5) come in later modules, you'll add them to their own deliverables then, not here.

## Link to live loop

[`00-build/agent.py`](../00-build/agent.py) — bounds and stop conditions are visible in code
(`MAX_ITERATIONS`, `MAX_REVISIONS`, `COST_CAP_USD`, `MAX_QUEUE_ITEMS`), and there is no publish tool.
