#!/usr/bin/env python3
"""
scripts/run_energyplus_loads.py

Generate an 8,760-hour heating and cooling load profile for a DOE prototype
office building using EnergyPlus with ZoneHVAC:IdealLoadsAirSystem.

WHAT THIS DOES
--------------
1. Loads a DOE Commercial Prototype Building IDF (ASHRAE 90.1-2019).
2. Replaces the prototype's HVAC with ZoneHVAC:IdealLoadsAirSystem in
   every zone — an ideal system that delivers exactly the zone load with
   no fan, coil, or efficiency losses.  This isolates the pure building
   thermal demand from the mechanical system.  The resulting Q_heat[h]
   and Q_cool[h] represent the heat the ground loop must absorb or reject.
3. Scales the building geometry and proportional internal loads to the
   requested floor area (if it differs from the prototype reference size).
4. Runs EnergyPlus via the pyenergyplus Python API.
5. Returns and saves Q_heat_W[8760] and Q_cool_W[8760] in numpy arrays.

WHY ZoneHVAC:IdealLoadsAirSystem
---------------------------------
This EnergyPlus object supplies heated or cooled air at whatever rate is
needed to hold the zone at setpoint with zero modeled HVAC hardware.
It is the standard EnergyPlus method for extracting unconditioned-side
zone thermal loads.  The output variable "Zone Ideal Loads Total Heating
Energy Rate" [W] is the instantaneous zone demand at each timestep.

Reference: EnergyPlus Input-Output Reference (NREL, 2024), sec. 1.36.

SETUP
-----
1. Install EnergyPlus (v24.2 recommended):
       https://energyplus.net/downloads
   Default macOS install path: /Applications/EnergyPlus-22-1-0
   Set ENERGYPLUS_DIR to your actual install path (env var or edit below).

2. Download the DOE Commercial Prototype IDF:
       https://energycodes.gov/prototype-building-models
   Select: Standard 90.1-2019 → Small Office → Chicago (ASHRAE CZ 5A).
   Save the extracted .idf as, e.g., data/energyplus_cache/SmallOffice.idf

3. Download the EPW weather file for your target location:
       https://energyplus.net/weather
   For Chicago CZ 5A, search "Chicago OHare International".
   File: USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw
   Save to, e.g., data/energyplus_cache/Chicago_5A.epw

USAGE
-----
  python scripts/run_energyplus_loads.py \\
      --idf  data/energyplus_cache/SmallOffice.idf \\
      --epw  data/energyplus_cache/Chicago_5A.epw \\
      --area 5000 \\
      --out  outputs/loads_SmallOffice_5000sqft

DOE PROTOTYPE FLOOR AREAS (reference sizes)
-------------------------------------------
  SmallOffice  :   511 m² /   5,502 sq ft  (single story)
  MediumOffice : 4,982 m² /  53,628 sq ft  (3 stories)
  LargeOffice  :46,320 m² / 498,588 sq ft  (12 stories)
  Source: Deru et al. (2011), NREL/TP-5500-46861.

REFERENCES
----------
  Deru, M. et al. (2011). U.S. Department of Energy commercial reference
    building models of the national building stock. NREL/TP-5500-46861.
    doi:10.2172/1000545
  EnergyPlus (2024). Input-Output Reference, v24.2. NREL/DOE.
    energyplus.net/documentation
  DOE (2023). Commercial Prototype Building Models (90.1-2019).
    energycodes.gov/prototype-building-models
"""

import argparse
import math
import os
import pathlib
import re
import sys

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

