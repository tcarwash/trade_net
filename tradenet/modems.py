"""Game unlock tiers; actual Data2G mode selection remains capability-driven."""

TIERS = (
    {"name": "Scout", "max_bandwidth_hz": 500, "frames_per_tick": 2, "upgrade_cost": 0},
    {"name": "Courier", "max_bandwidth_hz": 1200, "frames_per_tick": 6, "upgrade_cost": 500},
    {"name": "Express", "max_bandwidth_hz": 2400, "frames_per_tick": 16, "upgrade_cost": 1200},
)


# These are game-balance windows, travel speeds and cargo capacities, not
# measured RF throughput. Wayfarer is the separate, non-buyable starter hull.
SHIPS = (
    {"id": "wisp200", "name": "Wisp", "tier": 0, "cost": 200,
     "max_bandwidth_hz": 200, "frames_per_tick": 1, "speed": 1, "capacity": 16,
     "sprite": "wisp", "mode_family": "n4",
     "description": "Ultra-narrow 200 Hz N4 scout; a small, affordable cargo hull."},
    {"id": "scout500", "name": "Scout", "tier": 0, "cost": 350,
     "max_bandwidth_hz": 500, "frames_per_tick": 2, "speed": 1, "capacity": 30,
     "sprite": "scout", "description": "Flexible 500 Hz scout for narrowband trading."},
    {"id": "courier1200", "name": "Courier", "tier": 1, "cost": 900,
     "max_bandwidth_hz": 1200, "frames_per_tick": 6, "speed": 2, "capacity": 40,
     "sprite": "courier", "description": "Balanced 1200 Hz courier with room for regular deliveries."},
    {"id": "hauler2300", "name": "Hauler", "tier": 2, "cost": 1400,
     "max_bandwidth_hz": 2300, "frames_per_tick": 10, "speed": 2, "capacity": 60,
     "sprite": "hauler", "mode_family": "fsk",
     "description": "FSK long-haul freighter with a 2300 Hz ceiling and a large cargo hold."},
    {"id": "express2400", "name": "Express", "tier": 2, "cost": 1800,
     "max_bandwidth_hz": 2400, "frames_per_tick": 16, "speed": 3, "capacity": 30,
     "sprite": "express", "description": "Full-width 2400 Hz express; trades cargo space for game travel speed."},
)


def eligible_ship_modes(advertised: list[dict], class_id: str) -> list[dict]:
    """Advertised data modes within this hull's ceiling and optional family.

    ACK modes are control-only and never eligible for ship cargo. This does
    not change legacy tier eligibility or assert any measured RF rate.
    """
    ship = next((ship for ship in SHIPS if ship["id"] == class_id), None)
    if ship is None:
        raise ValueError("invalid ship class")
    family = ship.get("mode_family")
    result = []
    for mode in advertised:
        mode_id, bandwidth = mode.get("mode_id"), mode.get("bandwidth_hz")
        if not (isinstance(mode_id, str) and mode_id and "ack" not in mode_id.lower()
                and type(bandwidth) is int and 0 < bandwidth <= ship["max_bandwidth_hz"]):
            continue
        if family == "n4" and not mode_id.lower().startswith("n4-"):
            continue
        if family == "fsk" and not mode_id.lower().startswith("fsk"):
            continue
        result.append(mode)
    return result


def eligible_modes(advertised: list[dict], tier: int) -> list[dict]:
    """Filter *advertised* Data2G modes; never invent a modem mode.

    Each advertisement must have mode_id and bandwidth_hz. Actual PHY mode
    choice and rate adaptation stay with Data2G and the operator.
    """
    if not 0 <= tier < len(TIERS):
        raise ValueError("invalid ship modem tier")
    ceiling = TIERS[tier]["max_bandwidth_hz"]
    return [mode for mode in advertised
            if isinstance(mode.get("bandwidth_hz"), int)
            and 0 < mode["bandwidth_hz"] <= ceiling
            and isinstance(mode.get("mode_id"), str) and mode["mode_id"]]
