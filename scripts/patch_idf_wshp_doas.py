#!/usr/bin/env python3
"""
scripts/patch_idf_wshp_doas.py
───────────────────────────────────────────────────────────────────────────────
Patch DOE prototype IDFs to use WSHP+DOAS instead of VAV+chiller+boiler.

Replaces the prototype's VAV air-loop HVAC with:
  - ZoneHVAC:WaterToAirHeatPump (one per conditioned zone)
  - A neutral condenser water loop (proxy for the ground loop, 20°C setpoint)
  - A simplified DOAS ventilation air handler

Output variable added per zone:
  "Water To Air Heat Pump Source Side Heat Transfer Rate" [W]
  Positive = heat injection (cooling mode)
  Negative = heat extraction (heating mode)

Usage:
    python scripts/patch_idf_wshp_doas.py --building medium_office --city Buffalo
    python scripts/patch_idf_wshp_doas.py --building medium_office --city Miami
    python scripts/patch_idf_wshp_doas.py --all   # all test cases

Output: data/wshp_idfs/{building}_{city}_wshp.idf  (ready for EnergyPlus -x)

Note: Requires EnergyPlus ExpandObjects to expand HVACTemplate objects.
      The companion run script (run_energyplus_wshp_validation.py) handles this.
"""

import argparse
import pathlib
import re
import sys

ROOT      = pathlib.Path(__file__).parent.parent
PROTO_DIR = ROOT / "data" / "doe_prototypes"
OUT_DIR   = ROOT / "data" / "wshp_idfs"

# Prototype IDF directory stem and city-to-filename mapping
PROTO_MAP = {
    "medium_office": "ASHRAE901_OfficeMedium_STD2022",
    "large_office":  "ASHRAE901_OfficeLarge_STD2022",
    "small_office":  "ASHRAE901_OfficeSmall_STD2022",
    "hospital":      "ASHRAE901_Hospital_STD2022",
    "secondary_school": "ASHRAE901_SchoolSecondary_STD2022",
    "primary_school":   "ASHRAE901_SchoolPrimary_STD2022",
}