ENERGYPLUS_DIR = pathlib.Path(
    os.environ.get("ENERGYPLUS_DIR", "/Applications/EnergyPlus-22-1-0")
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "energyplus_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# DOE prototype reference floor areas and metadata.
# Source: Deru et al. (2011) NREL/TP-5500-46861, Table 3.
DOE_PROTOTYPES = {
    "SmallOffice": {
        "floor_area_m2": 511.2,
        "floor_area_sqft": 5502,
        "num_floors": 1,
        "description": "Single-story, 5,502 sq ft (511 m²). "
                       "5 zones: Core + 4 perimeter.",
    },
    "MediumOffice": {
        "floor_area_m2": 4982.2,
        "floor_area_sqft": 53628,
        "num_floors": 3,
        "description": "3-story, 53,628 sq ft (4,982 m²). "
                       "15 zones: 5 per floor (Core + 4 perimeter).",
    },
    "LargeOffice": {
        "floor_area_m2": 46320.0,
        "floor_area_sqft": 498588,
        "num_floors": 12,
        "description": "12-story, 498,588 sq ft (46,320 m²). "
                       "19 zones per floor.",
    },
}

# EnergyPlus IDD object classes belonging to the HVAC system.
# These are removed from the prototype and replaced with IdealLoads.
# IdealLoads needs only: Zone, thermostat setpoints, and building envelope.
#
# Kept deliberately: Zone, BuildingSurface:Detailed, FenestrationSurface:Detailed,
# Lights, ElectricEquipment, People, Schedule*, Construction, Material*,
# ZoneControl:Thermostat, ThermostatSetpoint:*, SiteLocation, RunPeriod,
# Building, ShadowCalculation, HeatBalanceAlgorithm, Timestep, etc.
_HVAC_CLASSES_TO_REMOVE = {
    # Air loops and distribution
    "AIRLOOPHVAC",
    "AIRLOOPHVAC:OUTDOORAIRSYSTEM",
    "AIRLOOPHVAC:OUTDOORAIRSYSTEM:EQUIPMENTLIST",
    "AIRLOOPHVAC:CONTROLLERLIST",
    "AIRLOOPHVAC:ZONESPLITTER",
    "AIRLOOPHVAC:ZONEMIXER",
    "AIRLOOPHVAC:SUPPLYPATH",
    "AIRLOOPHVAC:RETURNPATH",
    "AIRLOOPHVAC:RETURNPLENUM",
    "AIRLOOPHVAC:SUPPLYPLENUM",
    "AIRLOOPHVAC:UNITARYSYSTEM",
    "AIRLOOPHVAC:UNITARYHEATPUMP:AIRTOAIR",
    "AIRLOOPHVAC:UNITARYHEATPUMP:WATERTOAIR",
    # Fans
    "FAN:CONSTANTVOLUME",
    "FAN:VARIABLEVOLUME",
    "FAN:ONOFF",
    "FAN:SYSTEMMODEL",
    # Coil systems (wrappers around individual coils)
    "COILSYSTEM:COOLING:DX",
    "COILSYSTEM:COOLING:WATER:HEATEXCHANGERASSISTED",
    "COILSYSTEM:HEATING:DX",
    # Cooling coils
    "COIL:COOLING:DX:SINGLESPEED",
    "COIL:COOLING:DX:TWOSPEED",
    "COIL:COOLING:DX:VARIABLESPEED",
    "COIL:COOLING:DX:MULTISPEED",
    "COIL:COOLING:WATERTOAIRHEATPUMP:EQUATIONFIT",
    "COIL:COOLING:WATER",
    # Heating coils
    "COIL:HEATING:FUEL",
    "COIL:HEATING:GAS",
    "COIL:HEATING:ELECTRIC",
    "COIL:HEATING:DX:SINGLESPEED",
    "COIL:HEATING:WATERTOAIRHEATPUMP:EQUATIONFIT",
    "COIL:HEATING:WATER",
    # Heat exchangers (air-to-air ERV/HRV; present in cold-climate prototypes)
    "HEATEXCHANGER:AIRTOAIR:SENSIBLEANDLATENT",
    "HEATEXCHANGER:AIRTOAIR:FLATPLATE",
    "HEATEXCHANGER:DESICCANT:BALANCEDFLOW",
    # Controllers and setpoint managers
    "CONTROLLER:WATERCOIL",
    "CONTROLLER:OUTDOORAIR",
    "CONTROLLER:MECHANICALVENTILATION",
    "SETPOINTMANAGER:SCHEDULED",
    "SETPOINTMANAGER:MIXEDAIR",                      # IDD name has no space
    "SETPOINTMANAGER:MIXED AIR",                     # legacy alias kept for safety
    "SETPOINTMANAGER:OUTDOORAIRRESET",
    "SETPOINTMANAGER:OUTDOORAIRPRETREAT",
    "SETPOINTMANAGER:WARMEST",
    "SETPOINTMANAGER:WARMESTTEMPERATUREFLOW",
    "SETPOINTMANAGER:COLDEST",
    "SETPOINTMANAGER:FOLLOWOUTDOORAIRTEMPERATURE",
    "SETPOINTMANAGER:SINGLEZONE:COOLING",
    "SETPOINTMANAGER:SINGLEZONE:HEATING",
    "SETPOINTMANAGER:SINGLEZONE:REHEAT",
    "SETPOINTMANAGER:SINGLEZONE:HUMIDITY:MINIMUM",
    "SETPOINTMANAGER:MULTIZONE:HUMIDITY:MAXIMUM",
    "SETPOINTMANAGER:MULTIZONE:HUMIDITY:MINIMUM",
    "SETPOINTMANAGER:MULTIZONE:COOLING:AVERAGE",
    "SETPOINTMANAGER:MULTIZONE:HEATING:AVERAGE",
    "SETPOINTMANAGER:MULTIZONE:MINIMUMHUMIDITY:AVERAGE",
    "SETPOINTMANAGER:MULTIZONE:MAXIMUMHUMIDITY:AVERAGE",
    "SETPOINTMANAGER:SCHEDULED:DUALSETPOINT",
    "SETPOINTMANAGER:RETURNTEMPERATURE:HOTWATER",
    "SETPOINTMANAGER:RETURNTEMPERATURE:CHILLEDWATER",
    # Plant and condenser loops
    "PLANTLOOP",
    "CONDENSERLOOP",
    "CHILLER:ELECTRIC:EIR",
    "CHILLER:ELECTRIC:REFORMULATEDEIR",
    "BOILER:HOTWATER",
    "PUMP:VARIABLESPEED",
    "PUMP:CONSTANTSPEED",
    "PIPE:ADIABATIC",
    "PIPE:OUTDOOR",
    # Air terminals and distribution units (zone-side distribution)
    "AIRTERMINAL:SINGLEDUCT:UNCONTROLLED",
    "AIRTERMINAL:SINGLEDUCT:VAV:NOREHEAT",
    "AIRTERMINAL:SINGLEDUCT:VAV:REHEAT",
    "AIRTERMINAL:SINGLEDUCT:CONSTANTVOLUME:REHEAT",
    "AIRTERMINAL:SINGLEDUCT:CONSTANTVOLUME:NOREHEAT",
    "ZONEHVAC:AIRDISTRIBUTIONUNIT",          # ADU wraps the air terminal; must remove with terminal
    # Water heaters and fixtures (nodes conflict with IdealLoads initialization)
    "WATERHEATER:MIXED",
    "WATERHEATER:STRATIFIED",
    "WATERUSE:CONNECTIONS",
    "WATERUSE:EQUIPMENT",
    # Zone HVAC equipment lists/connections (will be re-added for IdealLoads)
    "ZONEHVAC:EQUIPMENTLIST",
    "ZONEHVAC:EQUIPMENTCONNECTIONS",
    # Plant equipment lists and operation
    "PLANTEQUIPMENTLIST",
    "CONDENSEREQUIPMENTLIST",
    "PLANTEQUIPMENTOPERATION:COOLINGLOAD",
    "PLANTEQUIPMENTOPERATION:HEATINGLOAD",
    "PLANTEQUIPMENTOPERATION:COOLLINGRNG",
    "PLANTEQUIPMENTOPERATION:HEATINGRNG",
    "PLANTEQUIPMENTOPERATION:UNCONTROLLED",
    "PLANTEQUIPMENTOPERATIONSCHEMES",
    "CONDENSEREQUIPMENTOPERATIONSCHEMES",
    # Branch and connector objects
    "BRANCHLIST",
    "BRANCH",
    "CONNECTORLIST",
    "CONNECTOR:SPLITTER",
    "CONNECTOR:MIXER",
    # Availability managers
    "AVAILABILITYMANAGER:SCHEDULED",
    "AVAILABILITYMANAGER:NIGHTCYCLE",
    "AVAILABILITYMANAGERASSIGNMENTLIST",
    # Sizing objects (not needed for IdealLoads run)
    "SIZING:SYSTEM",
    "SIZING:PLANT",
    # Outdoor air system objects
    "OUTDOORAIR:NODE",
    "OUTDOORAIR:NODELIST",
    "OUTDOORAIR:MIXER",
    # Node lists (re-added for IdealLoads)
    "NODELIST",
    # Daylighting (not needed for load extraction; references zone air nodes in some versions)
    "DAYLIGHTING:CONTROLS",
    "DAYLIGHTING:REFERENCEPOINT",
    "DAYLIGHTING:DESERV",
    # PV / generator system (unrelated to HVAC loads; causes warnings about availability)
    "GENERATOR:PVWATTS",
    "GENERATOR:WINDTURBINE",
    "ELECTRICLOADCENTER:DISTRIBUTION",
    "ELECTRICLOADCENTER:GENERATORS",
    "ELECTRICLOADCENTER:INVERTER:PVWATTS",
    "ELECTRICLOADCENTER:INVERTER:SIMPLE",
    "ELECTRICLOADCENTER:INVERTER:FUNCTIONOFPOWER",
    # Sizing objects (we disable system/plant sizing; these reference removed air loops)
    "SIZINGPERIOD:DESIGNDAY",
    "SIZINGPERIOD:WEATHERFILEDAYS",
    "SIZING:ZONE",
    "SIZING:PARAMETERS",
    "DESIGNSPECIFICATION:OUTDOORAIR",
    "DESIGNSPECIFICATION:ZONEAIRDISTRIBUTION",
    "RUNPERIODCONTROL:DAYLIGHTSAVINGTIME",
    "RUNPERIODCONTROL:SPECIALDAYS",
    # Orphaned performance curves (coils were removed)
    "CURVE:BIQUADRATIC",
    "CURVE:QUADRATIC",
    "CURVE:CUBIC",
    "CURVE:LINEAR",
    "CURVE:BICUBIC",
    "CURVE:EXPONENT",
    "CURVE:QUARTIC",
    # Custom meters that reference removed HVAC output variables (cause EnergyPlus segfault)
    "METER:CUSTOM",
    "METER:CUSTOMDECREMENT",
    # Electric load center transformer (connected to PV/generator which is removed)
    "ELECTRICLOADCENTER:TRANSFORMER",
    # Unnecessary output control objects
    "OUTPUT:VARIABLEDICTIONARY",
    "OUTPUT:SURFACES:DRAWING",
    "OUTPUT:SURFACES:LIST",
    "OUTPUT:CONSTRUCTIONS",
    # EMS objects that actuate original HVAC setpoints (no longer exist)
    "ENERGYMANAGEMENTSYSTEM:ACTUATOR",
    "ENERGYMANAGEMENTSYSTEM:SENSOR",
    "ENERGYMANAGEMENTSYSTEM:PROGRAM",
    "ENERGYMANAGEMENTSYSTEM:SUBROUTINE",
    "ENERGYMANAGEMENTSYSTEM:PROGRAMCALLINGMANAGER",
    "ENERGYMANAGEMENTSYSTEM:INTERNALVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:GLOBALVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:OUTPUTVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:METEREDOUTPUTVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:TRENDSENSOR",
    "ENERGYMANAGEMENTSYSTEM:CURVEORTHOGONALPOLYNOMIAL",
    # Refrigeration systems (restaurants/groceries; compressor rack nodes conflict
    # with IdealLoads air node setup — strip entirely, loads appear as internal gains)
    "REFRIGERATION:COMPRESSORRACK",
    "REFRIGERATION:CASE",
    "REFRIGERATION:WALKIN",
    "REFRIGERATION:CASEANDWALKINLIST",
    "REFRIGERATION:SYSTEM",
    "REFRIGERATION:TRANSCRITICALSYSTEM",
    "REFRIGERATION:SECONDARYSYSTEM",
    "REFRIGERATION:AIRCOOLEDCONDENSER",
    "REFRIGERATION:CONDENSERAIRCOOLEDSHELLANDINTUBESIMPLE",
    "REFRIGERATION:COMPRESSOR",
    "REFRIGERATION:COMPRESSORLIST",
    "REFRIGERATION:SUBCOOLER",
    "REFRIGERATION:GAS COOLER:AIRCOOLED",
}


# ─────────────────────────────────────────────────────────────────────────────
# IDF preparation
# ─────────────────────────────────────────────────────────────────────────────

def load_idf(idf_path: pathlib.Path, idd_path: pathlib.Path) -> "eppy.modeleditor.IDF":
    """Load an EnergyPlus IDF file using eppy.

    Pre-strips object types that cause eppy 0.5.63 to crash due to extensible
    field handling bugs (e.g. AirLoopHVAC:UnitaryHeatPump:WaterToAir in large
    office IDFs).  These objects are removed from the HVAC strip pass anyway, so
    stripping them in the raw text before eppy sees the file is safe.
    """
    try:
        from eppy.modeleditor import IDF
    except ImportError:
        sys.exit("ERROR: eppy not installed.  Run: pip install eppy")

    raw = idf_path.read_text(encoding="utf-8", errors="replace")
    raw = _strip_eppy_crash_objects(raw)

    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".idf", delete=False,
        encoding="utf-8", dir=idf_path.parent,
    )
    try:
        tmp.write(raw)
        tmp.close()
        IDF.setiddname(str(idd_path))
        idf = IDF(tmp.name)
    finally:
        os.unlink(tmp.name)
    return idf


