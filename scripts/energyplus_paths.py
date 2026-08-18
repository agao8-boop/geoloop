"""
scripts/energyplus_paths.py

Shared path resolution for EnergyPlus IDF and EPW files.
Used by both run_energyplus_loads.py and precompute_loads.py.

DATA LAYOUT
-----------
Copy your downloaded folders directly into the project:

  data/doe_prototypes/
    ASHRAE901_OfficeLarge_STD2022/
      ASHRAE901_OfficeLarge_STD2022_Albuquerque.idf
      ASHRAE901_OfficeLarge_STD2022_Atlanta.idf
      ...   (one IDF per city, .table.htm files are ignored)
    ASHRAE901_OfficeMedium_STD2022/
      ...
    ASHRAE901_OfficeSmall_STD2022/
      ...
    (add other building type folders as you download them)

  data/epw/
    USA_AK_Fairbanks.Intl.AP.702610_TMY3.epw
    USA_FL_Miami.Intl.AP.722020_TMY3.epw
    ...   (copy contents of ASHRAE901_epw/ folder here)

CITY → CLIMATE ZONE MAPPING  (official DOE ASHRAE 90.1-2022 table)
-------------------------------------------------------------------
Source: DOE Commercial Prototype Building Models, energycodes.gov/prototype-building-models

  Zone   Climate Name          City (IDF filename suffix)   State
  ──────────────────────────────────────────────────────────────────
  1A     Very Hot Humid        Miami                        FL
  2A     Hot Humid             Tampa                        FL
  2B     Hot Dry               Tucson                       AZ
  3A     Warm Humid            Atlanta                      GA
  3B     Warm Dry              ElPaso                       TX
  3C     Warm Marine           SanDiego                     CA
  4A     Mixed Humid           NewYork                      NY
  4B     Mixed Dry             Albuquerque                  NM
  4C     Mixed Marine          Seattle                      WA
  5A     Cool Humid            Buffalo                      NY
  5B     Cool Dry              Denver                       CO
  5C     Cool Marine           PortAngeles                  WA
  6A     Cold Humid            Rochester                    MN
  6B     Cold Dry              GreatFalls                   MT
  7      Very Cold             InternationalFalls            MN
  8      Subarctic/Arctic      Fairbanks                    AK

  Excluded (international): HoChiMinh (0A), Dubai (0B), NewDelhi (1B)
  All 16 US climate zones are covered by the downloaded file set.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

DOE_PROTOTYPES_DIR = ROOT / "data" / "doe_prototypes"
EPW_DIR            = ROOT / "data" / "epw"
ENERGYPLUS_DIR     = pathlib.Path("/Applications/EnergyPlus-22-1-0")

# ─────────────────────────────────────────────────────────────────────────────
# City → ASHRAE climate zone mapping
# ─────────────────────────────────────────────────────────────────────────────
# Key: city name as it appears at the end of the DOE IDF filename
#      (e.g. "Miami" from "ASHRAE901_OfficeSmall_STD2022_Miami.idf")
# Value: ASHRAE 90.1-2022 climate zone string, or None to skip.
#
# Zone 5A has no representative in the ASHRAE901_*_STD2022 downloads available.
# Add a "Chicago" entry here and place its IDF/EPW files in the data dirs to
# enable zone 5A simulations.

# Official DOE ASHRAE 90.1-2022 climate zone → representative city mapping.
# Source: DOE Commercial Prototype Building Models documentation table,
#   energycodes.gov/prototype-building-models
# Zones 0A (Ho Chi Minh), 0B (Dubai), 1B (New Delhi) are international; skipped.

CITY_TO_ZONE: dict[str, str | None] = {
    "Miami":              "1A",   # Very Hot Humid         — Miami Intl AP, FL
    "Tampa":              "2A",   # Hot Humid              — Tampa/MacDill AFB, FL
    "Tucson":             "2B",   # Hot Dry                — Tucson/Davis-Monthan AFB, AZ
    "Atlanta":            "3A",   # Warm Humid             — Atlanta/Hartsfield Jackson Intl AP, GA
    "ElPaso":             "3B",   # Warm Dry               — El Paso Intl AP, TX
    "SanDiego":           "3C",   # Warm Marine            — San Diego/Brown Field Muni AP, CA
    "NewYork":            "4A",   # Mixed Humid            — New York/JFK Intl AP, NY
    "Albuquerque":        "4B",   # Mixed Dry              — Albuquerque Intl Sunport, NM
    "Seattle":            "4C",   # Mixed Marine           — Seattle-Tacoma Intl AP, WA
    "Buffalo":            "5A",   # Cool Humid             — Buffalo Niagara Intl AP, NY
    "Denver":             "5B",   # Cool Dry               — Denver/Aurora/Buckley AFB, CO
    "PortAngeles":        "5C",   # Cool Marine            — Port Angeles/W.R. Fairchild Intl AP, WA
    "Rochester":          "6A",   # Cold Humid             — Rochester Intl AP, MN
    "GreatFalls":         "6B",   # Cold Dry               — Great Falls Intl AP, MT
    "InternationalFalls": "7",    # Very Cold              — International Falls Intl AP, MN
    "Fairbanks":          "8",    # Subarctic/Arctic       — Fairbanks Intl AP, AK
    # International zones — not applicable to US geothermal screening tool
    "HoChiMinh":          None,   # 0A Extremely Hot Humid — international
    "Dubai":              None,   # 0B Extremely Hot Dry   — international
    "NewDelhi":           None,   # 1B Very Hot Dry        — international
}

# Reverse map: zone → list of DOE city names that represent it
# (first entry is the primary; extras are secondary)
ZONE_TO_CITIES: dict[str, list[str]] = {}
for _city, _zone in CITY_TO_ZONE.items():
    if _zone is not None:
        ZONE_TO_CITIES.setdefault(_zone, []).append(_city)

# ─────────────────────────────────────────────────────────────────────────────
# DOE prototype label mapping  (internal key → DOE folder/filename fragment)
# ─────────────────────────────────────────────────────────────────────────────
# Maps prototype_loads.json keys to the label embedded in DOE folder names.
# Folder pattern: ASHRAE901_{DOE_LABEL}_STD{year}/
# IDF pattern:    ASHRAE901_{DOE_LABEL}_STD{year}_{City}.idf

DOE_LABELS: dict[str, str] = {
    "small_office":          "OfficeSmall",
    "medium_office":         "OfficeMedium",
    "large_office":          "OfficeLarge",
    "standalone_retail":     "RetailStandalone",
    "retail_stripmall":      "RetailStripmall",
    "primary_school":        "SchoolPrimary",
    "secondary_school":      "SchoolSecondary",
    "hospital":              "Hospital",
    "outpatient_healthcare": "OutpatientHealthcare",
    "small_hotel":           "HotelSmall",
    "large_hotel":           "HotelLarge",
    "warehouse":             "Warehouse",
    "midrise_apartment":     "MidriseApartment",
    "highrise_apartment":    "ApartmentHighRise",
    "restaurant_fastfood":   "RestaurantFastFood",
    "restaurant_sitdown":    "RestaurantSitDown",
}

# ─────────────────────────────────────────────────────────────────────────────
# EPW keyword map  (DOE city name → search keywords in EPW filename)
# ─────────────────────────────────────────────────────────────────────────────
# EPW filenames use dots and hyphens; city names don't always match exactly.
# Each entry is a list of strings to try (any match wins).

EPW_KEYWORDS: dict[str, list[str]] = {
    "Miami":              ["Miami"],
    "Tampa":              ["Tampa"],
    "Tucson":             ["Tucson"],
    "Atlanta":            ["Atlanta"],
    "ElPaso":             ["El.Paso", "El_Paso"],
    "SanDiego":           ["San.Deigo", "San.Diego"],   # note: TMY3 has typo "Deigo"
    "NewYork":            ["New.York", "Kennedy"],
    "Albuquerque":        ["Albuquerque"],
    "Seattle":            ["Seattle"],
    "PortAngeles":        ["Port.Angeles"],
    "Denver":             ["Denver"],
    "Buffalo":            ["Buffalo"],
    "GreatFalls":         ["Great.Falls"],
    "Rochester":          ["Rochester"],
    "InternationalFalls": ["International.Falls"],
    "Fairbanks":          ["Fairbanks"],
}


# ─────────────────────────────────────────────────────────────────────────────
# File finders
# ─────────────────────────────────────────────────────────────────────────────

def find_idf_folder(building_type: str) -> pathlib.Path | None:
    """Return the DOE prototype folder for a building type, or None if not found.

    Searches data/doe_prototypes/ for any directory whose name contains the
    DOE label for the building type (case-insensitive, any STD year).
    """
    label = DOE_LABELS.get(building_type)
    if not label:
        return None
    for folder in sorted(DOE_PROTOTYPES_DIR.iterdir()):
        if folder.is_dir() and label.lower() in folder.name.lower():
            return folder
    return None


def find_idf(building_type: str, zone: str) -> pathlib.Path | None:
    """Return the IDF path for a building type and ASHRAE climate zone.

    Picks the PRIMARY representative city for the zone (first in ZONE_TO_CITIES).
    If that city's IDF is not found, tries secondary cities for the same zone.
    Returns None if no matching IDF is found.
    """
    folder = find_idf_folder(building_type)
    if folder is None:
        return None

    candidates = ZONE_TO_CITIES.get(zone, [])
    for city in candidates:
        path = _idf_for_city(folder, city)
        if path is not None:
            return path
    return None


def _idf_for_city(folder: pathlib.Path, city: str) -> pathlib.Path | None:
    """Find the IDF file in a folder whose stem ends with _{city} (case-insensitive)."""
    city_lower = city.lower()
    for f in folder.glob("*.idf"):
        stem_lower = f.stem.lower()
        if stem_lower.endswith(f"_{city_lower}"):
            return f
    return None


def find_epw(zone: str) -> pathlib.Path | None:
    """Return the EPW file for an ASHRAE climate zone.

    Uses the primary representative city for the zone and searches data/epw/
    for a filename containing any of the city's EPW keywords.
    Falls back to secondary cities if the primary is not found.
    Returns None if no matching EPW is found.
    """
    candidates = ZONE_TO_CITIES.get(zone, [])
    for city in candidates:
        keywords = EPW_KEYWORDS.get(city, [city])
        path = _epw_by_keywords(keywords)
        if path is not None:
            return path
    return None


def _epw_by_keywords(keywords: list[str]) -> pathlib.Path | None:
    """Search data/epw/ for an EPW file containing any of the given keywords."""
    for f in sorted(EPW_DIR.glob("*.epw")):
        name = f.name
        if any(kw in name for kw in keywords):
            return f
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Inventory helper  (for precompute_loads.py and diagnostics)
# ─────────────────────────────────────────────────────────────────────────────

def inventory(building_types: list[str], zones: list[str]) -> tuple[list, list]:
    """Check which (building_type, zone) pairs have both IDF and EPW available.

    Returns:
        available : list of (building_type, zone, idf_path, epw_path)
        missing   : list of (building_type, zone, [reason_strings])
    """
    available = []
    missing   = []
    for btype in building_types:
        for zone in zones:
            i_path = find_idf(btype, zone)
            e_path = find_epw(zone)
            if i_path is not None and e_path is not None:
                available.append((btype, zone, i_path, e_path))
            else:
                reasons = []
                if i_path is None:
                    cities = ZONE_TO_CITIES.get(zone, [])
                    folder = find_idf_folder(btype)
                    if folder is None:
                        reasons.append(
                            f"  IDF folder missing for '{btype}' "
                            f"(expected: {DOE_PROTOTYPES_DIR}/...{DOE_LABELS.get(btype,'')}...)"
                        )
                    else:
                        reasons.append(
                            f"  IDF missing: no {cities} file in {folder.name}"
                        )
                if e_path is None:
                    cities = ZONE_TO_CITIES.get(zone, [])
                    reasons.append(
                        f"  EPW missing: no match for {cities} in {EPW_DIR}"
                    )
                missing.append((btype, zone, reasons))
    return available, missing


def print_inventory(building_types: list[str], zones: list[str]) -> None:
    """Print a formatted inventory of available and missing file pairs."""
    available, missing = inventory(building_types, zones)
    print(f"\n{'─'*60}")
    print(f"  DOE Prototypes dir : {DOE_PROTOTYPES_DIR}")
    print(f"  EPW dir            : {EPW_DIR}")
    print(f"  EnergyPlus         : {ENERGYPLUS_DIR}")
    print(f"{'─'*60}")
    print(f"  Available pairs    : {len(available)}")
    print(f"  Missing pairs      : {len(missing)}")

    if available:
        print("\nAVAILABLE:")
        for btype, zone, idf, epw in available:
            print(f"  ✓  {btype:20s} {zone:3s}  {idf.name}")
            print(f"                                   EPW: {epw.name}")

    if missing:
        print("\nMISSING:")
        for btype, zone, reasons in missing:
            cities = ZONE_TO_CITIES.get(zone, ["?"])
            print(f"  ✗  {btype:20s} {zone:3s}  ({', '.join(cities)})")
            for r in reasons:
                print(r)

    print(f"\n  To add files:")
    print(f"    IDF: copy ASHRAE folders → {DOE_PROTOTYPES_DIR}/")
    print(f"    EPW: copy .epw files     → {EPW_DIR}/")


if __name__ == "__main__":
    # Run as a diagnostic: python scripts/energyplus_paths.py
    import sys
    requested_types = sys.argv[1:] if len(sys.argv) > 1 else list(DOE_LABELS.keys())
    all_zones = list(ZONE_TO_CITIES.keys())
    print_inventory(requested_types, all_zones)
