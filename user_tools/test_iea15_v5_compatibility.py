# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_tools"))

import run_scenario  # noqa: E402


REPORT_PRIMARY = """------- OpenFAST INPUT FILE -------------------------------------------
IEA 15 MW report monopile
False                  Echo        - Echo input
\"FATAL\"                AbortLevel  - Abort level
300.0                  TMax        - Total run time
0.005                  DT          - Time step
2                      InterpOrder - Interpolation order
0                      NumCrctn    - Correction iterations
99999.0                DT_UJac     - Jacobian interval
1000000.0              UJacSclFact - Jacobian scale
1                      CompElast   - Structural dynamics
0                      CompIce     - Ice
0                      MHK         - MHK
\"none\"                 IceFile     - Ice input
"""

REPORT_ELASTODYN = """------- ELASTODYN INPUT FILE -------------------------------------------
False                  Echo        - Echo input
True                   EdgeDOF     - First edgewise blade mode
False                  TeetDOF     - Rotor-teeter DOF
15.0                   PtfmCMzt    - Platform CM
15.0                   PtfmRefzt   - Platform reference point
0.0                    TipMass(1)  - Blade 1 tip mass
0.0                    TipMass(2)  - Blade 2 tip mass
0.0                    TipMass(3)  - Blade 3 tip mass
69131                  HubMass     - Hub mass
"""

REPORT_SEASTATE = """------- SeaState Input File -------------------------------------------
False                  Echo        - Echo input
2                      WaveMod     - Irregular waves
0                      WaveStMod   - Wave stretching model
850                    WaveTMax    - Wave analysis time
"""

REPORT_AERODYN = """------- AeroDyn Input File -------------------------------------------
False                  CavitCheck  - Perform cavitation check
False                  Buoyancy    - Transitional buoyancy switch
False                  NacelleDrag - Include nacelle drag
1                      NumTwrNds   - Number of tower nodes
TwrElev TwrDiam TwrCd TwrTI TwrCb
(m) (m) (-) (-) (-)
15.0 10.0 0.5 0.1 0.0
"""

REPORT_SUBDYN = """------- SubDyn Input File -------------------------------------------
6                      GuyanDampSize - Damping matrix size
0 0 0 0 0 0
0 0 0 0 0 0
0 0 0 0 0 0
0 0 0 0 0 0
0 0 0 0 0 0
0 0 0 0 0 0
---- STRUCTURE JOINTS -------------------------------------------------------
1                      NJoints     - Number of joints
JointID JointXss JointYss JointZss JointType JointDirX JointDirY JointDirZ JointStiff
(-) (m) (m) (m) (-) (-) (-) (-) (Nm/rad)
1 0 0 -30 1 0 0 0 0
1                      NInterf     - Number of interface joints
IJointID ItfTDXss ItfTDYss ItfTDZss ItfRDXss ItfRDYss ItfRDZss
(-) (flag) (flag) (flag) (flag) (flag) (flag)
1 1 1 1 1 1 1
------------------ CIRCULAR BEAM CROSS-SECTION PROPERTIES ------------------
1                      NPropSets   - Number of circular sections
----------------- RECTANGULAR BEAM CROSS-SECTION PROPERTIES ----------------
0                      NPropSets   - Number of rectangular sections
"""

REPORT_HYDRODYN = """------- HydroDyn Input File -------------------------------------------
0                      PtfmCOByt   - Center-of-buoyancy y offset
0                      MnDrift     - Mean-drift forces
0                      AMMod       - Added-mass force model
1                      NAxCoef     - Number of axial coefficients
"""

REPORT_SERVODYN = """------- ServoDyn Input File -------------------------------------------
5                      PCMode      - Pitch control mode
0.0                    TPCOn       - Pitch control start time
9999.9                 TPitManS(1) - Blade 1 pitch maneuver start
"""


