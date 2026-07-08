# -*- coding: utf-8 -*-
"""Closed-loop OpenFAST driver for FOCAL Campaign-4 as-built model (portable version).

Adapted from driver.py (IEA-15MW standard reference) to work with the
FOCAL C4 OpenFAST 4.0.0 model (FOCAL_OpenFast_C4-main repo).

Key differences vs original driver.py:
  - File naming: FOCAL_C4_HydroDyn.dat, FOCAL_C4_ElastoDyn.dat, FOCAL_C4.fst
  - HydroDyn baseline: AddCLin has umbilical stiffness (Surge 6.86e3, Heave 6.22e4),
    AddBLin non-zero (Surge/Sway 1.6e5, Roll/Pitch 2.7e8),
    AddBQuad diagonal (Surge/Sway 1e6, Heave 6.6e6, Roll/Pitch/Yaw 7.2e10)
  - ElastoDyn: PtfmRIner (1.112e10) != PtfmPIner (1.248e10) — asymmetric
  - Mooring: MoorDyn linear springs (not MAP++ catenary)
  - OpenFAST 4.0.0: separate SeaState module, CompMooring=3
  - Platform initial conditions include non-zero equilibrium offsets

DOF index map (0-indexed, OpenFAST platform order):
    0=Surge  1=Sway  2=Heave  3=Roll  4=Pitch  5=Yaw

Matrix-edit spec: a list of (block, i, j, value) tuples, block in {'CLin','BLin','BQuad'},
i,j 0-indexed into the 6x6 HydroDyn additional matrix.
"""
import pathlib, shutil, subprocess, time, re
import numpy as np

# Import paths from config
try:
    from config import MODEL, OPENFAST_EXE, OUTPUT_DIR
except ImportError:
    print("ERROR: config.py not found. Make sure you are in the work_c4/ directory.")
    raise

HD_TEMPLATE = MODEL / "FOCAL_C4_HydroDyn.dat"
ED_TEMPLATE = MODEL / "FOCAL_C4_ElastoDyn.dat"
FST_TEMPLATE = MODEL / "FOCAL_C4.fst"

DOF_IDX  = {'Surge':0, 'Sway':1, 'Heave':2, 'Roll':3, 'Pitch':4, 'Yaw':5}
PTFM_KEY = {'Surge':'PtfmSurge','Sway':'PtfmSway','Heave':'PtfmHeave',
            'Roll':'PtfmRoll','Pitch':'PtfmPitch','Yaw':'PtfmYaw'}

# --------------------------------------------------------------------------- #
#  WRITE side: build OpenFAST inputs from a parameter set                      #
# --------------------------------------------------------------------------- #
def _block_start(lines, tag):
    """0-indexed line of the first row of the 6x6 matrix whose comment is `tag`."""
    for i, l in enumerate(lines):
        if tag in l and ('Add' in l or 'add' in l.lower()):
            return i
    raise KeyError(tag)

def _read_matrix(lines, start):
    M = np.zeros((6, 6))
    for r in range(6):
        toks = lines[start + r].split()
        nums = []
        for tk in toks:
            try:
                nums.append(float(tk))
            except ValueError:
                break
            if len(nums) == 6:
                break
        M[r, :len(nums)] = nums[:6]
    return M

def _trailing_comment(line):
    """Everything after the 6th numeric token on a matrix row."""
    toks = line.split(None, 6)
    return toks[6] if len(toks) > 6 else ''

def apply_edits(template_lines, edits):
    """Return a new HydroDyn line list with the (block,i,j,val) edits applied."""
    lines = list(template_lines)
    tagmap = {'CLin':'AddCLin', 'BLin':'AddBLin', 'BQuad':'AddBQuad'}
    by_block = {}
    for block, i, j, val in edits:
        by_block.setdefault(block, []).append((i, j, val))
    for block, items in by_block.items():
        tag = tagmap[block]
        start = _block_start(lines, tag)
        M = _read_matrix(lines, start)
        for i, j, val in items:
            M[i, j] = val
        comment = _trailing_comment(lines[start])
        for r in range(6):
            row = '\t'.join(f'{M[r, c]:.6E}' for c in range(6))
            lines[start + r] = row + (' ' + comment if (r == 0 and comment) else '')
    return lines