_EPPY_CRASH_TYPES = {
    "AirLoopHVAC:UnitaryHeatPump:WaterToAir",
    "AirLoopHVAC:UnitaryHeatPump:AirToAir:MultiSpeed",
}


def _strip_eppy_crash_objects(idf_text: str) -> str:
    """Remove IDF object blocks whose type is known to crash eppy 0.5.63.

    Parses top-level comma/semicolon-delimited object blocks and drops any
    whose first token matches a type in _EPPY_CRASH_TYPES.
    """
    import re
    # Split on semicolons that terminate top-level objects.
    # Each segment is one IDF object declaration (may span lines).
    segments = re.split(r';', idf_text)
    kept = []
    for seg in segments:
        # First non-blank, non-comment token is the object type.
        # Strip inline comments (!...) per line before checking.
        clean = re.sub(r'!.*', '', seg)
        tokens = re.split(r'[\s,]+', clean.strip())
        obj_type = tokens[0] if tokens else ""
        if obj_type in _EPPY_CRASH_TYPES:
            continue
        kept.append(seg)
    return ";".join(kept)


def get_zone_names(idf) -> list[str]:
    """Return conditioned zone names — zones that have a ZoneControl:Thermostat.

    Unconditioned zones (Attic, Plenum, crawlspace) have no thermostat in DOE
    prototype IDFs and must not receive a ZoneHVAC:IdealLoadsAirSystem, which
    requires a thermostat to determine heating/cooling demand.
    """
    thermostats = idf.idfobjects.get("ZONECONTROL:THERMOSTAT", [])
    conditioned = {t.Zone_or_ZoneList_Name for t in thermostats}

    if not conditioned:
        # Fallback: all zones (no thermostat objects found — minimal IDF case)
        all_zones = [z.Name for z in idf.idfobjects["ZONE"]]
        if not all_zones:
            raise ValueError("IDF contains no Zone objects.  Check the file.")
        return all_zones

    # Preserve the order zones appear in the IDF
    return [z.Name for z in idf.idfobjects["ZONE"] if z.Name in conditioned]


