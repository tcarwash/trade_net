# UI enhancement plan: a calmer command deck

Status: planned UI changes implemented in the browser UI; manual validation is complete for the primary workflows.

Implemented in the current working tree:

- Route-aware fueling actions, affordability/stock-limited fill, and clear tank
  fuel versus fuel cargo wording.
- Tracked freight checklist from loading through delivery, plus a ready-job
  recommendation and readable contract deadlines.
- Compact mobile commodity selection, with the selected market card shown.
- Contracts prioritized ahead of story boards; optional tutorial, local
  traffic, news, activity history, and secondary boards tucked away.
- Fleet views for Ships, Crew, Logistics, and Headquarters, with selection
  remembered per station, save file, and galaxy seed.
- Comms partner controls near the heading, with radio status in Comms.
- Routine arrival and automation notices reduced; players can mute routine
  milestone dialogs while hazard and radio failure warnings remain visible.

Validation completed: the tracked freight loop reached delivery and payout;
fuel service and route costs were checked; Fleet views survive refresh and work
with keyboard navigation; market selection and Contracts ordering work on
mobile; Comms radio status and local beacon preview work without invoking the
separate real-radio Broadcast control; all four views fit a 640 CSS-pixel
viewport at 2x device scale without horizontal overflow; and the browser
accessibility tree exposes names for actionable controls. Separate save files
with the same seed receive distinct preference IDs. A live screen-reader session
and a hardware radio transmission were not part of this UI implementation pass.

## Direction

Make the everyday loop obvious: choose a job, load cargo, fuel the ship, fly,
collect payment. The first priority is **less visual competition and easier
fueling**. Keep the dark space-trading character, but give each screen one
primary purpose and each task one clear next action.

This plan follows a source review and a Chromium preview of a disposable
seed-42 save at 1440×1000 and 390×844. It does not use or modify the player's
saved galaxy. Findings are design judgments, not results from player testing.

## What currently causes friction

- The opening screen has separate campaign, tutorial, and news banners before
  the map. Each competes to tell the player what matters.
- Refueling lives in Fleet, while insufficient-fuel warnings appear on the
  Flight deck. The fixed `Refuel +5` purchase can require repeated clicks.
- Fuel is also a tradable commodity. Buying fuel into the hold and filling
  the ship's tank need clearer labels because they are different actions.
- Contracts puts captain stories, five expeditions, discovery history, passing
  encounters, and campaign information above the ordinary job filters.
- Fleet combines servicing, recruiting, cargo transfers, automation, standing
  orders, ship shopping, equipment, and headquarters construction on one page.
- In this fresh-save preview, Contracts was about 2,660 pixels tall and Fleet
  about 4,790 on desktop. The mobile Flight deck was about 4,340 pixels tall.
  These are snapshots, not fixed dimensions or performance measurements.
- The mobile market expands all seven commodities into cards before the trade
  controls. A simple purchase takes too much scrolling.
- Routine arrivals and automated deliveries share a modal queue with major
  milestones. Repeated interruptions will become more intrusive as fleets grow.
- Local freight buttons can plot the destination with no required goods aboard.
  The recommended mission prioritizes the campaign over ready local deliveries.

## 1. First release: fueling and visual simplification

### Put ship services where the player flies

Show one compact active-ship strip above the route controls:

`Wayfarer · Haven   |   Tank 12/40   |   Hull 92%   |   Hold 3/30`

Fuel opens a small service popover on desktop or bottom sheet on mobile.
Display unit price, port fuel available, quantity added, resulting tank level,
total cost, and credits remaining. Offer:

- **Fill tank**: one purchase for the full missing quantity when affordable
  and in stock. Show its cost on the action.
- **Enough for this route**: purchase only the current shortfall for the
  plotted journey. Hide when no route is selected or no shortfall exists.
- **Custom amount**: a secondary numeric control, with useful presets.
- **Buy maximum available**: when credits or port stock prevent a full tank,
  name the partial result explicitly; never label a partial purchase “Fill tank.”

An insufficient-fuel route warning includes the purchase action directly:
`Need 2 more fuel · Refuel +2 for 56 cr` (illustrative prices after the fuel rebalance).
Fueling updates the route card; **Launch remains a separate deliberate action**.
Explain that “Enough for this route” covers the outbound leg only. Do not
promise a return flight or safe round trip from an unobserved destination.