def _set_val(lines, key, newval):
    """Replace the leading value token on the line whose 2nd token == key."""
    for i, l in enumerate(lines):
        parts = l.split()
        if len(parts) >= 2 and parts[1] == key:
            rest = l.split(None, 1)[1] if len(l.split(None, 1)) > 1 else ''
            lines[i] = f"{str(newval):<13} {rest}"
            return True
    raise KeyError(key)

def _disable_aero_servo(lines):
    """Set CompAero=0, CompServo=0, CompInflow=0 for free-decay runs."""
    for i, l in enumerate(lines):
        parts = l.split()
        if len(parts) >= 2:
            if parts[1] == 'CompAero':
                lines[i] = '      0   CompAero        - Compute aerodynamic loads (switch) {0=None; 1=AeroDyn v14; 2=AeroDyn v15}'
            elif parts[1] == 'CompServo':
                lines[i] = '      0   CompServo       - Compute control and electrical-drive dynamics (switch) {0=None; 1=ServoDyn}'
            elif parts[1] == 'CompInflow':
                lines[i] = '      0   CompInflow      - Compute inflow wind velocities (switch) {0=still air; 1=InflowWind; 2=external from OpenFOAM}'

def _lock_blades(lines):
    """Disable all blade/rotor DOFs, set RotSpeed=0 and BlPitch=90 for parked."""
    dof_flags = ['FlapDOF1','FlapDOF2','EdgeDOF','DrTrDOF','GenDOF','YawDOF']
    for i, l in enumerate(lines):
        parts = l.split()
        if len(parts) >= 2:
            if parts[1] in dof_flags:
                lines[i] = f"False         {parts[1]}    - {' '.join(parts[2:])}" if len(parts) > 2 else f"False         {parts[1]}"
            elif parts[1] == 'RotSpeed':
                lines[i] = f"          0   RotSpeed    - Initial or fixed rotor speed (rpm)"
            elif parts[1].startswith('BlPitch('):
                lines[i] = f"         90   {parts[1]}  - Blade {parts[1][-2]} initial pitch (degrees)"

def _ensure_platform_cross_inertia(lines):
    """Add zero platform products of inertia required by OpenFAST 4.x inputs."""
    if any(len(l.split()) >= 2 and l.split()[1] == 'PtfmXYIner' for l in lines):
        return
    for i, l in enumerate(lines):
        parts = l.split()
        if len(parts) >= 2 and parts[1] == 'PtfmYIner':
            lines[i + 1:i + 1] = [
                '          0   PtfmXYIner - Platform roll-pitch moment of inertia about the platform CM (kg m^2)',
                '          0   PtfmYZIner - Platform pitch-yaw moment of inertia about the platform CM (kg m^2)',
                '          0   PtfmXZIner - Platform roll-yaw moment of inertia about the platform CM (kg m^2)',
            ]
            return
    raise KeyError('PtfmYIner')

def _ensure_yaw_friction(lines):
    """Add the zero yaw-friction block required by newer ElastoDyn inputs."""
    if any(len(l.split()) >= 2 and l.split()[1] == 'YawFrctMod' for l in lines):
        return
    for i, l in enumerate(lines):
        if 'DRIVETRAIN' in l:
            lines[i:i + 1] = [
                '---------------------- YAW-FRICTION --------------------------------------------',
                '          0   YawFrctMod - Yaw-friction model {0: none, 1: basic, 2: load-dependent, 3: user-defined}',
                '          0   M_CSmax    - Maximum static Coulomb friction torque (N-m)',
                '          0   M_FCSmax   - Static Coulomb friction proportional to yaw bearing shear force (N-m)',
                '          0   M_MCSmax   - Static Coulomb friction proportional to yaw bearing bending moment (N-m)',
                '          0   M_CD       - Dynamic Coulomb friction moment (N-m)',
                '          0   M_FCD      - Dynamic Coulomb friction proportional to yaw bearing shear force (N-m)',
                '          0   M_MCD      - Dynamic Coulomb friction proportional to yaw bearing bending moment (N-m)',
                '          0   sig_v      - Linear viscous friction coefficient (N-m/(rad/s))',
                '          0   sig_v2     - Quadratic viscous friction coefficient (N-m/(rad/s)^2)',
                '          0   OmgCut     - Yaw angular velocity cutoff below which viscous friction is linearized (rad/s)',
                '---------------------- DRIVETRAIN ----------------------------------------------',
            ]
            return
    raise KeyError('DRIVETRAIN')