def compute_floor_area_m2(idf) -> float:
    """Estimate total conditioned floor area [m²] from floor surfaces.

    Floor surfaces in EnergyPlus have Surface_Type = 'Floor' and
    Outside_Boundary_Condition = 'Ground' or 'GroundFCfactorMethod'
    or 'OtherSideCoefficients', or they are interior floors with
    Outside_Boundary_Condition = 'Surface'.

    We sum the area of all surfaces with Surface_Type = 'Floor'.
    """
    total = 0.0
    for surf in idf.idfobjects["BUILDINGSURFACE:DETAILED"]:
        if surf.Surface_Type.strip().lower() == "floor":
            verts = surf.coords  # list of (x, y, z) tuples from eppy
            total += _polygon_area(verts)
    return total


def _polygon_area(coords: list) -> float:
    """Area of a 3-D planar polygon via the cross-product method."""
    if len(coords) < 3:
        return 0.0
    # Shoelace on the projected plane (works for horizontal surfaces)
    n = len(coords)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]
    return abs(area) / 2.0


def scale_geometry(idf, scale_factor: float) -> None:
    """Scale all building surface vertices by sqrt(scale_factor) in X and Y.

    A uniform X-Y scale of s changes every zone floor area by s², so setting
    s = sqrt(target_area / prototype_area) gives the correct total floor area
    while preserving the building aspect ratio.

    Window-to-wall ratios and relative zone sizes remain unchanged.
    """
    s = math.sqrt(scale_factor)
    for surf in idf.idfobjects["BUILDINGSURFACE:DETAILED"]:
        new_coords = [(x * s, y * s, z) for x, y, z in surf.coords]
        surf.setcoords(new_coords)
    for surf in idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]:
        new_coords = [(x * s, y * s, z) for x, y, z in surf.coords]
        surf.setcoords(new_coords)
    # Shading surfaces (overhangs, fins, site shading)
    for surf in idf.idfobjects.get("SHADING:SITE:DETAILED", []):
        new_coords = [(x * s, y * s, z) for x, y, z in surf.coords]
        surf.setcoords(new_coords)
    for surf in idf.idfobjects.get("SHADING:BUILDING:DETAILED", []):
        new_coords = [(x * s, y * s, z) for x, y, z in surf.coords]
        surf.setcoords(new_coords)


def scale_internal_loads(idf, scale_factor: float) -> None:
    """Scale absolute-wattage internal load objects by scale_factor.

    DOE prototypes use either Watts/Area or LightingLevel calculation methods.
    - Watts/Area → no change needed (density is per unit area; area scales automatically)
    - LightingLevel (absolute W) → must multiply by scale_factor
    - People with absolute count → multiply by scale_factor
    - ElectricEquipment with EquipmentLevel → multiply by scale_factor
    """
    for obj in idf.idfobjects["LIGHTS"]:
        method = obj.Design_Level_Calculation_Method.strip().lower()
        if method in ("lightinglevel", "lighting level"):
            try:
                obj.Lighting_Level = float(obj.Lighting_Level) * scale_factor
            except (ValueError, AttributeError):
                pass

    for obj in idf.idfobjects["ELECTRICEQUIPMENT"]:
        method = obj.Design_Level_Calculation_Method.strip().lower()
        if method in ("equipmentlevel", "equipment level"):
            try:
                obj.Design_Level = float(obj.Design_Level) * scale_factor
            except (ValueError, AttributeError):
                pass

    for obj in idf.idfobjects["PEOPLE"]:
        method = obj.Number_of_People_Calculation_Method.strip().lower()
        if method in ("people", "numberofpeople", "number of people"):
            try:
                obj.Number_of_People = float(obj.Number_of_People) * scale_factor
            except (ValueError, AttributeError):
                pass


def remove_hvac_objects(idf) -> int:
    """Remove all HVAC system objects from the IDF.

    Uses eppy's removeidfobject() — the correct API for mutating the
    internal IDF object tree (direct list slice-assignment does not
    propagate to eppy's bunch_dt internals).

    Returns the count of objects removed.
    """
    removed = 0
    for cls in _HVAC_CLASSES_TO_REMOVE:
        try:
            objs = list(idf.idfobjects[cls])  # copy; list shrinks as we remove
        except (KeyError, TypeError):
            continue
        for obj in objs:
            try:
                idf.removeidfobject(obj)
                removed += 1
            except Exception:
                pass
    return removed


def get_zone_air_nodes(idf) -> dict[str, str]:
    """Extract zone → zone_air_node_name mapping from existing EquipmentConnections.

    Must be called BEFORE remove_hvac_objects() so the original connections are
    still present.  The zone air node is referenced by thermostats and sizing
    objects throughout the IDF; new EquipmentConnections must reuse the same name.
    """
    mapping: dict[str, str] = {}
    for conn in idf.idfobjects.get("ZONEHVAC:EQUIPMENTCONNECTIONS", []):
        zone = conn.Zone_Name.strip()
        node = conn.Zone_Air_Node_Name.strip()
        if zone and node:
            mapping[zone] = node
    return mapping


