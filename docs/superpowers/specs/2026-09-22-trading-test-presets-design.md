# Trading Test Presets

## Goal

Add reproducible options-exit experiment presets to the existing Core / Runners tab. Selecting a preset must only create a reviewable draft; Echo's active settings change only after the operator presses Save.

## Placement and Interaction

The Core / Runners screen receives a **Trading test presets** section above the existing runner controls. It presents five named presets:

1. Runner Capture
2. Full Take Profit +50
3. No Downside Stop
4. Mike Directed
5. Wide-Risk Control

Selecting a preset updates the visible runner controls and displays every non-runner setting that will change. The screen labels the selection **Draft only** until Save succeeds. Reload discards an unsaved selection. Manual edits after selection mark the draft as customized without changing the preset payload silently.

## Preset Contract

Each preset is a complete exit-policy patch. It explicitly sets legacy take-profit, stop-loss, break-even, trailing, coordinated-exit, reversal, loss-ladder, core-runner, and 0DTE controls so stale settings from a previous experiment cannot leak into the next one.

Operational correctness controls are invariant across presets:

- sell-alert listening remains enabled;
- broker reconciliation and pending-order replacement are not changed;
- general and runner 0DTE liquidation remain enabled at 15:40;
- explicit contract-specific Discord exits remain available;
- presets do not change entry sizing, broker credentials, or auto-trading state.

## Presets

### Runner Capture

- Coordinated exits enabled; legacy independent exits disabled.
- Staged core profits: 50% of core at +25%, then 25% at +50%.
- Defensive core loss ladder: 10% at -15%, 20% at -25%, 30% at -35%, remaining core at -50%.
- Runner allocation: greater of 20% or one contract, maximum two.
- Runner activation: +100% MFE.
- Tiered runner trail: 35% at +100%, 30% at +300%, 25% at +500%, and 20% at +1,000%.
- Runner catastrophic stop: -65% with two confirmations three seconds apart.

### Full Take Profit +50

- Coordinated exits and runners disabled.
- Legacy take profit enabled at +50%, selling 100%.
- Price stop, break-even, trailing, loss ladder, adaptive trailing, and reversal exits disabled.
- Explicit Discord exits and mandatory 0DTE liquidation remain enabled.

### No Downside Stop

- Coordinated staged-profit lifecycle enabled.
- All price-based downside exits disabled by disabling the loss ladder and setting coordinated hard/emergency thresholds to 100%.
- Core runners enabled with no catastrophic price stop.
- Staged core profits and tiered runner trailing remain active.
- Explicit Discord exits, confirmed reversals, and mandatory 0DTE liquidation remain enabled.

The 100% coordinated threshold is an engine boundary rather than an ordinary protective stop; it can only act when the premium is effectively exhausted. The UI describes this preset as full premium at risk.

### Mike Directed

- Coordinated exits, runners, legacy take-profit, stop-loss, break-even, trailing, adaptive trailing, and reversal exits disabled.
- Echo follows explicit Discord exits and mandatory 0DTE liquidation only.

### Wide-Risk Control

- Coordinated exits enabled with -50% normal, -65% high-risk, and -75% emergency thresholds.
- Core loss ladder disabled so the hard stop is the downside comparison point.
- Staged profits at +25% and +50%.
- Runners disabled; coordinated trailing remains available for the post-stage remainder.

## Save and Audit Behavior

Preset selection performs no HTTP write. Save submits one PUT to `/api/settings` containing the selected complete preset patch plus the visible runner form. A successful save clears the draft marker and reports the activated preset. The backend's existing settings audit records every changed field.

## Validation and Testing

- Unit tests prove all five presets exist and contain invariant 0DTE and Discord-exit controls.
- Unit tests prove mutually exclusive legacy/coordinated controls are reset correctly.
- Unit tests prove No Downside Stop disables price-based downside exits while retaining upside and mandatory exits.
- Persistence tests prove selecting is local-only and Save is the only settings PUT path.
- TypeScript, frontend tests, backend settings tests, and production build must pass.

