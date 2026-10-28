# Launch Plan — November 2026 (One Page)

**Cell:** Cirruslabs Inventory & Forecasting Cell (VEDANTA POC)
**Sprint:** S-6 · Owner: Maya (Scrum Master)
**Target go-live:** 2026-11-10 (sprint end) · Status: In progress

## Objective
Ship the November monthly insight pack (D1–D7) for every plant on time, with all seven
deliverables validated by the QA cohort before release.

## Scope — the seven deliverables
| # | Deliverable | Owner | Due |
|---|---|---|---|
| D1 | 3-month gross inventory forecast by plant | Inventory Control | 2026-11-03 |
| D2 | Overstock / high-holdings analysis | Inventory Control | 2026-11-04 |
| D3 | Understock / critical spares at risk | Inventory Control | 2026-11-05 |
| D4 | Non-moving & slow-moving materials (NMI/SMI) | Inventory Control | 2026-11-06 |
| D5 | Prioritised purchase requisition suggestions | Procurement | 2026-11-07 |
| D6 | MRP eligibility per consumption trend | Planning | 2026-11-08 |
| D7 | Duplicate material code detection | Data Quality | 2026-11-09 |

## Milestones
- **Week 1 (Oct 28 – Nov 1):** Data refresh & baseline validation; confirm plant master data.
- **Week 2 (Nov 2 – 6):** D1–D4 computed, reviewed, and signed off by plant leads.
- **Week 3 (Nov 7 – 10):** D5–D7 completed; QA cohort runs the 213-test suite; go/no-go.
- **Nov 10:** Release insight pack to stakeholders; retro & close sprint.

## Roles
- **Maya (Scrum Master):** cadence, blockers, sprint health, release sign-off.
- **Ron (Chief of Staff):** stakeholder comms, calendar, follow-ups.
- **Inventory Control / Planning / Procurement / Data Quality:** deliverable owners above.
- **QA cohort:** validation gate (213 tests, 0 failures required).

## Risks & mitigations
- **Data freshness** (plant master data stale) → refresh in Week 1; escalate to Ron if blocked.
- **Scope creep** (new asks mid-sprint) → park in backlog; decide at grooming.
- **QA failures** → fix-forward within sprint; no release with failing tests.
- **Single-owner bottlenecks** → cross-train a backup per deliverable.

## Success criteria (go-live gate)
All seven deliverables present, QA suite green (213 pass / 0 fail), plant-lead sign-off
recorded, and release note posted to the stakeholder channel.

## Communication
Daily standup (async), weekly stakeholder update (Ron), release note on go-live.
Blockers logged immediately via the impediment ledger.