def _localize_ed_references(lines, output_dir):
    """Copy ElastoDyn blade/tower files to output_dir and use local names."""
    ref_keys = {'BldFile1', 'BldFile2', 'BldFile3', 'TwrFile'}
    for i, l in enumerate(lines):
        parts = l.split()
        if len(parts) >= 2 and parts[1] in ref_keys:
            raw_name = parts[0].strip('"')
            ref_path = pathlib.Path(raw_name)
            if not ref_path.is_absolute():
                ref_path = MODEL / raw_name
            local_path = pathlib.Path(output_dir) / ref_path.name
            if ref_path.is_file() and not local_path.exists():
                shutil.copy2(ref_path, local_path)
            comment = l.split('-', 1)[1] if '-' in l else ''
            lines[i] = f'"{local_path.name}"    {parts[1]}    - {comment}'.rstrip()

def _copy_model_support_files(output_dir):
    """Copy model support files needed when generated cases run from output_dir."""
    output_dir = pathlib.Path(output_dir)
    hydro_src = MODEL / 'Hydro'
    hydro_dst = output_dir / 'Hydro'
    if hydro_src.is_dir() and not hydro_dst.exists():
        shutil.copytree(hydro_src, hydro_dst)

    for fname in ['SeaState_DLC_1p6.dat']:
        src = MODEL / fname
        dst = output_dir / fname
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)

    md_src = MODEL / 'FOCAL_C4_MoorDyn.dat'
    md_dst = output_dir / 'FOCAL_C4_MoorDyn.dat'
    if md_src.is_file():
        md_lines = _ensure_moordyn_v2(md_src.read_text(encoding='utf-8', errors='replace').splitlines())
        md_dst.write_text('\n'.join(md_lines), encoding='utf-8')

def _ensure_moordyn_v2(lines):
    """Convert the FOCAL MoorDyn v1-style file to MoorDyn v2 table layout."""
    out = []
    section = None
    for line in lines:
        upper = line.upper()
        if 'UnstrLen' in line and 'NodeAnch' in line:
            out.append('ID      LineType  AttachA  AttachB  UnstrLen  NumSegs  Outputs')
            continue
        if 'LINE TYPES' in upper:
            section = 'line_types'
            out.append('----------------------- LINE TYPES ------------------------------------------')
            continue
        if 'CONNECTION PROPERTIES' in upper:
            section = 'points'
            out.append('---------------------- POINTS -----------------------------------------------')
            continue
        if 'LINE PROPERTIES' in upper:
            section = 'lines'
            out.append('---------------------- LINES ------------------------------------------------')
            continue
        if 'SOLVER OPTIONS' in upper:
            section = 'solver'
            out.append(line)
            continue
        if 'OUTPUTS' in upper:
            section = 'outputs'
            out.append(line)
            continue

        parts = line.split()
        if len(parts) >= 2 and parts[1] in {'NTypes', 'NConnects', 'NLines'}:
            continue
        if section == 'line_types' and len(parts) == 9 and parts[0].isalpha():
            name, diam, massden, ea, ba, can, cat, cdn, cdt = parts[:9]
            out.append(' '.join([name, diam, massden, ea, ba, '0', cdn, can, cdt, cat]))
            continue
        if section == 'points' and len(parts) >= 12 and parts[0].isdigit():
            out.append(' '.join(parts[:7] + parts[10:12]))
            continue
        if len(parts) >= 8 and parts[0].isdigit() and len(parts) > 1 and parts[1] in {'A', 'B', 'C'}:
            line_id, line_type, unstr_len, num_segs, anchor, fairlead, outputs, ctrl = parts[:8]
            out.append(' '.join([line_id, line_type, anchor, fairlead, unstr_len, num_segs, outputs]))
            continue

        if section == 'line_types' and line.lstrip().startswith('Name'):
            out.append('Name     Diam      MassDen      EA     BA/-zeta  EI   Cd   Ca   CdAx   CaAx')
        elif section == 'line_types' and line.lstrip().startswith('(-)'):
            out.append('(-)       (m)      (kg/m)       (N)    (N-s/-)   (-)  (-)  (-)  (-)    (-)')
        elif section == 'points' and line.lstrip().startswith('Node'):
            out.append('ID      Attachment   X        Y        Z       M     V      CdA   Ca')
        elif section == 'points' and line.lstrip().startswith('(-)'):
            out.append('(-)     (-)          (m)      (m)      (m)     (kg)  (m^3)  (m^2) (-)')
        elif section == 'lines' and line.lstrip().startswith('(-)'):
            out.append('(-)     (-)       (-)      (-)      (m)       (-)      (-)')
        else:
            out.append(line)
    return out

