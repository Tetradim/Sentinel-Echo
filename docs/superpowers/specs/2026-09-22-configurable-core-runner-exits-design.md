# Configurable Core and Runner Exit Policy

## Objective

Allow each options position to be divided into a normally managed core allocation and an optional runner allocation. Consumers can decide whether runners exist, how many contracts become runners, when runner protection activates, which ordinary exit rules runners ignore, how much premium runners may risk, and how runner profits are trailed.

The policy must preserve broker-backed quantity accounting. Core and runner quantities are logical allocations within one Alpaca option position; Echo continues submitting ordinary SELL orders against the actual broker position.

## Terms

- **Original quantity**: total contracts confirmed filled for the entry campaign.
- **Core quantity**: contracts available to ordinary loss ladders, profit stages, profit floors, and coordinated trailing.
- **Runner candidate**: contracts reserved from profit-taking so they still exist if the runner activation threshold is reached.
- **Dedicated runner**: a runner candidate whose maximum favorable excursion has reached the configured activation threshold.
- **MFE**: maximum favorable excursion, calculated from the highest executable bid relative to the broker-confirmed average entry premium.

## Master Controls

The Risk Management screen adds a **Core / Runners** section with these controls:

| Setting | Default | Meaning |
| --- | ---: | --- |
| Core/runner policy | Off | Master switch. Off preserves the existing coordinated lifecycle. |
| Runner allocation mode | Percent | Percent of original, fixed contracts, or greater-of-percent-and-minimum. |
| Runner allocation percent | 20% | Requested percentage of filled contracts assigned as runner candidates. |
| Fixed runner contracts | 1 | Used in fixed mode. |
| Minimum runner contracts | 1 | Minimum in percent/greater-of modes when at least two contracts filled. |
| Maximum runner contracts | 0 | Zero means no explicit maximum. |
| Runner activation MFE | +100% | MFE required to convert candidates into dedicated runners. Zero dedicates them immediately. |
| Reserve candidates from profit exits | On | Keeps candidate contracts available while waiting for activation. |
| Loss ladder may consume candidates | On | Preserves normal downside control before runners earn protection. |

Runner quantity is whole-contract floor-rounded and capped at the broker-held quantity. A one-contract position may become a runner only when **Allow single-contract runner** is enabled; otherwise it remains core-managed.

The calculated allocation and its inputs are persisted at the first confirmed fill. Later DCA fills may increase original and core quantities, but cannot silently reduce an already dedicated runner quantity.

## Candidate Behavior Before Activation

When **Reserve candidates from profit exits** is enabled, runner candidates are protected from profit stages and the post-profit floor from entry, ensuring contracts remain available to become runners. Turning it off allows ordinary profit exits to consume candidates before activation. Before activation, candidates continue participating in loss protection when **Loss ladder may consume candidates** is enabled.

If losses reduce the broker position below the candidate quantity before activation, the candidate quantity is reduced to the broker-held quantity. No synthetic or negative core quantity is permitted.

When MFE reaches the activation threshold, the remaining candidate contracts become dedicated runners. Activation is permanent for that entry campaign and is written as an operator event.

## Protection Matrix

Consumers can independently choose whether dedicated runners are protected from:

- descending loss-ladder exits
- normal coordinated hard stop
- coordinated break-even and entry-plus-one-cent floors
- Stage 1 and Stage 2 profit-taking
- ordinary fixed, tightening, or elastic coordinated trailing
- reversal-warning partial reductions
- contextual analyst trims

Confirmed reversal, explicit contract-specific analyst exits, catastrophic runner stop, and mandatory 0DTE liquidation have separate controls and are never implicitly disabled by the protection matrix.

For each SELL decision, Echo calculates the permitted core quantity and runner quantity. A core-only exit cannot set the target remaining broker quantity below the currently protected runner quantity. Pending-order replacement uses that target remaining quantity so an older SELL cannot accidentally consume runners.

## Catastrophic Runner Risk

| Setting | Default | Meaning |
| --- | ---: | --- |
| Catastrophic runner stop | 65% | Exit dedicated runners when executable bid loss reaches this percentage. |
| Catastrophic stop confirmations | 2 | Distinct quote observations required. |
| Confirmation interval | 3 seconds | Minimum interval between confirmations. |

Setting the catastrophic stop percentage to `0` disables the price-based catastrophic stop and allows the runner to risk its full premium. This does not disable explicit analyst exits, configured reversal exits, or mandatory expiration handling.

The UI must display a clear inline state when full-premium risk is selected. Zero is a valid deliberate value, not a missing setting.

## Runner Trailing

Runner trailing has its own master switch and does not reuse the ordinary coordinated trail. Consumers may select:

1. **Fixed**: one activation MFE and one trail width.
2. **Tiered**: editable MFE-to-trail-width rows.
3. **Underlying-confirmed**: the tiered price trail must also have a configured underlying reversal before selling.

Default tiered schedule:

| Runner MFE | Trail below highest executable bid |
| ---: | ---: |
| +100% | 35% |
| +300% | 30% |
| +500% | 25% |
| +1,000% | 20% |

The consumer may add, remove, and reorder one to ten tiers. MFE values must be strictly increasing. Trail widths may widen or tighten according to consumer preference and must remain between 1% and 100%.

Additional controls:

- minimum dollar/premium distance
- bid/ask spread multiplier
- required bid-breach confirmations
- confirmation interval
- minimum time since activation
- require a fresh high after activation
- use executable bid or midpoint for observation; executable bid remains required for the final SELL trigger
- whether the trail floor may move downward when entering a wider tier; default is no

The default runner trail requires two bid breaches at least three seconds apart. A new high clears pending breach confirmation state.

## Core Profit Controls

Core profit stages remain independently configurable. Recommended defaults when the core/runner policy is enabled are:

| Stage | Trigger | Sell quantity |
| --- | ---: | ---: |
| Stage 1 | +25% | 25% of original quantity |
| Stage 2 | +50% | 25% of original quantity |

Profit-stage quantities can never consume protected runner candidates or dedicated runners. Consumers retain the existing ability to configure stage triggers and quantities.

The post-Stage-1 profit floor receives a separate **Apply to runners** toggle, default off. Its core target remains configurable in percentage or premium cents.

## Loss Ladder Controls

Each existing loss-ladder row gains an **Allocation target** choice:

- core only
- runners only
- core then runners
- entire position

The default is core only. The final ladder row therefore closes the remaining core without automatically closing dedicated runners. Consumers may choose entire position to preserve current all-out behavior.

Before runner activation, a separate **Loss ladder may consume candidates** toggle controls whether candidates participate. The default is on, preventing a not-yet-earned runner from bypassing ordinary loss controls.

## Analyst Exit Controls

Runner behavior for Discord exits is configurable by specificity and requested size:

- contextual trim protection on/off
- contextual full-exit protection on/off
- explicit contract trim protection on/off
- explicit contract full-exit override on/off
- percentage threshold that permits an analyst exit to consume runners

Recommended default: contextual trims do not consume runners; an explicit contract-specific 80% or greater exit may consume them. Every protected or overriding analyst decision records the parsed text, matched contract identity, requested quantity, allowed core quantity, and resulting broker target.

## Expiration Handling

Mandatory 0DTE liquidation remains the final authority by default. Consumers can configure a separate runner liquidation time, but cannot configure it after the broker's supported option-closing deadline.

For later-dated positions, runners remain open across sessions unless an enabled exit condition triggers. Startup reconciliation reconstructs core and runner quantities from persisted state and the current Alpaca position.

## Execution And Reconciliation

- Every exit decision expresses a target remaining quantity, not only a SELL quantity.
- Pending SELL orders are cancelled and replaced when their target would consume protected runners or leave excess core contracts.
- Broker fills update core first unless the order was explicitly runner-targeted.
- Partial fills recalculate both allocations from the broker-held remainder.
- Broker quantity is authoritative after every fill, restart, timeout, or late fill.
- If local allocation state is missing, Echo reconstructs it conservatively and records the reconciliation instead of assuming all contracts are core or all are runners.

## Observability

Positions and audit responses expose:

- original, core, candidate, and dedicated runner quantities
- runner activation threshold and activation timestamp
- runner MFE, highest executable bid, active trail tier, width, and floor
- pending breach count and last qualifying quote
- catastrophic stop configuration
- protections currently applied
- every exit's requested and permitted target quantities

After a contract is completely closed, Echo continues collecting read-only option quotes through the configured review horizon. This produces MFE/MAE and counterfactual policy evidence without creating simulated orders or positions.

## Validation And Compatibility

- Master switch off exactly preserves existing behavior.
- Percentages accept zero only where zero has explicit disabling semantics.
- Runner allocation cannot exceed 100% or the broker-held quantity.
- Tier MFE thresholds must increase; duplicate thresholds are rejected.
- Invalid combinations are rejected by the API and explained beside the relevant UI control.
- Existing positions opened before the feature remain core-only unless the consumer explicitly adopts them into the runner policy.
- Settings use backend defaults, API validation, frontend state, persistence tests, policy tests, fill-reconciliation tests, and restart tests so the displayed and effective policies cannot diverge.

## Recommended Initial Test Profile

- Policy enabled.
- Runner allocation: greater of 20% or one contract, maximum two.
- Activation: +100% MFE.
- Candidates protected from profit stages but consumable by pre-activation loss ladder.
- Dedicated runners protected from ordinary ladder, break-even/profit floor, ordinary trailing, reversal warning, and contextual trims.
- Catastrophic stop: -65%, two confirmations three seconds apart.
- Tiered runner trail: 35% at +100%, 30% at +300%, 25% at +500%, 20% at +1,000%.
- Explicit contract-specific 80% or greater analyst exit may consume runners.
- Confirmed reversal may close runners.
- Mandatory 0DTE runner liquidation remains enabled.
