"""Curated vocabulary used by deterministic procedural name generation."""

# These are intentionally modular: the generator combines them with a numeric
# chart designation, so names remain identifiable as a system grows.
PLANET_PREFIXES = (
    "Aster", "Aurelia", "Boreal", "Caldera", "Cinder", "Cobalt", "Dawn",
    "Eidolon", "Ember", "Farpoint", "Fallow", "Frost", "Gannet", "Hallow",
    "Hesper", "Ilyra", "Juniper", "Kestrel", "Lacuna", "Lumen", "Morrow",
    "Nacre", "Nereid", "Northstar", "Orison", "Peregrine", "Quillon", "Rook",
    "Sable", "Sagan", "Solace", "Starling", "Tern", "Thistle", "Vela",
    "Verdant", "Vesper", "Waypoint", "Wren", "Yarrow", "Zephyr",
)

PLANET_SUFFIXES = (
    "Basin", "Bend", "Bloom", "Crossing", "Crown", "Delta", "Drift", "Fall",
    "Fen", "Field", "Gate", "Glen", "Haven", "Horizon", "Reach", "Rest",
    "Ridge", "Rift", "Rise", "Run", "Shallows", "Shoal", "Sound", "Spur",
    "Station", "Step", "Vale", "Vista", "Wake", "Ward", "Watch", "Well",
    "Wilds", "Wold", "Wreath", "Arch", "Beacon", "Chasm", "Garden", "Harbor",
    "Meridian", "Pass",
)

CREW_FIRST_NAMES = (
    "Ari", "Asha", "Avery", "Bex", "Cato", "Cleo", "Dara", "Dev", "Eli",
    "Elian", "Elara", "Emi", "Farah", "Finn", "Hana", "Ilya", "Imani",
    "Indra", "Jae", "Jalen", "Juno", "Kai", "Kavi", "Leona", "Lin", "Lio",
    "Luca", "Mara", "Mika", "Mina", "Nia", "Noor", "Oren", "Pax", "Rafi",
    "Ren", "Rhea", "Rin", "Sana", "Sera", "Sol", "Tavi", "Tomas", "Uma",
    "Vera", "Yara", "Zev",
)

CREW_FAMILY_NAMES = (
    "Adebayo", "Ahn", "Alvarez", "Basu", "Chen", "Costa", "Dawes", "Delgado",
    "Dlamini", "El-Amin", "Farouk", "Fern", "Fischer", "Flores", "Gao",
    "Haddad", "Hale", "Ibarra", "Ito", "Jensen", "Kaur", "Kim", "Kovacs",
    "Mercer", "Moreno", "Moss", "Navarro", "Okafor", "Osei", "Patel", "Quinn",
    "Reyes", "Rossi", "Sato", "Shah", "Singh", "Solano", "Soren", "Tanaka",
    "Vale", "Venn", "Watanabe", "Wells", "Yoon", "Zoric",
)

# Keep this as a stable, deterministic pool for the dockside hiring board.
CREW_NAMES = tuple(f"{first} {family}"
                   for first in CREW_FIRST_NAMES
                   for family in CREW_FAMILY_NAMES)