# HVAC object type prefixes to strip (air loops, chillers, boilers, cooling towers)
# Leaves behind: Zone, BuildingSurface, Fenestration, Thermostat, Schedules, etc.
_STRIP_TYPES = {
    "AIRLOOPHVAC",
    "AIRLOOPHVAC:CONTROLLERLIST",
    "AIRLOOPHVAC:OUTDOORAIRSYSTEM",
    "AIRLOOPHVAC:OUTDOORAIRSYSTEM:EQUIPMENTLIST",
    "AIRLOOPHVAC:RETURNPLENUM",
    "AIRLOOPHVAC:SUPPLYPLENUM",
    "AIRLOOPHVAC:RETURNPATH",
    "AIRLOOPHVAC:SUPPLYPATH",
    "AIRLOOPHVAC:ZONESPLITTER",
    "AIRLOOPHVAC:ZONEMIXER",
    "WATERUSE:CONNECTIONS",
    "WATERUSE:EQUIPMENT",
    "AIRLOOPHVAC:UNITARYSYSTEM",
    "AVAILABILITYMANAGER:SCHEDULED",
    "AVAILABILITYMANAGERASSIGNMENTLIST",
    "BRANCH",
    "BRANCHLIST",
    "CHILLER:ELECTRIC:EIR",
    "CHILLER:ELECTRIC:REFORMULATEDEIR",
    "CHILLERHEATER:ABSORPTION:DIRECTFIRED",
    "COIL:COOLING:WATER",
    "COIL:COOLING:DX:SINGLESPEED",
    "COIL:COOLING:DX:TWOSPEED",
    "COIL:COOLING:DX:VARIABLESPEED",
    "COIL:HEATING:WATER",
    "COIL:HEATING:GAS",
    "COIL:HEATING:ELECTRIC",
    "COIL:HEATING:DX:SINGLESPEED",
    "COIL:WATERHEATING:AIRTOWATERHEATPUMP:PUMPED",
    "COIL:HEATING:FUEL",
    # WaterToAirHeatPump equation-fit coils from prototype data-center CRAC units
    # (large_office). Our _build_wshp_objects appends new ones AFTER stripping, so
    # stripping here removes only the orphaned data-center coils.
    "COIL:COOLING:WATERTOAIRHEATPUMP:EQUATIONFIT",
    "COIL:HEATING:WATERTOAIRHEATPUMP:EQUATIONFIT",
    "COILSYSTEM:COOLING:DX",
    "COILSYSTEM:COOLING:WATER",
    "COILSYSTEM:HEATING:DX",
    "CONNECTOR:MIXER",
    "CONNECTOR:SPLITTER",
    "CONNECTORLIST",
    "CONTROLLER:OUTDOORAIR",
    "CONTROLLER:WATERCOIL",
    "COOLINGTOWER:SINGLESPEED",
    "COOLINGTOWER:TWOSPEED",
    "COOLINGTOWER:VARIABLESPEED",
    "CURVE:BIQUADRATIC",
    "CURVE:CUBIC",
    "CURVE:EXPONENT",
    "CURVE:QUADRATIC",
    "CURVE:QUARTIC",
    "CURVE:QUADLINEAR",
    "CURVE:QUINTLINEAR",
    "DISTRICTCOOLING",
    "DISTRICTHEATING",
    "SETPOINTMANAGER:SCHEDULED:DUALSETPOINT",
    "PLANTCOMPONENT:TEMPERATURESOURCE",
    "SIZING:PLANT",
    # DESIGNSPECIFICATION:OUTDOORAIR — keep from prototype; needed by Sizing:Zone for autosizing
    "DUCT",
    "FAN:CONSTANTVOLUME",
    "FAN:ONOFF",
    "FAN:VARIABLEVOLUME",
    "HEATEXCHANGER:AIRTOAIR:SENSIBLEANDLATENT",
    "HUMIDIFIER:STEAM:ELECTRIC",
    "OUTDOORAIR:MIXER",
    "OUTDOORAIR:NODELIST",
    "PIPE:ADIABATIC",
    "CONDENSEREQUIPMENTLIST",
    "CONDENSEREQUIPMENTOPERATIONSCHEMES",
    "CONDENSERLOOP",
    "PLANTEQUIPMENTLIST",
    "PLANTEQUIPMENTOPERATION:COOLINGLOAD",
    "PLANTEQUIPMENTOPERATION:HEATINGLOAD",
    "PLANTEQUIPMENTOPERATION:UNCONTROLLED",
    "PLANTEQUIPMENTOPERATIONSCHEMES",
    "PLANTLOOP",
    "PUMP:CONSTANTSPEED",
    "PUMP:VARIABLESPEED",
    "SETPOINTMANAGER:FOLLOWOUTDOORAIRTEMPERATURE",
    "SETPOINTMANAGER:MIXEDAIR",
    "SETPOINTMANAGER:OUTDOORAIRRESET",
    "SETPOINTMANAGER:SCHEDULED",
    "SETPOINTMANAGER:SINGLEZONE:REHEAT",
    "SETPOINTMANAGER:WARMEST",
    "SETPOINTMANAGER:COLDEST",
    "SETPOINTMANAGER:RETURNAIRBYPASSFLOW",
    "SETPOINTMANAGER:SINGLEZONE:COOLING",
    "SETPOINTMANAGER:SINGLEZONE:HEATING",
    "SETPOINTMANAGER:SINGLEZONE:HUMIDITY:MINIMUM",
    "SETPOINTMANAGER:SINGLEZONE:HUMIDITY:MAXIMUM",
    "SETPOINTMANAGER:MULTIZONE:COOLING:AVERAGE",
    "SETPOINTMANAGER:MULTIZONE:HEATING:AVERAGE",
    "SETPOINTMANAGER:MULTIZONE:MINIMUMHUMIDITY:AVERAGE",
    "SETPOINTMANAGER:MULTIZONE:MAXIMUMHUMIDITY:AVERAGE",
    "SETPOINTMANAGER:OUTDOORAIRPRETREAT",
    "SETPOINTMANAGER:RETURNTEMPERATURE:HOTWATER",
    "SETPOINTMANAGER:RETURNTEMPERATURE:CHILLEDWATER",
    "SIZING:PLANT",
    "SIZING:SYSTEM",
    "UNITARYSYSTEMPERFORMANCE:MULTISPEED",
    "CONTROLLER:MECHANICALVENTILATION",
    # Refrigeration — commercial refrigeration equipment (schools, restaurants)
    # These reference Curve:Quadratic etc. that we strip; easier to drop the whole system.
    "REFRIGERATION:CASE",
    "REFRIGERATION:WALKIN",
    "REFRIGERATION:COMPRESSORRACK",
    "REFRIGERATION:SYSTEM",
    "REFRIGERATION:CONDENSER:AIRCOOLED",
    "REFRIGERATION:CONDENSER:WATERCOOLED",
    "REFRIGERATION:CONDENSER:EVAPORATIVECOOLED",
    "REFRIGERATION:CONDENSER:CASCADE",
    "REFRIGERATION:COMPRESSOR",
    "REFRIGERATION:SUBCOOLER",
    "REFRIGERATION:TRANSFERLOADSUMMARY",
    "REFRIGERATION:SECONDARYSYSTEM",
    "REFRIGERATION:AIRCHILLER",
    "REFRIGERATION:CASEANDWALKINLIST",
    # SIZING:ZONE — keep from prototype; needed for WSHP autosizing
    "THERMALZONE:CONDITIONINGEQUIPMENTLIST",
    "WATERHEATER:MIXED",
    "ZONEHVAC:AIRDISTRIBUTIONUNIT",
    "ZONEHVAC:EQUIPMENTCONNECTIONS",
    "ZONEHVAC:EQUIPMENTLIST",
    "ZONEHVAC:FOURPIPEFANCOIL",
    "ZONEHVAC:IDEALLOADSAIRSYSTEM",
    "ZONEHVAC:PACKAGEDTERMINALAIRCONDITIONER",
    "ZONEHVAC:PACKAGEDTERMINALHEATPUMP",
    "ZONEHVAC:UNITVENTILATOR",
    "ZONEHVAC:WATERTO AIRHEATPUMP",
    "AIRTERMINAL:SINGLEDUCT:CONSTANTVOLUME:NOREHEAT",
    "AIRTERMINAL:SINGLEDUCT:CONSTANTVOLUME:REHEAT",
    "AIRTERMINAL:SINGLEDUCT:VAV:NOREHEAT",
    "AIRTERMINAL:SINGLEDUCT:VAV:REHEAT",
    "BOILER:HOTWATER",
    "OUTPUT:METER",
    "OUTPUT:VARIABLE",
    "METER:CUSTOM",
    "METER:CUSTOMDECREMENT",
    # Electric load center — transformer references custom meters we strip
    "ELECTRICLOADCENTER:TRANSFORMER",
    "ELECTRICLOADCENTER:DISTRIBUTION",
    "ELECTRICLOADCENTER:GENERATORS",
    "ELECTRICLOADCENTER:INVERTER:PVWATTS",
    "ELECTRICLOADCENTER:INVERTER:SIMPLE",
    "ELECTRICLOADCENTER:INVERTER:LOOKUPTABLE",
    "GENERATOR:PVWATTS",
    "GENERATOR:PHOTOVOLTAIC",
    # EMS — all reference original VAV system; not needed for WSHP
    "ENERGYMANAGEMENTSYSTEM:SENSOR",
    "ENERGYMANAGEMENTSYSTEM:ACTUATOR",
    "ENERGYMANAGEMENTSYSTEM:PROGRAM",
    "ENERGYMANAGEMENTSYSTEM:PROGRAMCALLINGMANAGER",
    "ENERGYMANAGEMENTSYSTEM:GLOBALVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:INTERNALVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:OUTPUTVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:TRENDVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:CURVEORTABLEINDEXVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:CONSTRUCTIONINDEXVARIABLE",
    "ENERGYMANAGEMENTSYSTEM:METEREDOUTPUTVARIABLE",
}


