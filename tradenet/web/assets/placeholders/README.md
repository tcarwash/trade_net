# Editable game art placeholders

These transparent PNG sheets are deliberately simple drawing guides. Paint over the placeholder silhouettes or replace a tile while preserving its cell size and position. Each cell has a visible name and status tag so current content is easy to distinguish from planned content.

## Sheets

| File | Cell size | Layout | Current content | Reserved content |
| --- | ---: | ---: | --- | --- |
| `encounter-rewards.png` | 64 × 64 | 8 across | Unique item, salvaged module, cargo, bounty, tank fuel, survey beacon | Two future drops |
| `ships.png` | 96 × 112 | 4 × 4 | Wayfarer, Wisp, Scout, Courier, Hauler, Express, Carrier | Interceptor, survey ship, salvage tug, passenger liner, repair tender, explorer, faction hull, derelict, reserved hull |
| `worlds-entities.png` | 64 × 64 | 4 × 4 | Temperate, desert, ringed, ice, volcanic, lush worlds; station; carrier | Derelict site, asteroid field, nebula, gas giant, ocean world, moon, anomaly, reserved entity |

Frames are row-major from the top left. The current reward modal reads the first six cells of `encounter-rewards.png` in this order: unique (artifact or mod), module/salvage, cargo, credits, fuel, beacon. It scales a cell to 160 × 160 CSS pixels. Keep the 8-cell strip at 512 × 64 when replacing it.

The ship sheet is an art planning template; existing ship portraits still come from `/ships.svg`. The worlds sheet includes the six current planet archetypes and current station/carrier entity types; existing planet art still comes from `/assets/planets/`. Future-labeled frames are placeholders for content that does not exist in the game yet.
