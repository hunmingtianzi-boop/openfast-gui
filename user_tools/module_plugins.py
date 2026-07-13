# -*- coding: utf-8 -*-
"""Module registry used by the generic OpenFAST input editor.

The registry deliberately describes capabilities instead of reimplementing an
OpenFAST parser per module.  Files are classified from their path, heading, and
well-known keys; the generic document parser then preserves the source layout.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import pathlib
import re
from typing import Any, Iterable


@dataclass(frozen=True)
class ModulePlugin:
    id: str
    name: str
    stage: int
    category: str
    description: str
    docs: str
    patterns: tuple[str, ...] = ()
    key_signals: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ("scalars", "tables", "matrices", "outlist", "raw")
    priority: int = 0

    def public(self) -> dict[str, Any]:
        row = asdict(self)
        row.pop("patterns", None)
        row.pop("key_signals", None)
        row.pop("priority", None)
        return row


PLUGINS: tuple[ModulePlugin, ...] = (
    ModulePlugin(
        "fastfarm", "FAST.Farm", 6, "farm",
        "Wind-farm driver, turbine layout, ambient wind, wake dynamics and farm outputs.",
        "https://openfast.readthedocs.io/en/main/source/user/fast.farm/InputFiles.html",
        (r"\.fstf$", r"fast[._ -]?farm"), ("NumTurbines", "Mod_AmbWind"),
        ("scalars", "tables", "outlist", "raw", "external-tool"), 120,
    ),
    ModulePlugin(
        "turbsim", "TurbSim", 6, "wind",
        "Synthetic turbulent full-field wind generator.",
        "https://openfast.readthedocs.io/en/main/source/user/turbsim/index.html",
        (r"turbsim", r"(?:^|[/\\])wind[/\\].*\.in$"), ("TurbModel", "RandSeed1"),
        ("scalars", "tables", "raw", "external-tool"), 115,
    ),
    ModulePlugin(
        "openfast", "OpenFAST glue code", 1, "glue",
        "Primary coupled-model controls, module switches, linearization and visualization.",
        "https://openfast.readthedocs.io/en/main/source/user/input_file_overview.html",
        (r"\.fst$",), ("TMax", "CompElast", "CompInflow"),
        ("scalars", "tables", "outlist", "raw", "linearization", "vtk"), 110,
    ),
    ModulePlugin(
        "inflowwind", "InflowWind", 3, "wind",
        "Steady, uniform, TurbSim, Bladed, HAWC and user-defined inflow configuration.",
        "https://openfast.readthedocs.io/en/main/source/user/inflowwind/input.html",
        (r"inflow", r"inflowwind"), ("WindType", "HWindSpeed"), priority=105,
    ),
    ModulePlugin(
        "seastate", "SeaState", 3, "environment",
        "Wave spectra, external wave fields, currents and environmental properties.",
        "https://openfast.readthedocs.io/en/main/source/user/seastate/input_files.html",
        (r"sea[ _-]?state", r"seastate"), ("WaveMod", "WaveTMax", "WtrDpth"), priority=104,
    ),
    ModulePlugin(
        "hydrodyn", "HydroDyn", 3, "hydrodynamics",
        "Potential-flow and strip-theory hydrodynamics, Morison members and added matrices.",
        "https://openfast.readthedocs.io/en/main/source/user/hydrodyn/input_files.html",
        (r"hydrodyn",), ("PotMod", "AddCLin", "NMembers"),
        ("scalars", "tables", "matrices", "outlist", "raw", "morison"), 103,
    ),
    ModulePlugin(
        "moordyn", "MoorDyn", 3, "mooring",
        "Line types, rods, bodies, points, lines, failures and solver options.",
        "https://moordyn.readthedocs.io/en/latest/inputs.html",
        (r"moordyn",), ("dtM", "TmaxIC"), priority=102,
    ),
    ModulePlugin(
        "map", "MAP++", 3, "mooring",
        "Quasi-static mooring line dictionary, nodes, lines and solver options.",
        "https://openfast.readthedocs.io/en/main/source/user/map.html",
        (r"(?:^|[/\\_])map(?:[._-]|$)",), ("LINE DICTIONARY", "NODE PROPERTIES"), priority=101,
    ),
    ModulePlugin(
        "elastodyn", "ElastoDyn", 4, "structure",
        "Rigid-body and modal structural DOFs, initial conditions, mass and drivetrain properties.",
        "https://openfast.readthedocs.io/en/main/source/user/elastodyn/input.html",
        (r"elastodyn",), ("FlapDOF1", "PtfmSgDOF", "RotSpeed"), priority=100,
    ),
    ModulePlugin(
        "aerodyn", "AeroDyn", 4, "aerodynamics",
        "BEM/OLAF aerodynamics, airfoils, blades, tower and aerodynamic outputs.",
        "https://openfast.readthedocs.io/en/main/source/user/aerodyn/input.html",
        (r"aerodyn", r"airfoil", r"polar"), ("Wake_Mod", "TwrAero", "NumAFfiles"), priority=99,
    ),
    ModulePlugin(
        "servodyn", "ServoDyn", 4, "controls",
        "Pitch, torque, yaw, braking, DLL/Simulink and structural-control interfaces.",
        "https://openfast.readthedocs.io/en/main/source/user/servodyn/input.html",
        (r"servodyn", r"(?:^|[/\\])stc[-_]", r"structural[ _-]?control"), ("PCMode", "VSContrl", "DLL_FileName"), priority=98,
    ),
    ModulePlugin(
        "rosco", "ROSCO", 4, "controls",
        "ROSCO controller tuning YAML and DISCON controller parameters.",
        "https://rosco-toolbox.readthedocs.io/en/latest/",
        (r"rosco", r"discon\.in$", r"cp_ct_cq"), ("LoggingLevel", "F_LPFType"),
        ("scalars", "tables", "raw", "controller"), 97,
    ),
    ModulePlugin(
        "beamdyn", "BeamDyn", 5, "structure",
        "Geometrically exact blade geometry, discretization and sectional 6x6 properties.",
        "https://openfast.readthedocs.io/en/main/source/user/beamdyn/input_files.html",
        (r"beamdyn",), ("member_total", "kp_total", "station_total"), priority=96,
    ),
    ModulePlugin(
        "subdyn", "SubDyn", 5, "substructure",
        "Substructure joints, members, properties, constraints and Craig-Bampton reduction.",
        "https://openfast.readthedocs.io/en/main/source/user/subdyn/input_files.html",
        (r"subdyn",), ("NJoints", "NMembers", "Nmodes"), priority=95,
    ),
    ModulePlugin(
        "extptfm", "ExtPtfm", 5, "substructure",
        "External reduced-order platform mass, damping, stiffness and force inputs.",
        "https://openfast.readthedocs.io/en/main/source/user/extptfm/input_files.html",
        (r"extptfm", r"extptf", r"redfile", r"superelement"), ("FileFormat", "Red_FileName"),
        ("scalars", "tables", "matrices", "outlist", "raw"), 94,
    ),
    ModulePlugin(
        "olaf", "OLAF", 4, "aerodynamics",
        "Free-vortex wake configuration used by AeroDyn.",
        "https://openfast.readthedocs.io/en/main/source/user/olaf/input.html",
        (r"olaf",), ("IntMethod", "DTfvw"), priority=93,
    ),
    ModulePlugin(
        "generic", "OpenFAST auxiliary file", 1, "auxiliary",
        "Format-preserving editor for module assets and value-column input files.",
        "https://openfast.readthedocs.io/en/main/source/user/input_file_overview.html",
        (), (), priority=-100,
    ),
)

PLUGIN_BY_ID = {plugin.id: plugin for plugin in PLUGINS}


KEY_METADATA: dict[str, dict[str, Any]] = {
    "WindType": {"type": "integer", "options": [0, 1, 2, 3, 4, 5, 6, 7]},
    "WaveMod": {"type": "integer", "options": [0, 1, 2, 3, 4, 5, 6, 7]},
    "Wake_Mod": {"type": "integer", "options": [0, 1, 3]},
    "CompElast": {"type": "integer", "options": [0, 1, 2, 3]},
    "CompInflow": {"type": "integer", "options": [0, 1, 2]},
    "CompAero": {"type": "integer", "options": [0, 1, 2, 3]},
    "CompServo": {"type": "integer", "options": [0, 1]},
    "CompSeaSt": {"type": "integer", "options": [0, 1]},
    "CompSeaState": {"type": "integer", "options": [0, 1]},
    "CompHydro": {"type": "integer", "options": [0, 1]},
    "CompSub": {"type": "integer", "options": [0, 1, 2]},
    "CompMooring": {"type": "integer", "options": [0, 1, 2, 3, 4]},
    "PCMode": {"type": "integer", "options": [0, 3, 4, 5]},
    "VSContrl": {"type": "integer", "options": [0, 1, 3, 4, 5]},
    "YCMode": {"type": "integer", "options": [0, 3, 4, 5]},
    "HSSBrMode": {"type": "integer", "options": [0, 1]},
    "Linearize": {"type": "boolean"},
    "CalcSteady": {"type": "boolean"},
    "WrVTK": {"type": "integer", "options": [0, 1, 2, 3]},
    "VTK_type": {"type": "integer", "options": [1, 2, 3]},
    "PotMod": {"type": "integer", "options": [0, 1, 2]},
    "ExctnMod": {"type": "integer", "options": [0, 1, 2]},
    "RdtnMod": {"type": "integer", "options": [0, 1, 2]},
    "MCoefMod": {"type": "integer", "options": [1, 2, 3]},
    "Echo": {"type": "boolean"},
}


def plugin_definitions() -> list[dict[str, Any]]:
    return [plugin.public() for plugin in PLUGINS if plugin.id != "generic"]


def _pattern_score(plugin: ModulePlugin, haystack: str) -> int:
    return sum(1 for pattern in plugin.patterns if re.search(pattern, haystack, re.IGNORECASE))


def classify_module(
    file_id: str,
    heading: str = "",
    keys: Iterable[str] | None = None,
) -> ModulePlugin:
    """Return the highest-confidence plugin for a model file."""
    key_set = {str(key).lower() for key in (keys or [])}
    normalized = str(pathlib.PurePosixPath(str(file_id).replace("\\", "/"))).lower()
    haystack = f"{normalized}\n{heading.lower()}"
    ranked: list[tuple[int, int, ModulePlugin]] = []
    for plugin in PLUGINS:
        if plugin.id == "generic":
            continue
        pattern_hits = _pattern_score(plugin, haystack)
        key_hits = sum(1 for key in plugin.key_signals if key.lower() in key_set or key.lower() in haystack)
        if not pattern_hits and not key_hits:
            continue
        score = pattern_hits * 20 + key_hits * 8 + plugin.priority
        ranked.append((score, plugin.priority, plugin))
    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return ranked[0][2]
    return PLUGIN_BY_ID["generic"]


def metadata_for_key(key: str) -> dict[str, Any]:
    return dict(KEY_METADATA.get(key, {}))


def capability_matrix(catalog: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    present: dict[str, list[str]] = {}
    for row in catalog:
        present.setdefault(str(row.get("pluginId") or "generic"), []).append(str(row.get("file") or ""))
    result = []
    for plugin in PLUGINS:
        if plugin.id == "generic":
            continue
        files = [file for file in present.get(plugin.id, []) if file]
        result.append(
            {
                **plugin.public(),
                "available": bool(files),
                "files": files,
                "status": "available" if files else "not-in-model",
            }
        )
    return result