def _parse_zones_from_thermostat(idf_text: str) -> list[str]:
    """Extract conditioned zone names from ZoneControl:Thermostat objects.

    Object structure:
      ZoneControl:Thermostat,
          {Name},        !- Name
          {ZoneName},    !- Zone or ZoneList Name
          ...
    Zone name is the SECOND field (index 1 in comma-split after object type).
    """
    zones = []
    # Match full thermostat object up to semicolon
    for m in re.finditer(
        r"ZoneControl:Thermostat\s*,(.*?);",
        idf_text, re.IGNORECASE | re.DOTALL
    ):
        fields = [f.split("!")[0].strip() for f in m.group(1).split(",")]
        # fields[0] = object name, fields[1] = zone name
        if len(fields) >= 2:
            z = fields[1].strip()
            if z:
                zones.append(z)
    if not zones:
        # Fallback: all Zone objects
        for m in re.finditer(r"^\s*Zone\s*,\s*\n\s*([^,\n!]+)", idf_text, re.MULTILINE):
            zones.append(m.group(1).strip())
    # Exclude return/supply plenums — they are not conditioned zones
    zones = [z for z in zones if "plenum" not in z.lower()]
    return list(dict.fromkeys(zones))  # deduplicate, preserve order


def _strip_hvac_blocks(idf_text: str) -> str:
    """Remove IDF object blocks whose type is in _STRIP_TYPES.

    Line-by-line parser that ignores semicolons inside !-comments, which
    appear in DOE prototype IDFs (e.g. !- Wind Direction {Degrees; N=0, S=180}).
    """
    result = []
    current_lines: list[str] = []
    last_kept_type = ""  # for repairing orphaned blocks (DOE prototype IDF bug)

    for line in idf_text.splitlines(keepends=True):
        # Strip the comment portion for semicolon detection only
        ci = line.find("!")
        data_part = line[:ci] if ci >= 0 else line

        if ";" in data_part:
            # This line terminates an IDF object block
            current_lines.append(line)
            block = "".join(current_lines)
            # Identify object type from first non-blank, non-comment line
            obj_type = ""
            for bl in block.splitlines():
                s = bl.strip()
                if s and not s.startswith("!"):
                    obj_type = s.split(",")[0].strip().upper()
                    break
            # Repair: some DOE prototype IDFs (e.g. large_office) have Construction
            # objects missing their 'Construction,' header line. EnergyPlus object
            # type names never contain periods; if obj_type has a period it's actually
            # a name field of an orphaned block. Re-inject the last kept type header.
            if obj_type and "." in obj_type:
                if last_kept_type and last_kept_type not in _STRIP_TYPES:
                    result.append(f"  {last_kept_type.title()},\n" + block)
                # if last_kept_type was stripped, silently drop orphaned block too
            elif obj_type not in _STRIP_TYPES:
                result.append(block)
                if obj_type:
                    last_kept_type = obj_type
            current_lines = []
        else:
            current_lines.append(line)

    # Any trailing content not terminated by semicolon (headers, blank lines)
    if current_lines:
        result.append("".join(current_lines))

    return "".join(result)


