# Smart Entry Sizing

Echo can reduce the quantity of a valid options alert using point-in-time Alpaca
market context. This phase changes entry quantity only. It does not block an
otherwise valid alert and does not change stop loss, break-even, take-profit, or
trailing-stop behavior.

## Decision Inputs

- Six or more recent one-minute bars for the underlying ticker.
- Latest bid and ask for the exact alerted option contract.
- Underlying five-minute momentum.
- Recent three-bar trend versus the preceding three bars.
- Last price versus volume-weighted average price.
- Direction of the latest candle when its volume is at least average.
- CALL or PUT direction from the parsed Discord alert.

Echo classifies the context as agreement, mixed, or conflict. A spread wider
than 50 percent of the option midpoint prevents the agreement tier from using
full size.

## Defaults

| Setting | Default |
| --- | ---: |
| `smart_sizing_enabled` | `true` |
| `smart_sizing_agreement_percent` | `100` |
| `smart_sizing_mixed_percent` | `50` |
| `smart_sizing_conflict_percent` | `25` |

The percentage is applied after Echo's existing risk and source limits. The
result is rounded down to a whole contract with a floor of one contract. Smart
sizing cannot increase the previously calculated quantity.

If market context is unavailable or incomplete, Echo uses the mixed tier. If
smart sizing is disabled, it uses 100 percent of the previously calculated
quantity.

## Operator Controls

The controls are in `Risk Management > Position` under `Smart Entry Sizing`.
Each percentage must be greater than zero and no greater than 100.

Every submitted entry trade records the tier, score, applied percentage, quote
spread, and scoring reasons. Echo also emits an `entry_intelligence` operator
event with the base and selected quantities.
