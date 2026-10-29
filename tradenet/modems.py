"""Game unlock tiers; actual Data2G mode selection remains capability-driven."""

TIERS = (
    {"name": "Scout", "max_bandwidth_hz": 500, "frames_per_tick": 2, "upgrade_cost": 0},
    {"name": "Courier", "max_bandwidth_hz": 1200, "frames_per_tick": 6, "upgrade_cost": 500},
    {"name": "Express", "max_bandwidth_hz": 2400, "frames_per_tick": 16, "upgrade_cost": 1200},
)


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
