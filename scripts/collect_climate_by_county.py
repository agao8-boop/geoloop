"""Generate data/public/climate_by_county.csv.

Assigns ASHRAE 169-2013 climate zones to all US counties by:
1. Reading the county list from deep_thermal_by_county.csv
2. Applying state-level defaults (Table B-1 dominant zone)
3. Applying county-level exceptions for multi-zone states
"""

import pathlib
import pandas as pd

_ROOT = pathlib.Path(__file__).parents[1]
_IN   = _ROOT / "data" / "public" / "deep_thermal_by_county.csv"
_OUT  = _ROOT / "data" / "public" / "climate_by_county.csv"

# ASHRAE 169-2013 Table B-1 — dominant climate zone per state
STATE_DEFAULTS = {
    'AK': '7',  'AL': '3A', 'AR': '3A', 'AZ': '3B', 'CA': '3B',
    'CO': '5B', 'CT': '5A', 'DC': '4A', 'DE': '4A', 'FL': '2A',
    'GA': '3A', 'GU': '1A', 'HI': '1A', 'IA': '5A', 'ID': '5B',
    'IL': '5A', 'IN': '5A', 'KS': '4A', 'KY': '4A', 'LA': '2A',
    'MA': '5A', 'MD': '4A', 'ME': '6A', 'MI': '5A', 'MN': '6A',
    'MO': '4A', 'MP': '1A', 'MS': '3A', 'MT': '6B', 'NC': '3A',
    'ND': '6A', 'NE': '5A', 'NH': '6A', 'NJ': '4A', 'NM': '4B',
    'NV': '3B', 'NY': '5A', 'OH': '5A', 'OK': '3A', 'OR': '4C',
    'PA': '5A', 'PR': '1A', 'RI': '5A', 'SC': '3A', 'SD': '6A',
    'TN': '4A', 'TX': '2A', 'UT': '4B', 'VA': '4A', 'VI': '1A',
    'VT': '6A', 'WA': '4C', 'WI': '6A', 'WV': '4A', 'WY': '6B',
}