def add_ideal_loads_hvac(idf, zone_names: list[str],
                         zone_air_nodes: dict[str, str] | None = None) -> None:
    """Add ZoneHVAC:IdealLoadsAirSystem infrastructure to every zone.

    For each zone this creates:
      - ZoneHVAC:IdealLoadsAirSystem  (the ideal system object)
      - ZoneHVAC:EquipmentList        (lists the ideal system as zone equipment)
      - ZoneHVAC:EquipmentConnections (connects zone to supply air node)

    zone_air_nodes : dict mapping zone name → existing zone air node name,
        extracted from the prototype by get_zone_air_nodes() before HVAC removal.
        If absent, falls back to constructing a name from the zone name.

    The thermostat (ZoneControl:Thermostat + ThermostatSetpoint:DualSetpoint)
    already exists in the DOE prototype IDF and is left unchanged.

    Supply air temperature limits follow ASHRAE 90.1-2019 Table G3.1.2.8:
      Heating supply air: 50°C (122°F)
      Cooling supply air: 13°C (55.4°F)

    Reference: EnergyPlus Input-Output Reference, sec. 1.36.
    """
    if zone_air_nodes is None:
        zone_air_nodes = {}

    for zone in zone_names:
        supply_node = f"{zone} IdealLoads Supply Air Node"
        equip_name  = f"{zone} IdealLoads"
        equip_list  = f"{zone} IdealLoads Equipment List"
        zone_air_node = zone_air_nodes.get(zone, f"{zone} Zone Air Node")

        # ZoneHVAC:IdealLoadsAirSystem
        ideal = idf.newidfobject("ZONEHVAC:IDEALLOADSAIRSYSTEM")
        ideal.Name = equip_name
        ideal.Zone_Supply_Air_Node_Name = supply_node
        # Availability: always on (blank = Schedule:Always_On built-in)
        ideal.Availability_Schedule_Name = ""
        # Supply air temperature limits (ASHRAE 90.1-2019 G3.1.2.8)
        ideal.Maximum_Heating_Supply_Air_Temperature = 50.0   # °C
        ideal.Minimum_Cooling_Supply_Air_Temperature = 13.0   # °C
        # Humidity limits — let EnergyPlus use defaults (no override)
        ideal.Maximum_Heating_Supply_Air_Humidity_Ratio = ""
        ideal.Minimum_Cooling_Supply_Air_Humidity_Ratio = ""
        # Capacity limits — none (ideal = unlimited capacity)
        ideal.Heating_Limit = "NoLimit"
        ideal.Cooling_Limit = "NoLimit"
        # No outdoor air — empty string means OA is excluded from the supply
        # stream.  In a WSHP+DOAS system the DOAS handles ventilation; the
        # ground loop only serves zone space loads.  This is intentional and
        # correct for borefield sizing.
        ideal.Design_Specification_Outdoor_Air_Object_Name = ""
        # No heat recovery on the WSHP terminal unit (DOAS has its own ERV).
        ideal.Heat_Recovery_Type = "None"

        # ZoneHVAC:EquipmentList
        equip_list_obj = idf.newidfobject("ZONEHVAC:EQUIPMENTLIST")
        equip_list_obj.Name = equip_list
        equip_list_obj.Zone_Equipment_1_Object_Type = "ZoneHVAC:IdealLoadsAirSystem"
        equip_list_obj.Zone_Equipment_1_Name = equip_name
        equip_list_obj.Zone_Equipment_1_Cooling_Sequence = 1
        equip_list_obj.Zone_Equipment_1_Heating_or_NoLoad_Sequence = 1

        return_node = f"{zone} Return Air Node"

        # ZoneHVAC:EquipmentConnections
        conn = idf.newidfobject("ZONEHVAC:EQUIPMENTCONNECTIONS")
        conn.Zone_Name = zone
        conn.Zone_Conditioning_Equipment_List_Name = equip_list
        conn.Zone_Air_Inlet_Node_or_NodeList_Name = supply_node
        conn.Zone_Air_Exhaust_Node_or_NodeList_Name = ""
        conn.Zone_Air_Node_Name = zone_air_node
        conn.Zone_Return_Air_Node_or_NodeList_Name = return_node


def add_output_variables(idf, zone_names: list[str]) -> None:
    """Add hourly Output:Variable requests for IdealLoads thermal energy.

    Requested variables (Joules per hour, converted to W in parsing):
      Zone Ideal Loads Zone Total Heating Energy — zone heating demand [J]
      Zone Ideal Loads Zone Total Cooling Energy — zone cooling demand [J]

    "Zone Total" includes both sensible and latent contributions, which is
    correct for ground-loop sizing (the heat pump handles all of it).

    In EnergyPlus 26.1 the old *Rate [W] variables no longer exist;
    the equivalent energy [J] variables are divided by 3600 in parsing
    to recover the hourly-average power in Watts.

    Reference: EnergyPlus I/O Reference, ZoneHVAC:IdealLoadsAirSystem outputs.
    """
    # Remove any existing Output:Variable objects to avoid duplicates
    for obj in list(idf.idfobjects.get("OUTPUT:VARIABLE", [])):
        try:
            idf.removeidfobject(obj)
        except Exception:
            pass

    for var_name in [
        "Zone Ideal Loads Zone Total Heating Energy",
        "Zone Ideal Loads Zone Total Cooling Energy",
    ]:
        ov = idf.newidfobject("OUTPUT:VARIABLE")
        ov.Key_Value = "*"          # all zones
        ov.Variable_Name = var_name
        ov.Reporting_Frequency = "Hourly"

    # Also request zone air temperature for diagnostic validation
    ov = idf.newidfobject("OUTPUT:VARIABLE")
    ov.Key_Value = "*"
    ov.Variable_Name = "Zone Mean Air Temperature"
    ov.Reporting_Frequency = "Hourly"