Use **Tank fuel** in services and **Fuel cargo** in the market, with a short
explanation when that commodity is selected. Refueling consumes port stock and
credits, and does not consume fuel cargo. Fuel has a lower base price and
narrower scarcity swings; travel burns one unit per map hop, with charted routes
using half. Haven maintains a dependable fuel reserve. Emergency fuel remains
available when a port is out, at a premium.

Provide clear states for full tank, no stock, insufficient credits, in-flight
vessels, radio missions, and autopilot control. Follow the engine's existing
maintenance eligibility, including paused versus running automation.

### Reduce competition on the Flight deck

- Keep the ship strip, one compact tracked-task row, map, and route card.
- Fold the optional tutorial into that task row while the guide is active.
- Replace the large news banner with a quiet news link/count. Relevant urgent
  news can appear in the task detail, without another permanent banner.
- Move the NPC roster into a collapsed “Local traffic” section.
- Put modem, rig, economy-clock detail, and Debug inside a status/settings
  disclosure. Keep a small save/connection indicator visible. Expand an error
  when it affects the current action.
- Use one bright primary button per task area. Reduce uppercase micro-labels,
  nested card borders, glows, and repeated explanatory paragraphs. Preserve
  readable contrast and obvious keyboard focus.

Keep the existing four primary destinations initially. Avoid adding more
top-level navigation during the first pass.

**Acceptance:** a fuel-short ship can purchase its route shortfall or fill its
tank without visiting Fleet or repeatedly pressing +5. The Flight deck has one
prominent task prompt. Normal arrivals do not block play.

## 2. Make the core loop work as one task

### Track a job without inventing an acceptance requirement

Add “Track job” to ordinary freight offers. This is a planning preference;
existing freight is still deliverable without accepting it. Preserve the
explicit accept/board steps for expeditions and passengers.

Show a compact checklist: **Source → Load → Fly → Deliver**. Its next action
comes from the selected ship's actual state:

| Situation | Primary action |
| --- | --- |
| Missing goods, available at current port | Select goods and missing quantity in market |
| Missing goods, need another supplier | Plot suggested pickup, clearly marked as a hint |
| Cargo loaded, fuel insufficient | Purchase route shortfall |
| Cargo loaded, ready to depart | Review delivery route |
| Traveling | Show arrival countdown |
| Docked at destination with cargo | Deliver and collect the stated payout |
| Job expired, stock unavailable, or ship busy | Explain the blocker and offer another task |

An explicitly tracked task takes priority over campaign suggestions. Surface
an immediately available payout without silently replacing the tracked task.
Show the assigned/selected ship clearly; never commandeer another ship to make
the checklist look complete. Untracking a job does not cancel it or discard cargo.

Keep the tutorial restartable from Help. Persist its progress and tracked job
as preferences scoped to the save, rather than only the browser tab. Validate
those references after loading, delivery, expiration, and ship loss.

### Simplify the route and market

- The route card summarizes destination, fuel needed/remaining after arrival,
  travel time, and known danger. Put calculation details in a disclosure.
- Keep a compact pirate-response summary; expand choices on request and when a
  scanned pirate encounter is relevant. Preserve control on unscanned routes.
- Distinguish “You are here,” selected destination, and tracked destination
  using labels/shapes as well as color. Put secondary map details behind
  selection; preserve fog of war and distinguish known mission coordinates
  from surveyed port identity and observed market information.
- On mobile, show compact commodity rows and expand only the selected good.
  Put its quantity, quote, and Buy/Sell controls next to it.
- Label historical market intel “Last observed”; keep timestamps/age and
  detailed comparisons in the expanded view. Do not imply guaranteed profit.
- Show purchase cost and remaining credits before buying. Do not present actual
  net profit without a reliable cost basis and accounting for operating costs.

**Acceptance:** a new player can complete a tracked freight loop without
searching multiple boards for the next step. A mobile trade does not require
scrolling through every commodity's expanded details.

## 3. Separate management tasks within existing screens

### Contracts

Open on **Available jobs**, with filters directly below the heading. Add
**Tracked/active**, **Stories & exploration**, and **History** as secondary
views. Put expeditions and captain stories in Stories; resolved discoveries
belong in History. Filters should control the whole selected view, rather
than leaving unrelated boards above filtered results.