# County-level exceptions (county_fips → climate_zone)
COUNTY_EXCEPTIONS = {
    # Florida: extreme south is 1A
    '12011': '1A',  # Broward
    '12086': '1A',  # Miami-Dade
    '12087': '1A',  # Monroe
    '12099': '1A',  # Palm Beach
    # Texas: far west desert is 2B
    '48109': '2B',  # Culberson
    '48141': '2B',  # El Paso
    '48229': '2B',  # Hudspeth
    '48243': '2B',  # Jeff Davis
    '48377': '2B',  # Presidio
    # Texas: west TX elevated is 3B
    '48043': '3B',  # Brewster
    '48389': '3B',  # Reeves
    '48443': '3B',  # Terrell
    # Arizona: low desert (south) is 2B
    '04013': '2B',  # Maricopa (Phoenix)
    '04019': '2B',  # Pima (Tucson)
    '04021': '2B',  # Pinal
    '04023': '2B',  # Santa Cruz
    '04027': '2B',  # Yuma
    '04012': '2B',  # La Paz
    # Arizona: high elevation is 5B
    '04005': '5B',  # Coconino (Flagstaff)
    '04017': '5B',  # Navajo
    '04001': '5B',  # Apache
    # California: coastal zones 3C
    '06001': '3C',  # Alameda (Oakland)
    '06013': '3C',  # Contra Costa
    '06041': '3C',  # Marin
    '06055': '3C',  # Napa
    '06075': '3C',  # San Francisco
    '06081': '3C',  # San Mateo
    '06085': '3C',  # Santa Clara (San Jose)
    '06087': '3C',  # Santa Cruz
    '06097': '3C',  # Sonoma
    # California: San Diego coast
    '06073': '3C',  # San Diego
    # California: north interior
    '06035': '5B',  # Lassen
    '06049': '5B',  # Modoc
    '06063': '5B',  # Plumas
    '06091': '5B',  # Sierra
    '06093': '5B',  # Siskiyou
    '06103': '5B',  # Tehama (partially)
    # Nevada: north (Reno area) is 5B
    '32001': '5B',  # Churchill
    '32003': '3B',  # Clark (Las Vegas)
    '32007': '5B',  # Elko
    '32011': '5B',  # Eureka
    '32013': '5B',  # Humboldt
    '32015': '5B',  # Lander
    '32017': '5B',  # Lincoln
    '32021': '5B',  # Mineral
    '32023': '5B',  # Nye
    '32027': '5B',  # Pershing
    '32029': '5B',  # Storey
    '32031': '5B',  # Washoe (Reno)
    '32033': '5B',  # White Pine
    # Alaska: interior/north is 8
    '02090': '8',   # Fairbanks North Star
    '02100': '8',   # Haines
    '02180': '8',   # Nome
    '02185': '8',   # North Slope
    '02188': '8',   # Northwest Arctic
    '02240': '8',   # Southeast Fairbanks
    '02261': '8',   # Valdez-Cordova
    '02270': '8',   # Wade Hampton
    '02290': '8',   # Yukon-Koyukuk
    # Colorado: high mountain counties → 7
    '08097': '7',   # Pitkin (Aspen)
    '08109': '7',   # Saguache
    # Minnesota: far north → 7
    '27003': '7',   # Beltrami
    '27007': '7',   # Carlton
    '27071': '7',   # Koochiching
    '27075': '7',   # Lake
    '27077': '7',   # Lake of the Woods
    '27089': '7',   # Marshall
    '27137': '7',   # St. Louis (Duluth)
    '27135': '7',   # Roseau
    # Wisconsin far north → 7
    '55003': '7',   # Ashland
    '55013': '7',   # Burnett
    '55078': '7',   # Menominee
    # Oregon east → 5B
    '41001': '5B',  # Baker
    '41013': '5B',  # Crook
    '41017': '5B',  # Deschutes
    '41021': '5B',  # Gilliam
    '41023': '5B',  # Grant
    '41025': '5B',  # Harney
    '41031': '5B',  # Jefferson
    '41037': '5B',  # Lake
    '41045': '5B',  # Malheur
    '41049': '5B',  # Morrow
    '41055': '5B',  # Sherman
    '41059': '5B',  # Umatilla
    '41061': '5B',  # Union
    '41063': '5B',  # Wallowa
    '41065': '5B',  # Wasco
    '41069': '5B',  # Wheeler
    # Washington east → 5B
    '53001': '5B',  # Adams
    '53003': '5B',  # Asotin
    '53013': '5B',  # Columbia
    '53017': '5B',  # Douglas
    '53019': '5B',  # Ferry
    '53021': '5B',  # Franklin
    '53023': '5B',  # Garfield
    '53025': '5B',  # Grant
    '53037': '5B',  # Kittitas
    '53039': '5B',  # Klickitat
    '53043': '5B',  # Lincoln
    '53047': '5B',  # Okanogan
    '53051': '5B',  # Pend Oreille
    '53063': '5B',  # Spokane
    '53065': '5B',  # Stevens
    '53071': '5B',  # Walla Walla
    '53075': '5B',  # Whitman
    '53077': '5B',  # Yakima
    # South Dakota west → 7
    '46007': '7',   # Bennett
    '46031': '7',   # Corson
    '46037': '7',   # Day
    '46041': '7',   # Dewey
    '46045': '7',   # Edmund
    '46055': '7',   # Haakon
    '46059': '7',   # Harding
    '46069': '7',   # Hyde
    '46071': '7',   # Jackson
    '46075': '7',   # Jones
    '46091': '7',   # Marshall
    '46095': '7',   # Mellette
    '46099': '7',   # Minnehaha
    '46105': '7',   # Perkins
    '46117': '7',   # Stanley
    '46121': '7',   # Todd
    '46123': '7',   # Tripp
    '46127': '7',   # Union
    '46137': '7',   # Ziebach
    # North Dakota west → 7
    '38003': '7',   # Barnes
    '38015': '7',   # Burleigh
    '38023': '7',   # Divide
    '38033': '7',   # Golden Valley
    '38041': '7',   # Hettinger
    '38053': '7',   # McKenzie
    '38055': '7',   # McLean
    '38059': '7',   # Morton
    '38061': '7',   # Mountrail
    '38065': '7',   # Oliver
    '38085': '7',   # Sioux
    '38087': '7',   # Slope
    '38089': '7',   # Stark
    '38105': '7',   # Williams
}


def main() -> None:
    df = pd.read_csv(_IN, dtype={"county_fips": str})
    df["county_fips"] = df["county_fips"].str.zfill(5)

    # Apply state default, then county exceptions
    df["climate_zone"] = df["state_abbrev"].map(STATE_DEFAULTS).fillna("unknown")
    df["climate_zone"] = df["county_fips"].map(COUNTY_EXCEPTIONS).combine_first(df["climate_zone"])

    out = df[["county_fips", "state_abbrev", "county_name", "climate_zone"]].copy()
    out.to_csv(_OUT, index=False)
    print(f"Wrote {len(out):,} rows to {_OUT}")

    dist = out["climate_zone"].value_counts().sort_index()
    print("\nClimate zone distribution:")
    for zone, count in dist.items():
        print(f"  {zone:4s}: {count:4d} counties")

    unmapped = out[out["climate_zone"] == "unknown"]
    if not unmapped.empty:
        print(f"\nWARNING: {len(unmapped)} counties have no climate zone:")
        print(unmapped[["county_fips", "state_abbrev", "county_name"]].to_string(index=False))


if __name__ == "__main__":
    main()
