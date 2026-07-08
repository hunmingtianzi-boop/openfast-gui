# -*- coding: utf-8 -*-
"""Path configuration for the FOCAL C4 workflow.

The workflow is portable: by default it derives all project paths from this
file's location. Set OPENFAST_EXE in the environment if OpenFAST is installed
outside the project.
"""
import os
import pathlib


# Project root directory: contains data/, FOCAL_OpenFast_C4-main/, work_c4/.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _find_openfast_exe():
    """Return the configured or best-known OpenFAST executable path."""
    env_path = os.environ.get("OPENFAST_EXE")
    candidates = [
        pathlib.Path(env_path) if env_path else None,
        PROJECT_ROOT / "bin" / "openfast_x64.exe",
        PROJECT_ROOT / "openfast_x64.exe",
        PROJECT_ROOT / "bin" / "openfast.exe",
        PROJECT_ROOT / "openfast.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return pathlib.Path(env_path) if env_path else PROJECT_ROOT / "bin" / "openfast_x64.exe"


# OpenFAST 4.0.0+ executable. Must support SeaState + MoorDyn v2.
OPENFAST_EXE = _find_openfast_exe()

# Output directory for generated cases and results.
OUTPUT_DIR = pathlib.Path(__file__).resolve().parent / "output"


# Derived paths.
MODEL = pathlib.Path(
    os.environ.get(
        "FOCAL_C4_MODEL_TEMPLATE",
        PROJECT_ROOT / "FOCAL_OpenFast_C4-main" / "FOCAL_OpenFast_C4-main",
    )
)
IEA_MODEL = (
    PROJECT_ROOT
    / "IEA-15-240-RWT-master"
    / "OpenFAST"
    / "IEA-15-240-RWT-UMaineSemi"
)
IEA_OPENFAST_EXE = IEA_MODEL / "OpenFAST_Release.exe"
DATA = PROJECT_ROOT / "data" / "focal_c4_organized"
DATA_FREEDECAY = DATA / "01_free_decay"


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def validate_paths():
    """Check critical workflow paths. Returns (ok, messages)."""
    messages = []
    ok = True

    if not PROJECT_ROOT.is_dir():
        messages.append(f"ERROR PROJECT_ROOT not found: {PROJECT_ROOT}")
        ok = False
    else:
        messages.append(f"OK PROJECT_ROOT: {PROJECT_ROOT}")

    if not MODEL.is_dir():
        messages.append(f"ERROR MODEL directory not found: {MODEL}")
        ok = False
    else:
        messages.append(f"OK MODEL: {MODEL}")
        for fname in ["FOCAL_C4.fst", "FOCAL_C4_HydroDyn.dat", "FOCAL_C4_ElastoDyn.dat"]:
            fpath = MODEL / fname
            if not fpath.is_file():
                messages.append(f"  ERROR missing template: {fname}")
                ok = False
            else:
                messages.append(f"  OK template: {fname}")

    if not DATA_FREEDECAY.is_dir():
        messages.append(f"WARN free-decay data not found: {DATA_FREEDECAY}")
        messages.append("  General GUI/scenario runs do not require the experimental free-decay dataset.")
    else:
        messages.append(f"OK DATA_FREEDECAY: {DATA_FREEDECAY}")
        dof_dirs = [
            d.name for d in DATA_FREEDECAY.iterdir()
            if d.is_dir() and d.name.upper().startswith("FD")
        ]
        messages.append(f"  Found {len(dof_dirs)} DOF directories: {dof_dirs}")

    if not OPENFAST_EXE.is_file():
        messages.append(f"WARN OpenFAST exe not found: {OPENFAST_EXE}")
        messages.append("  Set OPENFAST_EXE or place openfast_x64.exe under PROJECT_ROOT/bin/.")
    else:
        messages.append(f"OK OPENFAST_EXE: {OPENFAST_EXE}")

    messages.append(f"OK OUTPUT_DIR: {OUTPUT_DIR}")
    return ok, messages


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 70)
    print("FOCAL C4 Workflow Configuration Validation")
    print("=" * 70)
    ok, messages = validate_paths()
    for msg in messages:
        print(msg)
    print("=" * 70)
    if ok:
        print("Configuration valid: data analysis workflow is ready.")
    else:
        print("Configuration errors: fix the paths above.")
    print("=" * 70)
