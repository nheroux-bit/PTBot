# Cost & Budget Estimate

> All figures in **US dollars (USD)**. Loose ranges, not exact numbers.
> Built from the approved project spec. If the spec changes, redo this
> estimate before building.

## TL;DR

PTBot is a CLI tool that runs locally or in Oz cloud environments. The
only meaningful recurring cost is the AI usage from spawning 8 agents
per run (4 scouts + 3 deep-dive + 1 QC). Most months: $0 - $5 if you
run a few analyses. Costs go up with frequency of use. No hosting or
infrastructure needed.

## What you will need to sign up for

- Warp account with Oz access (required for agent orchestration)
- attack.market skill installed locally (dependency for run_local_agent)

## Hosting & infrastructure

None. PTBot is a local CLI tool. It writes output files to disk. No
server, database, or cloud hosting required.

When run via Oz cloud agents, Warp-hosted infrastructure handles
execution -- this is covered by your Warp team plan, not a separate
line item.

## API & third-party fees

> Assumption: about 2 - 5 precedent transaction analyses per month,
> each spawning 8 agents (4 scouts, 3 deep-dives, 1 QC).

- **AI / LLM (via Oz agents)**: estimated $1 - $5 per run. Each run
  spawns 8 agent sessions. Cost depends on model tier and prompt
  length. At 2 - 5 runs per month: about $2 - $25 / month.
- **Web search (if scouts access search APIs)**: $0 - $5 / month.
  Agents use web search during research. Cost depends on search
  provider and volume.

## Monthly band

- **Low** _(occasional use, 1 - 2 runs)_: ~$2 / month
- **Typical** _(regular use, 3 - 5 runs)_: ~$10 - $25 / month
- **High** _(heavy use, 10+ runs or large sector sweeps)_: ~$50 - $100 / month

## Scale considerations

- Running many analyses in quick succession (e.g. sweeping 10 sectors
  in a day) multiplies the per-run LLM cost linearly.
- Using more expensive model tiers for agents increases per-run cost.
- If scouts rely on paid search APIs, high-volume research sessions
  can push search costs up.

## Build & maintenance time

- **Build**: about 2 - 4 hours remaining (code is substantially
  implemented; remaining work is migration, verification, and skill
  installation)
- **Maintenance**: about 1 - 2 hours / month (prompt tuning, model
  updates, source list refresh)

## Decision point

Pick **one**. The build phase will refuse to start until this is
recorded.

1. **Build** -- proceed to build with this cost expectation.
2. **Rescope** -- keep building but reduce cost first. List the spec
   changes, then redo this estimate.
3. **No-build** -- stop here. Record the reason below.
4. **Skip** -- skip the cost phase. Record a short reason
   (e.g. "hobby project, cost is not a concern", or "cost already
   estimated as part of parent project X").

### Decision recorded

- **Decision**: build
- **Date**: 2026-05-04
- **Recorded by**: heroux
- **Reason**: N/A (build selected)

---

_This estimate is a snapshot. Vendor pricing changes over time. Redo
this file before any major scope change. Methodology lives in
[references/cost-models.md](deft/references/cost-models.md)._