def _ensure_hydrodyn_v4(lines):
    """Convert older/custom FOCAL HydroDyn layout to OpenFAST 4.x layout."""
    lines = list(lines)

    env_idx = next((i for i, l in enumerate(lines) if 'ENVIRONMENTAL CONDITIONS' in l), None)
    float_idx = next((i for i, l in enumerate(lines) if 'FLOATING PLATFORM' in l), None)
    if env_idx is not None and float_idx is not None and env_idx < float_idx:
        del lines[env_idx:float_idx]

    if not any(len(l.split()) >= 2 and l.split()[1] == 'PtfmYMod' for l in lines):
        for i, l in enumerate(lines):
            parts = l.split()
            if len(parts) >= 2 and parts[1] == 'ExctnCutOff':
                lines[i + 1:i + 1] = [
                    '             0   PtfmYMod       - Model for large platform yaw offset {0: static, 1: dynamic filtered PRP yaw}',
                    '             0   PtfmRefY       - Platform reference yaw offset (deg)',
                    '          0.01   PtfmYCutOff    - Cutoff frequency for low-pass filtering PRP yaw motion (Hz)',
                    '            36   NExctnHdg      - Number of platform yaw/heading angles for wave excitation (-)',
                ]
                break

    for i, l in enumerate(lines):
        if 'SimplCd' in l and 'SimplCb' not in l:
            lines[i] = (
                '     SimplCd    SimplCdMG    SimplCa    SimplCaMG    SimplCp    SimplCpMG'
                '   SimplAxCd    SimplAxCdMG   SimplAxCa  SimplAxCaMG  SimplAxCp'
                '   SimplAxCpMG    SimplCb    SimplCbMG'
            )
            if i + 2 < len(lines):
                vals = lines[i + 2].split()
                if len(vals) == 12:
                    lines[i + 2] = '        ' + '        '.join(vals + ['1', '1'])
            break

    return lines