def _build_wshp_objects(zones: list[str]) -> str:
    """Generate WSHP+DOAS HVACTemplate IDF text for all zones.

    EP 22.1.0 format: coils use Curve:QuadLinear / Curve:QuintLinear references
    (not inline coefficients as in older EP versions).
    """

    lines = []

    # ── Performance curves (shared across all zones) ───────────────────────
    lines.append("""
! ── WSHP performance curves (EP 22.1.0: curve-name references) ──────────────

  Curve:QuadLinear,
    WSHP TotCoolCapCurve,        !- Name
    -9.149069561,                !- Coefficient1 Constant
    10.87814026,                 !- Coefficient2 w
    -1.718780157,                !- Coefficient3 x
    0.746414818,                 !- Coefficient4 y
    0.0,                         !- Coefficient5 z
    -100, 100,                   !- Minimum/Maximum Value of w
    -100, 100,                   !- Minimum/Maximum Value of x
    0,   100,                    !- Minimum/Maximum Value of y
    0,   100;                    !- Minimum/Maximum Value of z

  Curve:QuadLinear,
    WSHP CoolPowCurve,           !- Name
    -3.205409884,                !- Coefficient1 Constant
    -0.976409399,                !- Coefficient2 w
    3.97892546,                  !- Coefficient3 x
    0.938181818,                 !- Coefficient4 y
    0.0,                         !- Coefficient5 z
    -100, 100,
    -100, 100,
    0,   100,
    0,   100;

  Curve:QuadLinear,
    WSHP HeatCapCurve,           !- Name
    -1.361311959,                !- Coefficient1 Constant
    -2.471798046,                !- Coefficient2 w
    4.173164514,                 !- Coefficient3 x
    0.640757401,                 !- Coefficient4 y
    0.0,                         !- Coefficient5 z
    -100, 100,
    -100, 100,
    0,   100,
    0,   100;

  Curve:QuadLinear,
    WSHP HeatPowCurve,           !- Name
    -2.176941116,                !- Coefficient1 Constant
    0.832114286,                 !- Coefficient2 w
    1.570743399,                 !- Coefficient3 x
    0.690793651,                 !- Coefficient4 y
    0.0,                         !- Coefficient5 z
    -100, 100,
    -100, 100,
    0,   100,
    0,   100;

  Curve:QuintLinear,
    WSHP CoolSensCapCurve,       !- Name
    -5.462690012,                !- Coefficient1 Constant
    17.95968138,                 !- Coefficient2 v
    -11.87818402,                !- Coefficient3 w
    -0.980163419,                !- Coefficient4 x
    0.767285761,                 !- Coefficient5 y
    0.0,                         !- Coefficient6 z
    -100, 100,                   !- Minimum/Maximum Value of v
    -100, 100,                   !- Minimum/Maximum Value of w
    -100, 100,                   !- Minimum/Maximum Value of x
    0,   100,                    !- Minimum/Maximum Value of y
    0,   100;                    !- Minimum/Maximum Value of z

""")

    # ── Ground loop: PlantLoop with DistrictHeating+DistrictCooling, DualSetpoint ─
    # Uses PlantLoop (not CondenserLoop) + DualSetPointDeadband for stability.
    # DistrictCooling: unlimited capacity, absorbs heat when loop > 25°C
    # DistrictHeating: unlimited capacity, adds heat when loop < 15°C
    # Together they maintain EWT in [15, 25]°C year-round.
    lines.append("""
! ── Ground loop proxy: neutral water loop at 15-25°C ────────────────────────

  PlantLoop,
    Ground Loop,                 !- Name
    Water,                       !- Fluid Type
    ,                            !- User Defined Fluid Type
    Ground Loop Operation,       !- Plant Equipment Operation Scheme Name
    Ground Loop Supply Outlet,   !- Loop Temperature Setpoint Node Name
    98,                          !- Maximum Loop Temperature {C}
    1,                           !- Minimum Loop Temperature {C}
    autosize,                    !- Maximum Loop Flow Rate {m3/s}
    0,                           !- Minimum Loop Flow Rate {m3/s}
    autocalculate,               !- Plant Loop Volume {m3}
    Ground Loop Supply Inlet,    !- Plant Side Inlet Node Name
    Ground Loop Supply Outlet,   !- Plant Side Outlet Node Name
    Ground Loop Supply Branches, !- Plant Side Branch List Name
    Ground Loop Supply Connectors, !- Plant Side Connector List Name
    Ground Loop Demand Inlet,    !- Demand Side Inlet Node Name
    Ground Loop Demand Outlet,   !- Demand Side Outlet Node Name
    Ground Loop Demand Branches, !- Demand Side Branch List Name
    Ground Loop Demand Connectors, !- Demand Side Connector List Name
    SequentialLoad,              !- Load Distribution Scheme
    ,                            !- Availability Manager List Name
    DualSetPointDeadband;        !- Plant Loop Demand Calculation Scheme

  SetpointManager:Scheduled:DualSetpoint,
    Ground Loop SPM,             !- Name
    Temperature,                 !- Control Variable
    Ground Loop High Temp Sch,   !- High Setpoint Temperature Schedule Name
    Ground Loop Low Temp Sch,    !- Low Setpoint Temperature Schedule Name
    Ground Loop Supply Outlet;   !- Setpoint Node or NodeList Name

  Schedule:Compact,
    Ground Loop High Temp Sch,   !- Name
    Any Number,                  !- Schedule Type Limits Name
    Through: 12/31,
    For: AllDays,
    Until: 24:00, 25.0;

  Schedule:Compact,
    Ground Loop Low Temp Sch,    !- Name
    Any Number,                  !- Schedule Type Limits Name
    Through: 12/31,
    For: AllDays,
    Until: 24:00, 15.0;

  PlantEquipmentOperationSchemes,
    Ground Loop Operation,       !- Name
    PlantEquipmentOperation:HeatingLoad, !- Control Scheme 1 Object Type
    GL Heating Operation,        !- Control Scheme 1 Name
    ALWAYS_ON,                   !- Control Scheme 1 Schedule Name
    PlantEquipmentOperation:CoolingLoad, !- Control Scheme 2 Object Type
    GL Cooling Operation,        !- Control Scheme 2 Name
    ALWAYS_ON;                   !- Control Scheme 2 Schedule Name

  PlantEquipmentOperation:HeatingLoad,
    GL Heating Operation,        !- Name
    0, 1000000000,               !- Load Range 1 [W]
    GL Heating Equip List;       !- Equipment List 1

  PlantEquipmentOperation:CoolingLoad,
    GL Cooling Operation,        !- Name
    0, 1000000000,               !- Load Range 1 [W]
    GL Cooling Equip List;       !- Equipment List 1

  PlantEquipmentList,
    GL Heating Equip List,       !- Name
    DistrictHeating,             !- Equipment 1 Object Type
    Ground Loop Heater;          !- Equipment 1 Name

  PlantEquipmentList,
    GL Cooling Equip List,       !- Name
    DistrictCooling,             !- Equipment 1 Object Type
    Ground Loop Cooler;          !- Equipment 1 Name

  DistrictHeating,
    Ground Loop Heater,          !- Name
    GL Heater Inlet,             !- Hot Water Inlet Node Name
    GL Heater Outlet,            !- Hot Water Outlet Node Name
    1000000000;                  !- Nominal Capacity {W} -- 1 GW, effectively unlimited

  DistrictCooling,
    Ground Loop Cooler,          !- Name
    GL Cooler Inlet,             !- Chilled Water Inlet Node Name
    GL Cooler Outlet,            !- Chilled Water Outlet Node Name
    1000000000;                  !- Nominal Capacity {W} -- 1 GW, effectively unlimited

  Pump:VariableSpeed,
    Ground Loop Pump,            !- Name
    Ground Loop Supply Inlet,    !- Inlet Node Name
    GL Pump Outlet,              !- Outlet Node Name
    autosize,                    !- Design Maximum Flow Rate {m3/s}
    50000,                       !- Design Pump Head {Pa}
    autosize,                    !- Design Power Consumption {W}
    0.87,                        !- Motor Efficiency
    0.0,                         !- Fraction of Motor Inefficiencies to Fluid Stream
    0,                           !- Coefficient 1 of the Part Load Performance Curve
    1,                           !- Coefficient 2 of the Part Load Performance Curve
    0,                           !- Coefficient 3 of the Part Load Performance Curve
    0,                           !- Coefficient 4 of the Part Load Performance Curve
    0.001,                       !- Design Minimum Flow Rate {m3/s}  (prevents zero-flow T spikes)
    Continuous;                  !- Pump Control Type

  Sizing:Plant,
    Ground Loop,                 !- Plant or Condenser Loop Name
    Heating,                     !- Loop Type
    20,                          !- Design Loop Exit Temperature {C}
    5;                           !- Loop Design Temperature Difference {deltaC}

  BranchList,
    Ground Loop Supply Branches, !- Name
    Ground Loop Supply Inlet Branch,
    GL Supply Heater Branch,
    GL Supply Cooler Branch,
    Ground Loop Supply Bypass Branch,
    Ground Loop Supply Outlet Branch;

  Branch,
    Ground Loop Supply Inlet Branch, ,
    Pump:VariableSpeed, Ground Loop Pump,
    Ground Loop Supply Inlet, GL Pump Outlet;

  Branch,
    GL Supply Heater Branch, ,
    DistrictHeating, Ground Loop Heater,
    GL Heater Inlet, GL Heater Outlet;

  Branch,
    GL Supply Cooler Branch, ,
    DistrictCooling, Ground Loop Cooler,
    GL Cooler Inlet, GL Cooler Outlet;

  Pipe:Adiabatic,
    GL Supply Bypass Pipe,
    GL Supply Bypass Inlet, GL Supply Bypass Outlet;

  Branch,
    Ground Loop Supply Bypass Branch, ,
    Pipe:Adiabatic, GL Supply Bypass Pipe,
    GL Supply Bypass Inlet, GL Supply Bypass Outlet;

  Pipe:Adiabatic,
    GL Supply Outlet Pipe,
    GL Supply Outlet Pipe Node, Ground Loop Supply Outlet;

  Branch,
    Ground Loop Supply Outlet Branch, ,
    Pipe:Adiabatic, GL Supply Outlet Pipe,
    GL Supply Outlet Pipe Node, Ground Loop Supply Outlet;

  ConnectorList,
    Ground Loop Supply Connectors,
    Connector:Splitter, Ground Loop Supply Splitter,
    Connector:Mixer,   Ground Loop Supply Mixer;

  Connector:Splitter,
    Ground Loop Supply Splitter,
    Ground Loop Supply Inlet Branch,
    GL Supply Heater Branch,
    GL Supply Cooler Branch,
    Ground Loop Supply Bypass Branch;

  Connector:Mixer,
    Ground Loop Supply Mixer,
    Ground Loop Supply Outlet Branch,
    GL Supply Heater Branch,
    GL Supply Cooler Branch,
    Ground Loop Supply Bypass Branch;

""")

    # ── One WSHP per zone (parallel coil branches — official EP ZoneWSHP_wDOAS pattern) ──
    # Each zone gets TWO demand branches: clg_branch (cooling coil) + htg_branch (heating coil).
    # Parallel connection (vs. series) eliminates the series mid-node that caused temperature
    # runaway (CalcHPHeatingSimple:SourceSideInletTemp → 437°C) in single-zone buildings.
    demand_branches = []

    for zone in zones:
        z = zone
        supply_node  = f"{z} WSHP Supply Air Node"
        exhaust_node = f"{z} WSHP Exhaust Node"
        # Parallel water paths: separate nodes for each coil (official EP WSHP pattern)
        wtr_clg_in   = f"{z} WSHP Clg Water Inlet"
        wtr_clg_out  = f"{z} WSHP Clg Water Outlet"
        wtr_htg_in   = f"{z} WSHP Htg Water Inlet"
        wtr_htg_out  = f"{z} WSHP Htg Water Outlet"
        clg_branch   = f"{z} WSHP Clg Water Branch"
        htg_branch   = f"{z} WSHP Htg Water Branch"

        demand_branches.extend([clg_branch, htg_branch])

        lines.append(f"""
  ZoneHVAC:WaterToAirHeatPump,
    {z} WSHP,                    !- Name
    ALWAYS_ON,          !- Availability Schedule Name
    {exhaust_node},              !- Air Inlet Node Name
    {supply_node},               !- Air Outlet Node Name
    ,                            !- Outdoor Air Mixer Object Type
    ,                            !- Outdoor Air Mixer Name
    autosize,                    !- Cooling Supply Air Flow Rate {{m3/s}}
    autosize,                    !- Heating Supply Air Flow Rate {{m3/s}}
    0,                           !- No Load Supply Air Flow Rate {{m3/s}}
    0,                           !- Cooling Outdoor Air Flow Rate {{m3/s}}
    0,                           !- Heating Outdoor Air Flow Rate {{m3/s}}
    0,                           !- No Load Outdoor Air Flow Rate {{m3/s}}
    Fan:OnOff,                   !- Supply Air Fan Object Type
    {z} WSHP Fan,                !- Supply Air Fan Name
    Coil:Heating:WaterToAirHeatPump:EquationFit, !- Heating Coil Object Type
    {z} WSHP Htg Coil,           !- Heating Coil Name
    Coil:Cooling:WaterToAirHeatPump:EquationFit, !- Cooling Coil Object Type
    {z} WSHP Clg Coil,           !- Cooling Coil Name
    2.5,                         !- Maximum Cycling Rate {{cycles/hr}}
    60,                          !- Heat Pump Time Constant {{s}}
    0.01,                        !- Fraction of On-Cycle Power Use
    60,                          !- Heat Pump Fan Delay Time {{s}}
    Coil:Heating:Electric,       !- Supplemental Heating Coil Object Type
    {z} WSHP Supp Htg,           !- Supplemental Heating Coil Name
    autosize,                    !- Maximum Supply Air Temperature from Supplemental Heater {{C}}
    21,                          !- Maximum Outdoor Dry-Bulb Temp for Supplemental Heater {{C}}
    ,                            !- Outdoor Dry-Bulb Temperature Sensor Node Name
    BlowThrough,                 !- Fan Placement
    ;                            !- Supply Air Fan Operating Mode Schedule Name (blank=cycling)

  Fan:OnOff,
    {z} WSHP Fan,                !- Name
    ALWAYS_ON,          !- Availability Schedule Name
    0.75,                        !- Fan Total Efficiency
    75,                          !- Pressure Rise {{Pa}}
    autosize,                    !- Maximum Flow Rate {{m3/s}}
    0.9,                         !- Motor Efficiency
    1.0,                         !- Motor In Airstream Fraction
    {exhaust_node},              !- Air Inlet Node Name
    {z} WSHP Fan Outlet;         !- Air Outlet Node Name

  Coil:Cooling:WaterToAirHeatPump:EquationFit,
    {z} WSHP Clg Coil,           !- Name
    {wtr_clg_in},                !- Water Inlet Node Name  (Source Side 1)
    {wtr_clg_out},               !- Water Outlet Node Name
    {z} WSHP Fan Outlet,         !- Air Inlet Node Name  (BlowThrough: Fan→Clg→Htg→SuppHtg)
    {z} WSHP Clg Coil Outlet,    !- Air Outlet Node Name
    autosize,                    !- Rated Air Flow Rate {{m3/s}}
    autosize,                    !- Rated Water Flow Rate {{m3/s}}
    autosize,                    !- Gross Rated Total Cooling Capacity {{W}}
    autosize,                    !- Gross Rated Sensible Cooling Capacity {{W}}
    4.5,                         !- Gross Rated Cooling COP
    WSHP TotCoolCapCurve,        !- Total Cooling Capacity Curve Name
    WSHP CoolSensCapCurve,       !- Sensible Cooling Capacity Curve Name
    WSHP CoolPowCurve,           !- Cooling Power Consumption Curve Name
    0,                           !- Nominal Time for Condensate Removal to Begin {{s}}
    0;                           !- Ratio of Initial Moisture Evaporation Rate / Latent Cap

  Coil:Heating:WaterToAirHeatPump:EquationFit,
    {z} WSHP Htg Coil,           !- Name
    {wtr_htg_in},                !- Water Inlet Node Name  (Source Side 2)
    {wtr_htg_out},               !- Water Outlet Node Name
    {z} WSHP Clg Coil Outlet,    !- Air Inlet Node Name
    {z} WSHP Htg Coil Outlet,    !- Air Outlet Node Name
    autosize,                    !- Rated Air Flow Rate {{m3/s}}
    autosize,                    !- Rated Water Flow Rate {{m3/s}}
    autosize,                    !- Gross Rated Heating Capacity {{W}}
    3.5,                         !- Gross Rated Heating COP
    WSHP HeatCapCurve,           !- Heating Capacity Curve Name
    WSHP HeatPowCurve;           !- Heating Power Consumption Curve Name

  Coil:Heating:Electric,
    {z} WSHP Supp Htg,           !- Name
    ALWAYS_ON,                   !- Availability Schedule Name
    1.0,                         !- Efficiency
    autosize,                    !- Nominal Capacity {{W}}
    {z} WSHP Htg Coil Outlet,    !- Air Inlet Node Name
    {supply_node};               !- Air Outlet Node Name

  ZoneHVAC:EquipmentList,
    {z} WSHP Equip List,         !- Name
    SequentialLoad,              !- Load Distribution Scheme
    ZoneHVAC:WaterToAirHeatPump, !- Zone Equipment 1 Object Type
    {z} WSHP,                    !- Zone Equipment 1 Name
    1,                           !- Zone Equipment 1 Cooling Sequence
    1,                           !- Zone Equipment 1 Heating or No-Load Sequence
    ,                            !- Zone Equipment 1 Sequential Cooling Fraction
    ;                            !- Zone Equipment 1 Sequential Heating Fraction

  ZoneHVAC:EquipmentConnections,
    {z},                         !- Zone Name
    {z} WSHP Equip List,         !- Zone Conditioning Equipment List Name
    {supply_node},               !- Zone Air Inlet Node or NodeList Name
    {exhaust_node},              !- Zone Air Exhaust Node or NodeList Name
    {z} Zone Air Node,           !- Zone Air Node Name
    {z} Return Air Node;         !- Zone Return Air Node or NodeList Name

  Branch,
    {clg_branch},                !- Name
    ,                            !- Pressure Drop Curve Name
    Coil:Cooling:WaterToAirHeatPump:EquationFit,
    {z} WSHP Clg Coil,
    {wtr_clg_in}, {wtr_clg_out};

  Branch,
    {htg_branch},                !- Name
    ,                            !- Pressure Drop Curve Name
    Coil:Heating:WaterToAirHeatPump:EquationFit,
    {z} WSHP Htg Coil,
    {wtr_htg_in}, {wtr_htg_out};

""")

    # ── Demand side branch/connector lists for ground loop ─────────────────
    branch_list_zone_entries = "\n".join(f"    {b}," for b in demand_branches)
    zone_branch_lines = "\n".join(f"    {b}," for b in demand_branches)

    lines.append(f"""
  Pipe:Adiabatic,
    Ground Loop Demand Bypass Pipe,
    GL Demand Bypass Inlet, GL Demand Bypass Outlet;

  Branch,
    Ground Loop Demand Bypass Branch, ,
    Pipe:Adiabatic, Ground Loop Demand Bypass Pipe,
    GL Demand Bypass Inlet, GL Demand Bypass Outlet;

  BranchList,
    Ground Loop Demand Branches, !- Name
    Ground Loop Demand Inlet Branch,
{branch_list_zone_entries}
    Ground Loop Demand Bypass Branch,
    Ground Loop Demand Outlet Branch;

  Branch,
    Ground Loop Demand Inlet Branch, ,
    Pipe:Adiabatic, Ground Loop Demand Inlet Pipe,
    Ground Loop Demand Inlet, GL Demand Inlet Pipe Outlet;

  Pipe:Adiabatic,
    Ground Loop Demand Inlet Pipe,
    Ground Loop Demand Inlet, GL Demand Inlet Pipe Outlet;

  Branch,
    Ground Loop Demand Outlet Branch, ,
    Pipe:Adiabatic, Ground Loop Demand Outlet Pipe,
    GL Demand Outlet Pipe Inlet, Ground Loop Demand Outlet;

  Pipe:Adiabatic,
    Ground Loop Demand Outlet Pipe,
    GL Demand Outlet Pipe Inlet, Ground Loop Demand Outlet;

  ConnectorList,
    Ground Loop Demand Connectors, !- Name
    Connector:Splitter, Ground Loop Demand Splitter,
    Connector:Mixer,   Ground Loop Demand Mixer;

  Connector:Splitter,
    Ground Loop Demand Splitter,
    Ground Loop Demand Inlet Branch,
{zone_branch_lines}
    Ground Loop Demand Bypass Branch;

  Connector:Mixer,
    Ground Loop Demand Mixer,
    Ground Loop Demand Outlet Branch,
{zone_branch_lines}
    Ground Loop Demand Bypass Branch;

""")

    # ── Output variables ────────────────────────────────────────────────────
    # Sign convention: cooling coil source = +W (heat injected to ground)
    #                  heating coil source = +W (heat extracted from ground)
    # Net ground load = cooling_source - heating_source (handled in run script)
    lines.append("  ! Output variables — ground loop source-side heat transfer\n")
    for zone in zones:
        lines.append(f"""  Output:Variable,
    {zone} WSHP Clg Coil,
    Cooling Coil Source Side Heat Transfer Rate,
    Hourly;

  Output:Variable,
    {zone} WSHP Htg Coil,
    Heating Coil Source Side Heat Transfer Rate,
    Hourly;

""")

    return "\n".join(lines)


