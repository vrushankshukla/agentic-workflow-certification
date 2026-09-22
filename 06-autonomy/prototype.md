# Prototype: Cortex PM Chief-of-Staff Agent

> Module 6 · ★ Deliverable 1, the working agent demo
>
> ✅ **What this validates:** the agent actually runs end to end, by the end you'll have proven it with real screenshots of your Cortex across the six required moments (M2 to M6).

## What it does

_One paragraph: the agent in action, end to end._

## How you built it

- **Coding agent:** _which one you directed (Claude Code / Cursor / Codex)_
- **Model + bounds:** _model used, max iterations, cost cap, queue cap_
- **Repo / config:** _path to your build in `00-build/`_
- **Live link:** _[shareable URL, optional bonus]_

## Screenshots (required, collected M2 to M6)

Real screenshots of *your* Cortex running. These are the `00-build/CORTEX-ANATOMY.md` set and they are required, a link alone is not enough.

| # | Screenshot | What it shows | From |
|---|---|---|---|
| 1 | _[img]_ | happy-path run: a real drafted update + the HITL checkpoint (queued, not posted) | M2 |
| 2 | [transcript below](#m3-capture-the-critic-rejecting-a-draft-that-passed-every-code-gate) | the critic rejecting a bad draft → escalate, no retry | M3 |
| 3 | _[img]_ | a grounded update citing pulled activity + a caught hallucination | M4 |
| 4 | _[img]_ | jailbreak refused + escalated | M5 |
| 5 | _[img]_ | an iteration/cost/queue bound halting a runaway | M5 |
| 6 | _[img]_ | end-to-end run | M6 |

## M3 capture: the critic rejecting a draft that passed every code gate

**Caption:** All seven deterministic gates PASSED on this Vega draft — including
`no_commitment`, because the soft commitment carried no date for the regex to catch. The
independent critic failed it on rule 3, quoted the line, and the loop escalated to me with
no retry: commitment is above my agent line. This is the run that proves the critic earns
its model call instead of duplicating code. Fixture `00-build/fixtures/task-softcommit.md`,
run cost $0.0011.

```text
================================================================
DETERMINISTIC GATES (enforced in code, outside the model)
================================================================
  [PASS] is_update: asserts a colour status and names the subject project
  [PASS] grounded: all 2 ID(s)/metric(s) trace to pulled data
  [PASS] status_call: asserts yellow; a more conservative call is always allowed
  [PASS] story_cap: no story batch over the queue cap
  [PASS] out_of_scope: the PRD lists no out-of-scope items
  [PASS] confidentiality: no confidential project named
  [PASS] no_commitment: no date committed on a gated launch

================================================================
CRITIC, independent validator (the 5 rules code cannot check)
================================================================
{
  "verdict": "fail",
  "failed_rules": [3, 5],
  "reasons": [
    "rule 3: The draft states, \"The migration is on track to land next sprint...\" but the
     roadmap indicates that the GA date is unconfirmed and gated on closing the proration
     defect. This constitutes a soft commitment against the roadmap that fails the rule.",
    "rule 5: The draft states, \"The migration is on track to land next sprint with GA
     following shortly after,\" which does not directly answer the prompt's requirement to
     call it Yellow or Red based on evidence..."
  ]
}

================================================================
ESCALATE, critic rule 3, soft commitment on a launch the roadmap marks unconfirmed.
A human owns commitment, no retry. Run cost ≈ $0.0011
================================================================

================================================================
ESCALATED, decision request for a human (draft held, NOT posted)
================================================================
**Project:** Vega (billing migration)   **Status:** Yellow
- ... Sev-1 **Double-charge on plan upgrade (#440)** ... open PR (#442) ...
- The migration is on track to land next sprint with GA following shortly after ...
                  ^^^ the line the critic caught

Updated existing draft for run key P-VEGA-2026-W39 -> run-output/P-VEGA-2026-W39.md
(for your review, nothing was posted)
```

**What this run also taught me:** the first attempt at this fixture failed to produce
evidence — Cortex self-escalated on the colour question (`at_risk` + open Sev-1) and never
drafted, so the critic had nothing to review. A validator can only be proven against an
agent that actually produces output. The fixture was rewritten to let Cortex call Yellow
honestly while still carrying the soft commitment.

## How to run it

_Minimal steps for someone to reproduce the demo (env vars, and the command or the coding-agent prompt you used)._