def set_run_period_annual(idf) -> None:
    """Ensure the simulation runs the full calendar year (Jan 1 – Dec 31).

    DOE prototypes typically already have a full-year RunPeriod, but
    this is set explicitly to guarantee 8,760 output rows.
    """
    periods = idf.idfobjects["RUNPERIOD"]
    if not periods:
        rp = idf.newidfobject("RUNPERIOD")
    else:
        rp = periods[0]
    rp.Name = "Annual"
    rp.Begin_Month = 1
    rp.Begin_Day_of_Month = 1
    rp.End_Month = 12
    rp.End_Day_of_Month = 31
    rp.Day_of_Week_for_Start_Day = "Sunday"
    rp.Use_Weather_File_Holidays_and_Special_Days = "Yes"
    rp.Use_Weather_File_Daylight_Saving_Period = "Yes"
    rp.Apply_Weekend_Holiday_Rule = "No"
    rp.Use_Weather_File_Rain_Indicators = "Yes"
    rp.Use_Weather_File_Snow_Indicators = "Yes"


def patch_v22_compat(idf) -> None:
    """Fix field values that changed between EnergyPlus 22.1 (DOE prototype IDF
    version) and 26.1 (our installed version).

    DOE ASHRAE 90.1-2022 prototype IDFs are stamped Version 22.1.  Running them
    under EnergyPlus 26.1 fails on enum values that were renamed.  This function
    patches the known breaking changes so the simulation can proceed without
    running the full transition tool chain.

    Changes applied:
      • People: Mean_Radiant_Temperature_Calculation_Type
          "ZoneAveraged" → "EnclosureAveraged"  (changed in 23.2→24.1 transition)
    """
    for person in idf.idfobjects.get("PEOPLE", []):
        val = getattr(person, "Mean_Radiant_Temperature_Calculation_Type", "").strip()
        if val.lower() == "zoneaveraged":
            person.Mean_Radiant_Temperature_Calculation_Type = "EnclosureAveraged"


def patch_simulation_control(idf) -> None:
    """Configure SimulationControl for an IdealLoads-only annual run.

    IdealLoads replaces all air loops and plant loops.  System and plant sizing
    calculations require those loops and will fail (or produce misleading results)
    without them.  Zone sizing is kept because it's needed by IdealLoads for
    design-day airflow calculations.
    """
    for sc in idf.idfobjects.get("SIMULATIONCONTROL", []):
        sc.Do_System_Sizing_Calculation = "No"
        sc.Do_Plant_Sizing_Calculation  = "No"
        # Keep zone sizing (Yes) and annual weather run (Yes)
        sc.Do_Zone_Sizing_Calculation                = "No"
        sc.Run_Simulation_for_Sizing_Periods         = "No"
        sc.Run_Simulation_for_Weather_File_Run_Periods = "Yes"
        sc.Do_HVAC_Sizing_Simulation_for_Sizing_Periods = "No"


def prepare_idf(
    src_idf_path: pathlib.Path,
    target_area_sqft: float,
    building_type: str,
    work_dir: pathlib.Path,
    idd_path: pathlib.Path,
) -> pathlib.Path:
    """Load, modify, and save a simulation-ready IDF.

    Steps:
      1. Load the prototype IDF.
      2. If target area != prototype area, scale geometry and internal loads.
      3. Remove all HVAC system objects.
      4. Add ZoneHVAC:IdealLoadsAirSystem for every zone.
      5. Add Output:Variable requests.
      6. Ensure full-year RunPeriod.
      7. Save the modified IDF to work_dir.

    Returns (path_to_modified_idf, zone_names_list).
    """
    idf = load_idf(src_idf_path, idd_path)

    proto_info = DOE_PROTOTYPES.get(building_type, {})
    proto_area_m2 = proto_info.get("floor_area_m2", None)

    target_area_m2 = target_area_sqft * 0.092903  # ft² → m²

    if proto_area_m2 and abs(target_area_m2 - proto_area_m2) / proto_area_m2 > 0.01:
        scale_factor = target_area_m2 / proto_area_m2
        print(f"  Scaling geometry: {proto_area_m2:.0f} m² → {target_area_m2:.0f} m² "
              f"(×{scale_factor:.3f})")
        scale_geometry(idf, scale_factor)
        scale_internal_loads(idf, scale_factor)
    else:
        print(f"  Using prototype geometry ({target_area_m2:.0f} m² ≈ prototype).")

    # Extract zone air node names BEFORE removing HVAC (they live in EquipmentConnections)
    zone_air_nodes = get_zone_air_nodes(idf)

    n_removed = remove_hvac_objects(idf)
    print(f"  Removed {n_removed} HVAC objects from prototype.")

    zone_names = get_zone_names(idf)
    print(f"  Zones ({len(zone_names)}): {zone_names}")

    add_ideal_loads_hvac(idf, zone_names, zone_air_nodes=zone_air_nodes)
    print(f"  Added ZoneHVAC:IdealLoadsAirSystem to {len(zone_names)} zones.")

    add_output_variables(idf, zone_names)
    set_run_period_annual(idf)
    patch_v22_compat(idf)
    patch_simulation_control(idf)

    work_dir.mkdir(parents=True, exist_ok=True)
    out_idf = work_dir / "simulation_ready.idf"
    idf.save(str(out_idf))
    # EP22 compat: EnclosureAveraged was renamed from ZoneAveraged after v23.2;
    # v22.1 only accepts ZoneAveraged.
    _t = out_idf.read_text()
    if "EnclosureAveraged" in _t:
        out_idf.write_text(_t.replace("EnclosureAveraged", "ZoneAveraged"))
    print(f"  Modified IDF saved → {out_idf}")
    return out_idf, zone_names


# ─────────────────────────────────────────────────────────────────────────────
# EnergyPlus execution
# ─────────────────────────────────────────────────────────────────────────────