class Iea15V5CompatibilityTests(unittest.TestCase):
    def test_primary_schema_upgrade_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp)
            relative = pathlib.Path("IEA-15-240-RWT-Monopile") / "IEA-15-240-RWT-Monopile.fst"
            path = run_dir / relative
            path.parent.mkdir(parents=True)
            path.write_text(REPORT_PRIMARY, encoding="utf-8")
            ed_path = path.with_name(f"{path.stem}_ElastoDyn.dat")
            ed_path.write_text(REPORT_ELASTODYN, encoding="utf-8")
            sea_state_path = path.with_name(f"{path.stem}_SeaState.dat")
            sea_state_path.write_text(REPORT_SEASTATE, encoding="utf-8")
            aero_path = path.with_name(f"{path.stem}_AeroDyn15.dat")
            aero_path.write_text(REPORT_AERODYN, encoding="utf-8")
            subdyn_path = path.with_name(f"{path.stem}_SubDyn.dat")
            subdyn_path.write_text(REPORT_SUBDYN, encoding="utf-8")
            hydrodyn_path = path.with_name(f"{path.stem}_HydroDyn.dat")
            hydrodyn_path.write_text(REPORT_HYDRODYN, encoding="utf-8")
            servodyn_path = path.with_name(f"{path.stem}_ServoDyn.dat")
            servodyn_path.write_text(REPORT_SERVODYN, encoding="utf-8")

            fixes = run_scenario.prepare_openfast_inputs(
                run_dir,
                compatibility="iea15_monopile_v5",
                runtime_format="v5",
                fst_name=str(relative),
            )
            self.assertEqual(len(fixes), 7)
            upgraded = path.read_text(encoding="utf-8").splitlines()
            for key in (
                "ModCoupling",
                "RhoInf",
                "ConvTol",
                "MaxConvIter",
                "NRotors",
                "CompSoil",
                "MirrorRotor",
                "SoilFile",
            ):
                self.assertTrue(run_scenario._has_key(upgraded, key), key)

            upgraded_ed = ed_path.read_text(encoding="utf-8").splitlines()
            for key in (
                "PitchDOF",
                "PtfmRefxt",
                "PtfmRefyt",
                "PBrIner(1)",
                "PBrIner(2)",
                "PBrIner(3)",
                "BlPIner(1)",
                "BlPIner(2)",
                "BlPIner(3)",
            ):
                self.assertTrue(run_scenario._has_key(upgraded_ed, key), key)

            upgraded_sea_state = sea_state_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(run_scenario._has_key(upgraded_sea_state, "WvCrntMod"))

            upgraded_aero = aero_path.read_text(encoding="utf-8").splitlines()
            self.assertFalse(run_scenario._has_key(upgraded_aero, "Buoyancy"))
            self.assertTrue(run_scenario._has_key(upgraded_aero, "NacelleDrag"))
            tower_header = next(line for line in upgraded_aero if line.startswith("TwrElev"))
            tower_row = next(line for line in upgraded_aero if line.startswith("15.0"))
            self.assertIn("TwrCp", tower_header)
            self.assertIn("TwrCa", tower_header)
            self.assertEqual(len(tower_row.split()), 7)

            upgraded_subdyn = subdyn_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(any("INITIAL RIGID-BODY POSITION" in line for line in upgraded_subdyn))
            self.assertTrue(run_scenario._has_key(upgraded_subdyn, "NPropSetsCyl"))
            self.assertTrue(run_scenario._has_key(upgraded_subdyn, "NPropSetsRec"))
            interface_header = next(line for line in upgraded_subdyn if line.startswith("IJointID"))
            self.assertEqual(interface_header.split()[1], "TPID")

            upgraded_hydrodyn = hydrodyn_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(run_scenario._has_key(upgraded_hydrodyn, "NAddDOF"))
            self.assertTrue(run_scenario._has_key(upgraded_hydrodyn, "HstMod"))

            upgraded_servodyn = servodyn_path.read_text(encoding="utf-8").splitlines()
            for key in ("PitNeut(1)", "PitSpr(1)", "PitDamp(1)"):
                self.assertTrue(run_scenario._has_key(upgraded_servodyn, key), key)

            second = run_scenario.prepare_openfast_inputs(
                run_dir,
                compatibility="iea15_monopile_v5",
                runtime_format="v5",
                fst_name=str(relative),
            )
            self.assertEqual(second, [])
            self.assertEqual(upgraded, path.read_text(encoding="utf-8").splitlines())
            self.assertEqual(upgraded_ed, ed_path.read_text(encoding="utf-8").splitlines())
            self.assertEqual(
                upgraded_sea_state,
                sea_state_path.read_text(encoding="utf-8").splitlines(),
            )
            self.assertEqual(upgraded_aero, aero_path.read_text(encoding="utf-8").splitlines())
            self.assertEqual(upgraded_subdyn, subdyn_path.read_text(encoding="utf-8").splitlines())
            self.assertEqual(
                upgraded_hydrodyn,
                hydrodyn_path.read_text(encoding="utf-8").splitlines(),
            )
            self.assertEqual(
                upgraded_servodyn,
                servodyn_path.read_text(encoding="utf-8").splitlines(),
            )


if __name__ == "__main__":
    unittest.main()