def write_case(name, edits, ic, tmax, free_decay=True, output_dir=None):
    """Materialize a full OpenFAST case from the FOCAL C4 templates.

    Args:
        name:       case tag -> hd_<name>.dat, ed_<name>.dat, <name>.fst
        edits:      list of (block,i,j,val) HydroDyn matrix edits vs template
        ic:         dict {'Roll':10.34, ...} platform initial displacements (deg/m)
        tmax:       simulation length (s)
        free_decay: if True, disable aero/servo and lock blades (parked, still air)
        output_dir: directory to write files (default: OUTPUT_DIR from config)
    Returns:
        path to the written .fst file
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    else:
        output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) HydroDyn
    _copy_model_support_files(output_dir)
    hd_tmpl = HD_TEMPLATE.read_text(encoding='utf-8', errors='replace').splitlines()
    hd_tmpl = _ensure_hydrodyn_v4(hd_tmpl)
    hd = apply_edits(hd_tmpl, edits)
    hd_path = output_dir / f"hd_{name}.dat"
    hd_path.write_text('\n'.join(hd), encoding='utf-8')

    # 2) ElastoDyn
    ed = ED_TEMPLATE.read_text(encoding='utf-8', errors='replace').splitlines()
    _ensure_platform_cross_inertia(ed)
    _ensure_yaw_friction(ed)
    _localize_ed_references(ed, output_dir)
    for dof, key in PTFM_KEY.items():
        _set_val(ed, key, 0)
    for dof, amp in ic.items():
        _set_val(ed, PTFM_KEY[dof], amp)
    if free_decay:
        _lock_blades(ed)
    ed_path = output_dir / f"ed_{name}.dat"
    ed_path.write_text('\n'.join(ed), encoding='utf-8')

    # 3) .fst
    fst = FST_TEMPLATE.read_text(encoding='utf-8', errors='replace').splitlines()
    out = []
    for l in fst:
        p = l.split()
        if len(p) >= 2 and p[1] == 'EDFile':
            l = f'"ed_{name}.dat"        EDFile       - Name of file containing ElastoDyn input parameters (quoted string)'
        elif len(p) >= 2 and p[1] == 'HydroFile':
            l = f'"hd_{name}.dat"        HydroFile    - Name of file containing hydrodynamic input parameters (quoted string)'
        elif len(p) >= 2 and p[1] == 'TMax':
            l = f'{tmax:<13} TMax        - Total run time (s)'
        out.append(l)
    if free_decay:
        _disable_aero_servo(out)
    fst_path = output_dir / f"{name}.fst"
    fst_path.write_text('\n'.join(out), encoding='utf-8')
    return fst_path

# --------------------------------------------------------------------------- #
#  RUN side: invoke OpenFAST                                                   #
# --------------------------------------------------------------------------- #
def run_openfast(fst_path, timeout=1800):
    """Call OpenFAST on fst_path (cwd=parent dir so relative paths resolve).
    Returns (out_path, info) where info has returncode, walltime_s, ok, tail."""
    fst_path = pathlib.Path(fst_path)
    out_path = fst_path.with_suffix('.out')
    if out_path.exists():
        out_path.unlink()

    if not OPENFAST_EXE.is_file():
        raise FileNotFoundError(f"OpenFAST executable not found: {OPENFAST_EXE}\n"
                              f"Set OPENFAST_EXE in config.py or environment variable")

    t0 = time.time()
    proc = subprocess.run([str(OPENFAST_EXE), fst_path.name], cwd=str(fst_path.parent),
                          capture_output=True, encoding='utf-8', errors='replace',
                          timeout=timeout)
    dt = time.time() - t0
    tail = (proc.stdout or '')[-1500:]
    ok = (proc.returncode == 0) and out_path.exists()
    info = dict(returncode=proc.returncode, walltime_s=dt, ok=ok,
                tail=tail, stderr=(proc.stderr or '')[-800:])
    return out_path, info

# --------------------------------------------------------------------------- #
#  READ side: parse .out and compute model-vs-data morphology metrics          #
# --------------------------------------------------------------------------- #
def read_out(out_path, channels):
    """Fast OpenFAST .out loader: Time + requested channels -> dict of np arrays."""
    lines = pathlib.Path(out_path).read_text(encoding='utf-8', errors='replace').splitlines()
    hi = next(i for i, l in enumerate(lines) if l.lstrip().startswith('Time'))
    cols = lines[hi].split()
    ci = {c: cols.index(c) for c in (['Time'] + channels)}
    data = np.genfromtxt(lines[hi + 2:], usecols=[ci['Time']] + [ci[c] for c in channels])
    out = {'Time': data[:, 0]}
    for k, c in enumerate(channels):
        out[c] = data[:, k + 1]
    return out

def _env(x, dt):
    """Hilbert envelope with smoothing."""
    N = len(x); X = np.fft.fft(x); h = np.zeros(N)
    if N % 2 == 0:
        h[0] = h[N // 2] = 1; h[1:N // 2] = 2
    else:
        h[0] = 1; h[1:(N + 1) // 2] = 2
    e = np.abs(np.fft.ifft(X * h))
    w = max(3, int(0.5 / dt)); k = np.ones(w) / w
    return np.convolve(e, k, 'same')

def decay_seg(t, x, floor=0.02):
    """Extract decay segment: center on equilibrium, trim to [peak, floor*peak]."""
    dt = np.median(np.diff(t)); eq = np.median(x[-len(x) // 4:]); xc = x - eq
    env = _env(xc, dt); i0 = int(np.argmax(env)); thr = floor * env[i0]
    i1 = len(t) - 1
    for i in range(len(t) - 1, i0, -1):
        if env[i] > thr:
            i1 = i; break
    return t[i0:i1 + 1] - t[i0], xc[i0:i1 + 1], env[i0:i1 + 1]

def morph_metrics(tM, xM, eM, tD, xD, eD):
    """Model-vs-data morphology on the common overlap window."""
    Tend = min(tM[-1], tD[-1]); m = tD <= Tend
    tg = tD[m]; xDg = xD[m]; eDg = eD[m]
    xMg = np.interp(tg, tM, xM); eMg = np.interp(tg, tM, eM)
    rms = lambda a: np.sqrt(np.mean(a ** 2))
    J_wave = rms(xMg - xDg) / (xDg.max() - xDg.min())
    fl = 0.05 * max(eDg.max(), eMg.max())
    xhatD = xDg / np.maximum(eDg, fl); xhatM = xMg / np.maximum(eMg, fl)
    J_shape = rms(xhatM - xhatD) / rms(xhatD)
    env_err = rms(eMg - eDg) / rms(eDg)
    A1D = eDg[:max(3, len(eDg) // 20)].max(); A1M = eMg[:max(3, len(eMg) // 20)].max()
    fp_err = abs(A1M - A1D) / A1D
    q = len(xDg) // 4
    LERD = np.sum(xDg[-q:] ** 2) / np.sum(xDg[:q] ** 2)
    LERM = np.sum(xMg[-q:] ** 2) / np.sum(xMg[:q] ** 2)
    return dict(J_wave=J_wave, J_shape=J_shape, env_err=env_err, fp_err=fp_err,
                LERD=LERD, LERM=LERM, LER_err=abs(LERM - LERD) / LERD, Tend=Tend)


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 70)
    print("driver_c4.py self-check (FOCAL Campaign-4 as-built model)")
    print("=" * 70)
    print(f"  MODEL: {MODEL}")
    print(f"  MODEL exists: {MODEL.is_dir()}")
    print(f"  OPENFAST_EXE: {OPENFAST_EXE}")
    print(f"  EXE exists: {OPENFAST_EXE.is_file()}")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    print()

    print("Template files:")
    for fname in ['FOCAL_C4.fst', 'FOCAL_C4_HydroDyn.dat', 'FOCAL_C4_ElastoDyn.dat']:
        fpath = MODEL / fname
        print(f"  {fname}: {'✓' if fpath.is_file() else '❌'}")
    print()

    if HD_TEMPLATE.is_file():
        print("FOCAL C4 baseline HydroDyn matrices:")
        tmpl = HD_TEMPLATE.read_text(encoding='utf-8', errors='replace').splitlines()
        for tag in ('AddCLin', 'AddBLin', 'AddBQuad'):
            s = _block_start(tmpl, tag)
            M = _read_matrix(tmpl, s)
            print(f"  {tag:8} diag = {np.diag(M)}")
        print()

    if ED_TEMPLATE.is_file():
        print("FOCAL C4 platform properties:")
        ed = ED_TEMPLATE.read_text(encoding='utf-8', errors='replace').splitlines()
        for key in ['PtfmMass','PtfmRIner','PtfmPIner','PtfmYIner']:
            for l in ed:
                parts = l.split()
                if len(parts) >= 2 and parts[1] == key:
                    print(f"  {key:12} = {parts[0]}")
                    break
        print()

    print("Key differences from IEA-15MW standard model:")
    print("  • AddCLin: Surge=6860, Heave=62200 (umbilical stiffness)")
    print("  • AddBLin: Surge/Sway=1.6e5, Roll/Pitch=2.7e8")
    print("  • AddBQuad: Roll/Pitch/Yaw=7.2e10 (4.3× higher than IEA-15MW)")
    print("  • PtfmRIner ≠ PtfmPIner (asymmetric platform)")
    print("  • Mooring: MoorDyn linear springs (not MAP++ catenary)")
    print("=" * 70)