Cards show cargo/passenger requirement, destination, payout, time remaining,
readiness, and one next-step button. Use minutes/hours and an optional absolute
deadline instead of raw economy ticks. Rival offers also explain who can claim
them first. Radio offers keep their distinct local/real-radio labeling.

### Fleet

Default to a compact ship roster: location, task, fuel, hull, and alerts. Open
a selected ship's services, cargo, crew, equipment, and policy in a detail pane
or mobile sheet. Use secondary views for **Logistics**, **Shipyard**, and
**Haven**. Show standing orders only in Logistics and construction only in Haven.
Remember the player's selected view and expanded sections across refreshes.

At Haven, explicitly distinguish **Aboard ship**, **Eligible imported cargo**,
**Warehouse**, and **Reserved for radio**. Construction uses eligible materials
aboard; requisitions and partner shipments use warehouse stock. Put missing
requirements beside the relevant action, with source/unload shortcuts.

### Comms

Lead with partner contacts and current radio transfer status. Keep journal,
band passport, and diagnostic details in secondary views/disclosures. Preserve
the readiness checklist, explicit send controls, and distinction between local
simulation, unverified received advertisements, and verified radio contacts.
Collapsing controls must not stop the always-on receiver or conceal live
transmission progress and errors.

**Acceptance:** freight offers are visible immediately on entering Contracts;
Fleet initially shows ships and decisions needing attention; Haven construction
and radio diagnostics no longer lengthen routine ship management.

## 4. Quiet feedback and responsive polish

- Use nonblocking notifications for routine arrivals, ordinary purchases,
  recurring dispatches, and automated run completions. Aggregate fleet activity
  into “3 deliveries completed” instead of opening three dialogs.
- Reserve modal presentation for major milestones and decisions with lasting
  consequences. Keep an accessible activity history and a celebration preference.
- Keep actionable danger and loss notices visible until acknowledged, without
  interrupting unrelated input or silently authorizing a risky flight.
- Preserve input, focus, selected ship, filters, scroll position, and open sheets
  during polling. Update visible state without repeatedly announcing the journal.
- On mobile, keep the current task/action nearby, avoid stacking sticky bars,
  account for bottom navigation and the onscreen keyboard, and retain comfortable
  touch targets. Desktop should show ship status and the route/service controls
  within the first viewport at 1440×1000 under normal conditions.

## Implementation boundaries and verification

Start with release 1 as one coherent implementation slice. Ship simplification
and fueling together, then evaluate the calmer layout before adding task
tracking or secondary navigation.

Primary touchpoints are `tradenet/web/index.html` (`render`, `renderObjective`,
`renderGuide`, `renderFleetManager`, `renderContracts`, `updateTradeQuote`,
`updateRouteQuote`, `submitFlight`, and notification handling). The existing
`refuel(amount)` engine action supports arbitrary positive integer quantities;
the first pass does not need a new fueling mechanic.

Use authoritative service/route quotes from the server where necessary rather
than duplicating more eligibility and fuel calculations in the browser. Bind
purchases to the reviewed ship and quantity; revalidate stock, funds, and
eligibility when executing. Refresh a changed quote before accepting a different
cost. New preference storage should not change economic or radio state.

Verify each slice with behavior checks, then inspect desktop and phone layouts:

1. Full, empty, and partially filled tanks; exact route shortfall; pilot savings,
   navigator bypass, and evade fuel costs; insufficient stock/credits; route
   demand beyond tank capacity; double clicks; selected-ship changes; live quote
   changes. Confirm fuel, credits, and stock are debited exactly once.
2. Fresh-save freight from empty hold through payout, expired jobs, occupied
   holds, boarding/delivering a VIP, and switching ships while one is traveling.
3. Paused/running automation, warehouse capacity, imported-cargo eligibility,
   construction requirements, and reserved radio cargo remain consistent.
4. Keyboard-only servicing and trading, 200% zoom, reduced motion, screen-reader
   labels/focus, 390×844 mobile layout, and polling while editing a quantity.
5. Local task shortcuts never transmit. Real-radio send remains an explicit
   operator action; incoming listening continues with all ships away.

Use `tests/test_engine.py` and the relevant existing feature tests for economic
behavior, plus `tests/browser_smoke.py` for actual interactions. Avoid relying
only on HTML string-marker tests for the new workflows.

Evaluate with a small new-player walkthrough: can they identify their ship,
refuel without help, find an affordable job, and collect its payout? Record
hesitations and unnecessary screen changes before making further UI additions.
