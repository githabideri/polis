# [1.22.7] Firepit destroys uncooked input items when the fire dies mid-smelt

## Environment

Vintage Story 1.22.7, .NET 10, Linux dedicated server (embedded client,
headless). A custom mod placed the items into the firepit's slots and
polled the output; it never touched the fire's fuel or smelt timers —
cooking, fueling and the burn lifecycle are all engine code
(`DoSmelt`-driven, as in 1.21/1.22).

## Observed behavior

The firepit's three logical slots: input (top-left, the item being
smelted), output (top-right), fuel (bottom-left). One charcoal fuels one
cooked item; the item in the input slot is transformed by its own
`DoSmelt` recipe.

With **two** raw meats in the input slot and **two** charcoal in the
fuel slot, the fire dies before the second item's smelt finishes. The
first item cooks normally and lands in the output slot, but the
**still-raw second meat is destroyed**: after the fire is out it is not
in the player's inventory, not in any firepit slot, and not on the
ground anywhere — it is simply gone.

Reproduced on seven consecutive runs in one evening (the same setup,
re-issued into a fresh firepit each time). Earlier runs the same day —
same world, same item counts, an older client build of the mod —
produced 2 of 2 cooked, so the failure is timing-dependent (the fuel
exhaustion landing inside the second smelt window) rather than
deterministic or mod-dependent. Nothing in the mod code writes or moves
that item: it disappears on the engine's extinguish path.

## Reproduction

1. Place a firepit and light it.
2. Put 2× `redmeat-raw` in the input slot (top-left).
3. Add 2× `charcoal` to the fuel slot (bottom-left) and do not add more
   fuel.
4. Let the fire run out (a couple of minutes).
5. Output slot: 1× `redmeat-cooked`. Search the inventory, the firepit's
   slots, and the ground: the second `redmeat-raw` is nowhere.

## Proposed fix

When the fire dies with an item mid-smelt in the input slot, return the
uncooked remainder to the player (or drop it at the firepit) instead of
discarding it. Item loss on extinguish should not happen for any
input-item quantity: the smelt is interrupted, not completed.

## Verification

Re-run the steps above several times: 1 cooked + 1 raw returned per
run, with the item account closed (nothing destroyed). Also verify that
the 2-of-2 case (sufficient fuel for both smelts) still produces two
cooked items with no duplicates returned.