def run_energyplus(
    idf_path: pathlib.Path,
    epw_path: pathlib.Path,
    output_dir: pathlib.Path,
    energyplus_dir: pathlib.Path = ENERGYPLUS_DIR,
) -> pathlib.Path:
    """Run EnergyPlus via the pyenergyplus Python API.

    The pyenergyplus module is bundled inside the EnergyPlus installation
    directory (it is NOT a separate pip package).  We add ENERGYPLUS_DIR to
    sys.path to import it, which is the standard approach documented at
    energyplus.net/documentation.

    Args:
        idf_path       : path to the prepared simulation-ready IDF
        epw_path       : path to the EPW weather file
        output_dir     : directory where EnergyPlus writes all output files
        energyplus_dir : root of the EnergyPlus installation

    Returns:
        output_dir (for caller convenience)

    Raises:
        SystemExit if EnergyPlus is not found or simulation fails.
    """
    import subprocess as _subprocess

    binary = energyplus_dir / "energyplus"
    if not binary.exists():
        sys.exit(
            f"ERROR: EnergyPlus binary not found at {binary}\n"
            f"Set the ENERGYPLUS_DIR environment variable to your install path.\n"
            f"Download: https://energyplus.net/downloads"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Running EnergyPlus simulation…")
    print(f"    IDF : {idf_path}")
    print(f"    EPW : {epw_path}")
    print(f"    OUT : {output_dir}")

    # Run EnergyPlus as an isolated subprocess so that repeated calls in the
    # same batch process do not accumulate in-process library state (which
    # caused SIGSEGV crashes with pyenergyplus after ~20+ simulations).
    cmd = [
        str(binary),
        "-d", str(output_dir),
        "-w", str(epw_path),
        "-r",           # post-process .eso → .csv automatically
        str(idf_path),
    ]
    result = _subprocess.run(cmd, capture_output=True)
    exit_code = result.returncode

    if exit_code != 0:
        err_file = output_dir / "eplusout.err"
        snippet = ""
        if err_file.exists():
            lines = err_file.read_text().splitlines()
            # show last 20 lines for diagnosis
            snippet = "\n".join(lines[-20:])
        sys.exit(
            f"ERROR: EnergyPlus exited with code {exit_code}\n"
            f"Last lines of eplusout.err:\n{snippet}"
        )

    print("  EnergyPlus simulation complete.")
    return output_dir


# ─────────────────────────────────────────────────────────────────────────────
# Output parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ideal_loads_csv(csv_path):
    """Parse eplusout.csv → (rows_heat, rows_cool) lists of floats in Joules."""
    import csv as _csv
    with csv_path.open(newline="") as f:
        reader = _csv.reader(f)
        headers = next(reader)
        heat_cols, cool_cols = [], []
        for i, h in enumerate(headers):
            hu = h.upper()
            if "ZONE IDEAL LOADS ZONE TOTAL HEATING ENERGY" in hu:
                heat_cols.append(i)
            elif "ZONE IDEAL LOADS ZONE TOTAL COOLING ENERGY" in hu:
                cool_cols.append(i)
        if not heat_cols:
            sys.exit("ERROR: No heating columns in eplusout.csv — check IdealLoads setup.")
        if not cool_cols:
            sys.exit("ERROR: No cooling columns in eplusout.csv — check IdealLoads setup.")
        print(f"  Found {len(heat_cols)} heating columns, {len(cool_cols)} cooling columns.")
        rows_heat, rows_cool = [], []
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                rows_heat.append(sum(float(row[i]) for i in heat_cols))
                rows_cool.append(sum(float(row[i]) for i in cool_cols))
            except (ValueError, IndexError):
                continue
    return rows_heat, rows_cool


def _parse_ideal_loads_eso(eso_path):
    """Parse eplusout.eso directly → (rows_heat, rows_cool) lists of floats in Joules.

    Used as fallback when ReadVarsESO cannot produce eplusout.csv (e.g. macOS
    Gatekeeper blocks the PostProcess/ReadVarsESO binary).
    """
    HEAT_KEY = "ZONE IDEAL LOADS ZONE TOTAL HEATING ENERGY"
    COOL_KEY = "ZONE IDEAL LOADS ZONE TOTAL COOLING ENERGY"

    heat_codes, cool_codes = set(), set()
    rows_heat, rows_cool = [], []
    in_dict = True
    hour_heat = hour_cool = 0.0
    in_hour = False

    with eso_path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line == "End of Data Dictionary":
                in_dict = False
                continue
            if line == "End of Data":
                if in_hour:
                    rows_heat.append(hour_heat)
                    rows_cool.append(hour_cool)
                break
            if in_dict:
                parts = line.split(",", 2)
                if len(parts) >= 3:
                    code = parts[0].strip()
                    desc = parts[2].upper()
                    if HEAT_KEY in desc:
                        heat_codes.add(code)
                    elif COOL_KEY in desc:
                        cool_codes.add(code)
            else:
                code = line.split(",", 1)[0]
                if code == "2":
                    # Hourly timestamp — save previous hour, start new
                    if in_hour:
                        rows_heat.append(hour_heat)
                        rows_cool.append(hour_cool)
                    hour_heat = hour_cool = 0.0
                    in_hour = True
                elif code in heat_codes:
                    try:
                        hour_heat += float(line.split(",", 1)[1])
                    except (ValueError, IndexError):
                        pass
                elif code in cool_codes:
                    try:
                        hour_cool += float(line.split(",", 1)[1])
                    except (ValueError, IndexError):
                        pass

    print(f"  Parsed ESO: {len(rows_heat)} hours, "
          f"{len(heat_codes)} heat vars, {len(cool_codes)} cool vars.")
    return rows_heat, rows_cool


def parse_ideal_loads_output(
    output_dir: pathlib.Path,
    zone_names: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Parse the EnergyPlus output CSV and return building-total Q_heat and Q_cool.

    EnergyPlus writes hourly Output:Variable results to eplusout.csv when the
    -r flag is used (ReadVarsESO post-processing).

    Column headers have the format (EnergyPlus 26.1):
      "{Zone Name}:Zone Ideal Loads Zone Total Heating Energy [J](Hourly)"

    Values are in Joules per hour and are divided by 3600 to yield the
    hourly-average power in Watts.

    We sum across all zones to obtain the whole-building demand.

    Args:
        output_dir : directory containing eplusout.csv
        zone_names : list of zone names from the IDF

    Returns:
        q_heat_W : (8760,) float64 array, whole-building heating demand [W]
        q_cool_W : (8760,) float64 array, whole-building cooling demand [W]
                   (positive = cooling load)
    """
    import csv as _csv

    csv_path = output_dir / "eplusout.csv"
    eso_path = output_dir / "eplusout.eso"

    if csv_path.exists():
        rows_heat, rows_cool = _parse_ideal_loads_csv(csv_path)
    elif eso_path.exists():
        # ponytail: ReadVarsESO may be blocked by macOS Gatekeeper; parse ESO directly
        print("  eplusout.csv not found — parsing eplusout.eso directly")
        rows_heat, rows_cool = _parse_ideal_loads_eso(eso_path)
    else:
        sys.exit(
            f"ERROR: Neither eplusout.csv nor eplusout.eso found in {output_dir}\n"
            "Ensure EnergyPlus completed successfully."
        )

    q_heat = np.array(rows_heat, dtype=np.float64)
    q_cool = np.array(rows_cool, dtype=np.float64)

    if len(q_heat) not in (8760, 8784):
        print(f"  WARNING: Expected 8760 or 8784 rows, got {len(q_heat)}. "
              f"Check RunPeriod.")

    # Convert from Joules/hour to average Watts (÷ 3600 s/h).
    # EnergyPlus reports cooling load as positive (heat removed from zone).
    # Return both as positive Watts for consistency.
    J_PER_WH = 3600.0
    return q_heat / J_PER_WH, q_cool / J_PER_WH


def save_outputs(
    q_heat: np.ndarray,
    q_cool: np.ndarray,
    out_dir: pathlib.Path,
    label: str,
) -> None:
    """Save Q_heat and Q_cool as .npy arrays and a human-readable CSV."""
    out_dir.mkdir(parents=True, exist_ok=True)

    np.save(str(out_dir / f"{label}_q_heat_W.npy"), q_heat)
    np.save(str(out_dir / f"{label}_q_cool_W.npy"), q_cool)

    # CSV with both columns for inspection
    import csv as _csv
    csv_path = out_dir / f"{label}_loads_hourly.csv"
    with csv_path.open("w", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(["hour", "q_heat_W", "q_cool_W"])
        for h, (qh, qc) in enumerate(zip(q_heat, q_cool), start=1):
            writer.writerow([h, round(qh, 1), round(qc, 1)])

    peak_heat = q_heat.max()
    peak_cool = q_cool.max()
    ann_heat  = q_heat.sum() / 1000  # kWh
    ann_cool  = q_cool.sum() / 1000  # kWh

    print(f"\n  Results saved to {out_dir}/")
    print(f"  Peak heating: {peak_heat/1000:.1f} kW")
    print(f"  Peak cooling: {peak_cool/1000:.1f} kW")
    print(f"  Annual heating: {ann_heat:.0f} kWh")
    print(f"  Annual cooling: {ann_cool:.0f} kWh")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="EnergyPlus IdealLoads 8760-hour load profile generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--idf", required=True, type=pathlib.Path,
        help="Path to DOE prototype IDF (download from energycodes.gov/prototype-building-models)",
    )
    p.add_argument(
        "--epw", required=True, type=pathlib.Path,
        help="Path to EnergyPlus weather file (.epw, download from energyplus.net/weather)",
    )
    p.add_argument(
        "--area", type=float, default=None,
        help="Target floor area in square feet. "
             "Omit to use the prototype's reference area.",
    )
    p.add_argument(
        "--building-type", default="SmallOffice",
        choices=list(DOE_PROTOTYPES.keys()),
        help="DOE prototype building type (default: SmallOffice)",
    )
    p.add_argument(
        "--out", type=pathlib.Path,
        default=ROOT / "outputs" / "energyplus_loads",
        help="Directory for output files (numpy arrays + CSV)",
    )
    p.add_argument(
        "--energyplus-dir", type=pathlib.Path, default=ENERGYPLUS_DIR,
        help=f"EnergyPlus installation directory (default: {ENERGYPLUS_DIR})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    idf_path = args.idf.resolve()
    epw_path = args.epw.resolve()

    if not idf_path.exists():
        sys.exit(f"ERROR: IDF not found: {idf_path}")
    if not epw_path.exists():
        sys.exit(f"ERROR: EPW not found: {epw_path}")

    proto = DOE_PROTOTYPES.get(args.building_type, {})
    target_area = args.area if args.area is not None else proto.get("floor_area_sqft", 5502)

    area_label = f"{int(target_area)}sqft"
    label = f"{args.building_type}_{area_label}"
    work_dir = CACHE_DIR / f"work_{label}"

    print(f"\n{'='*60}")
    print(f"  Building type : {args.building_type}")
    print(f"  {proto.get('description', '')}")
    print(f"  Target area   : {target_area:,.0f} sq ft  "
          f"({target_area * 0.092903:.0f} m²)")
    print(f"  Weather file  : {epw_path.name}")
    print(f"{'='*60}\n")

    idd_path = args.energyplus_dir / "Energy+.idd"
    if not idd_path.exists():
        sys.exit(
            f"ERROR: Energy+.idd not found at {idd_path}\n"
            f"Check that ENERGYPLUS_DIR ({args.energyplus_dir}) points to "
            "your EnergyPlus installation."
        )

    print("[1/4] Preparing IDF…")
    ready_idf, zone_names = prepare_idf(
        src_idf_path=idf_path,
        target_area_sqft=target_area,
        building_type=args.building_type,
        work_dir=work_dir,
        idd_path=idd_path,
    )

    print("\n[2/4] Running EnergyPlus…")
    ep_output_dir = work_dir / "ep_output"
    run_energyplus(
        idf_path=ready_idf,
        epw_path=epw_path,
        output_dir=ep_output_dir,
        energyplus_dir=args.energyplus_dir,
    )

    print("\n[3/4] Parsing outputs…")
    q_heat, q_cool = parse_ideal_loads_output(ep_output_dir, zone_names)
    print(f"  Output length: {len(q_heat)} hours")

    print("\n[4/4] Saving results…")
    save_outputs(q_heat, q_cool, args.out, label)

    print(f"\nDone.  Load profile ready for GHEtool / load duration curve analysis.")
    print(f"  q_heat_W  → {args.out}/{label}_q_heat_W.npy")
    print(f"  q_cool_W  → {args.out}/{label}_q_cool_W.npy")


if __name__ == "__main__":
    main()