def patch_idf_raw(idf_src: pathlib.Path, out_path: pathlib.Path) -> pathlib.Path:
    """Patch any DOE prototype IDF path directly. Used by run_energyplus_wshp_all.py."""
    print(f"  Reading {idf_src.name} ...")
    raw = idf_src.read_text(encoding="utf-8", errors="replace")
    print(f"  Stripping HVAC ...")
    stripped = _strip_hvac_blocks(raw)
    zones = _parse_zones_from_thermostat(raw)
    print(f"  Found {len(zones)} conditioned zones")
    wshp_text = _build_wshp_objects(zones)
    sim_ctrl = """
  SimulationControl,
    Yes,   !- Do Zone Sizing Calculation
    Yes,   !- Do System Sizing Calculation
    Yes,   !- Do Plant Sizing Calculation
    No,    !- Run Simulation for Sizing Periods
    Yes;   !- Run Simulation for Weather File Run Periods
"""
    stripped = re.sub(
        r"SimulationControl,[^;]+;", sim_ctrl.strip() + ";", stripped, flags=re.DOTALL
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stripped + "\n\n" + wshp_text, encoding="utf-8")
    print(f"  → {out_path.name}")
    return out_path


def patch_idf(building: str, city: str) -> pathlib.Path:
    proto_stem = PROTO_MAP.get(building)
    if not proto_stem:
        sys.exit(f"Unknown building type: {building}. Available: {list(PROTO_MAP)}")

    idf_path = PROTO_DIR / proto_stem / f"{proto_stem}_{city}.idf"
    if not idf_path.exists():
        sys.exit(f"IDF not found: {idf_path}")

    print(f"  Reading {idf_path.name} ...")
    raw = idf_path.read_text(encoding="utf-8", errors="replace")

    print(f"  Stripping VAV/chiller/boiler HVAC objects ...")
    stripped = _strip_hvac_blocks(raw)

    print(f"  Detecting conditioned zones ...")
    zones = _parse_zones_from_thermostat(raw)  # use original for thermostat detection
    print(f"  Found {len(zones)} conditioned zones")

    print(f"  Adding WSHP+ground loop objects ...")
    wshp_text = _build_wshp_objects(zones)

    # Also update SimulationControl to enable system+plant sizing
    sim_ctrl = """
  SimulationControl,
    Yes,   !- Do Zone Sizing Calculation
    Yes,   !- Do System Sizing Calculation
    Yes,   !- Do Plant Sizing Calculation
    No,    !- Run Simulation for Sizing Periods
    Yes;   !- Run Simulation for Weather File Run Periods
"""
    stripped = re.sub(
        r"SimulationControl,[^;]+;", sim_ctrl.strip() + ";", stripped, flags=re.DOTALL
    )

    final = stripped + "\n\n" + wshp_text

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{building}_{city}_wshp.idf"
    out_path.write_text(final, encoding="utf-8")
    print(f"  → Saved: {out_path}")
    return out_path


TEST_CASES = [
    ("medium_office", "Buffalo"),
    ("medium_office", "Miami"),
    ("large_office",  "Buffalo"),
    ("large_office",  "Miami"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--building", help="Building type (e.g. medium_office)")
    ap.add_argument("--city",     help="City (e.g. Buffalo, Miami)")
    ap.add_argument("--all",      action="store_true",
                    help="Process all 4 validation test cases")
    args = ap.parse_args()

    if args.all:
        for b, c in TEST_CASES:
            print(f"\n{'='*50}")
            print(f"Patching {b} / {c}")
            patch_idf(b, c)
    elif args.building and args.city:
        patch_idf(args.building, args.city)
    else:
        ap.print_help()
        sys.exit(1)

    print("\nDone. Run scripts/run_energyplus_wshp_validation.py to execute.")


if __name__ == "__main__":
    main()
