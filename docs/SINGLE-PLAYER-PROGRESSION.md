# Single-player progression

## Recoverable ship modifications

Pirate wrecks and derelicts can offer individual modifications. Recovery is optional:
packed parts occupy one cargo unit and have no fitted abilities. Bring the vessel
to a **shipyard** to install them. A ship can fit three salvaged modifications;
each occupies the cargo space stated on its card.

Shipyard → Outfitting lists recovered parts before the standard equipment catalog.
Uninstalling puts a part in that port's locker. Another vessel docked at the same
port can fit it using the target-vessel selector. Standard purchased equipment can
also be uninstalled and reused. Lockers cannot teleport parts to another port.

| Unique | Ability | Installed cargo space |
| --- | --- | --- |
| Pilgrim’s Lantern | Save 1 fuel per flight; +40 credits on first discoveries | 2 |
| The Last Word | +3 pirate-group damage; evasion exposes the hull to 2 extra damage | 3 |
| Mercy of Dawn | Absorb 4 hull damage; repairs cost 20 percentage points less | 2 |
| Magpie’s Promise | +2 common cargo in pirate wrecks; +20 bounty credits | 2 |

Each named unique can be recovered once per save. Moving it between vessels keeps
its identity. Jettisoned or destroyed uniques cannot be generated again. Fuel
savings cap at two from modifications; every flight still costs at least one fuel.

## Pursuit and jettisoning

Packed Pilgrim’s Lantern, The Last Word, and Magpie’s Promise broadcast signatures
that attract raiders. Fitting them at a shipyard shields those signatures. Some
VIP contracts are explicitly marked high-profile before boarding and also attract
raiders. Passengers cannot be jettisoned.

The flight deck identifies the attracting cargo/passenger, shows closing pressure,
and draws a pursuing raider marker. Pressure builds slowly across trips. Stations
prevent interception while docked; pursuit freezes during decision dialogs and
offline time contributes at most five seconds on a refresh.

**Jettison … permanently** discards a packed modification, freeing its cargo space.
With no attracting sources left, the pursuers break off. If a VIP or another part
still attracts them, pursuit pressure is reduced and the remaining cause is shown.
Jettisoning after an intercept has started does not cancel the current combat.

## Combat turns

A fight that leaves both sides alive stays paused and offers Fight / Evade / Pay
again. Failed escapes also return to those choices. The dialog shows turn number,
hull, remaining raider strength, attack, escape odds, fuel requirement, and toll.
Escape attempts consume two fuel; weapon load reduces escape odds, and pilots
improve them. Payment requires the complete quoted toll.

Victory pays the one-time bounty and offers optional salvage. Successful escape
or payment resumes the flight. At zero hull, normal mode returns the ship to its
origin with ten hull; hard mode uses permanent ship loss, including carried mods.
Pursuit contacts have a cooldown before another group can close in.

## Settlement projects

Contracts → Settlement development lists visited planets other than Haven.
Deliveries come from your physical cargo and may be split across several visits.
Projects have no deadline. Each stage grants credits and permanent local benefits:

1. Food and medicine establish the settlement and reduce local buy prices by 3%.
2. Ore and propellant increase specialty production by one per economy tick.
3. Ore and medicine unlock a shipyard and award an unclaimed named unique, when
   available. The reward waits in that port's locker even if the hold is full.

The stages are Frontier → Established → Growing → Thriving. Haven retains its
existing headquarters construction system.

## Course planning and route unlocks

**Plot route** on the flight deck accepts an origin, destination, and preference:

- **Along the network** previews each stop and sums fuel across those legs.
- **Direct** previews one flight to the destination with its direct-course risks.

Save a course for the active vessel. The highlighted map course persists through
reloads. **Travel next leg** departs only from the current stop; each arrival lets
you trade, refuel, or change plans. Plotting from a different origin is a preview
until that vessel reaches the origin. Costs and hazards are rechecked at departure.

Fresh galaxies begin with the Kepler and Vesper approaches open. The Prospect
approach and the Meridian/Drift forks near Kepler require persistent delivery
quests completed at Haven. Existing explored branches and vessels already in
transit retain their access when an older save is loaded.

Locked-route dialogs provide **View unlocking contract**. Contracts → **Route
unlocks** lists gate quests separately. Gate quests cannot expire or be displaced
by rotating dispatch postings. Old missing or superseded gate postings are repaired
on load without granting rewards or unlocking the route automatically.
