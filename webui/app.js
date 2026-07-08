const state = {
  meta: null,
  scenarioFile: 'ui_scenario.json',
  scenario: { name: 'ui_scenario', description: 'Created from visual UI', cases: [] },
  selectedCase: 0,
  selectedModelId: localStorage.getItem('openfastGui.modelId') || '',
  selectedRuntimeId: localStorage.getItem('openfastGui.runtimeId') || '',
  currentJob: null,
  pollTimer: null,
  jobRunning: false
};

const $ = (id) => document.getElementById(id);
const DOFS = ['Surge', 'Sway', 'Heave', 'Roll', 'Pitch', 'Yaw'];
const MATRIX_BLOCKS = [
  ['CLin', 'AddCLin 线性刚度'],
  ['BLin', 'AddBLin 线性阻尼'],
  ['BQuad', 'AddBQuad 二次阻尼/拖曳']
];
const HYDRO_VISIBLE_COLUMNS = {
  axial: ['AxCoefID', 'AxCd', 'AxCa', 'AxCp', 'AxFDMod', 'AxVnCOff', 'AxFDLoFSc'],
  joints: ['JointID', 'Jointxi', 'Jointyi', 'Jointzi', 'JointAxID', 'JointOvrlp'],
  prop_sets_cyl: ['PropSetID', 'PropD', 'PropThck'],
  members: ['MemberID', 'MJointID1', 'MJointID2', 'MPropSetID1', 'MPropSetID2', 'MSecGeom', 'MSpinOrient', 'MDivSize', 'MCoefMod', 'MHstLMod', 'PropPot'],
  simple_cyl: ['SimplCd', 'SimplCdMG', 'SimplCa', 'SimplCaMG', 'SimplCp', 'SimplCpMG', 'SimplAxCd', 'SimplAxCdMG', 'SimplAxCa', 'SimplAxCaMG', 'SimplAxCp', 'SimplAxCpMG', 'SimplCb', 'SimplCbMG'],
  member_coeffs_cyl: ['MemberID', 'MemberCd1', 'MemberCd2', 'MemberCdMG1', 'MemberCdMG2', 'MemberCa1', 'MemberCa2', 'MemberCaMG1', 'MemberCaMG2', 'MemberCp1', 'MemberCp2', 'MemberCpMG1', 'MemberCpMG2', 'MemberAxCd1', 'MemberAxCd2', 'MemberAxCdMG1', 'MemberAxCdMG2', 'MemberAxCa1', 'MemberAxCa2', 'MemberAxCaMG1', 'MemberAxCaMG2', 'MemberAxCp1', 'MemberAxCp2', 'MemberAxCpMG1', 'MemberAxCpMG2', 'MemberCb1', 'MemberCb2', 'MemberCbMG1', 'MemberCbMG2']
};
const HYDRO_TABLE_TITLES = {
  axial: '轴向系数',
  joints: '节点',
  prop_sets_cyl: '圆柱截面属性',
  members: 'Morison 构件',
  simple_cyl: 'Simple Cd/Ca/Cp',
  member_coeffs_cyl: '成员独立 Cd/Ca/Cp'
};

function activeFiles() {
  const profile = state.meta?.modelProfile || {};
  return {
    fst: profile.fst || 'FOCAL_C4.fst',
    inflow: profile.inflowFile || 'FOCAL_C4_InflowFile.dat',
    sea: profile.seaStateFile || 'SeaState_DLC_1p6.dat',
    seaStateCompKey: profile.seaStateCompKey || 'CompSeaState',
    defaultMooring: Number(profile.defaultMooring ?? 3)
  };
}

function targetFormatForRuntime() {
  return state.meta?.hydroTables?.runtimeFormat === 'v5' ? 'v5' : 'auto_v4_runtime';
}

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2400);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || response.statusText);
  return data;
}

function emptyCase() {
  const files = activeFiles();
  return {
    name: `case_${String(state.scenario.cases.length + 1).padStart(2, '0')}`,
    notes: '',
    set: {
      [files.fst]: {
        TMax: 120,
        CompElast: 1,
        CompInflow: 1,
        CompAero: 2,
        CompServo: 1,
        [files.seaStateCompKey]: 1,
        CompHydro: 1,
        CompMooring: files.defaultMooring
      }
    },
    matrix_edits: []
  };
}

function normalizeScenario() {
  if (!Array.isArray(state.scenario.cases)) state.scenario.cases = [];
  if (!state.scenario.cases.length) state.scenario.cases.push(emptyCase());
  state.selectedCase = Math.min(state.selectedCase, state.scenario.cases.length - 1);
}

function currentCase() {
  normalizeScenario();
  return state.scenario.cases[state.selectedCase];
}

function setDeep(file, key, value) {
  const c = currentCase();
  if (!c.set) c.set = {};
  if (!c.set[file]) c.set[file] = {};
  c.set[file][key] = value;
}

function removeDeep(file, key) {
  const c = currentCase();
  if (c.set?.[file]) {
    delete c.set[file][key];
    if (!Object.keys(c.set[file]).length) delete c.set[file];
  }
}

function renderAll() {
  normalizeScenario();
  $('workspacePath').textContent = state.meta?.root || '';
  renderProfileControls();
  $('scenarioFile').value = state.scenarioFile;
  $('scenarioName').value = state.scenario.name || '';
  $('scenarioDescription').value = state.scenario.description || '';
  renderPresets();
  renderScenarioList();
  renderInterfaces();
  renderDocs();
  renderCases();
  renderReferenceFigures();
  renderModuleSwitches();
  renderAdvancedRows();
  renderHydroTables();
  renderCatalog();
  renderJson();
}

function renderReferenceFigures() {
  const panel = $('referencePanel');
  const wrap = $('referenceFigures');
  if (!panel || !wrap) return;
  const figures = [
    ...(state.scenario.reference_figures || []),
    ...(currentCase().reference_figures || [])
  ];
  panel.style.display = figures.length ? '' : 'none';
  wrap.innerHTML = '';
  for (const figure of figures) {
    const card = document.createElement('div');
    card.className = 'reference-card';
    const img = document.createElement('img');
    img.src = figure.url || figure.path || '';
    img.alt = figure.label || 'reference figure';
    const caption = document.createElement('div');
    caption.className = 'reference-caption';
    caption.textContent = `${figure.label || 'Reference'}${figure.source ? ` | ${figure.source}` : ''}`;
    card.appendChild(img);
    card.appendChild(caption);
    wrap.appendChild(card);
  }
}

function renderProfileControls() {
  const modelSelect = $('modelSelect');
  const runtimeSelect = $('runtimeSelect');
  if (!modelSelect || !runtimeSelect || !state.meta) return;
  state.selectedModelId = state.meta.selectedModelId || state.selectedModelId;
  state.selectedRuntimeId = state.meta.selectedRuntimeId || state.selectedRuntimeId;

  modelSelect.innerHTML = '';
  for (const model of state.meta.modelProfiles || []) {
    const option = document.createElement('option');
    option.value = model.id;
    option.textContent = `${model.exists && model.fstExists ? 'OK' : 'MISSING'} ${model.name}`;
    modelSelect.appendChild(option);
  }
  modelSelect.value = state.selectedModelId;

  runtimeSelect.innerHTML = '';
  for (const runtime of state.meta.runtimeProfiles || []) {
    const option = document.createElement('option');
    option.value = runtime.id;
    option.textContent = `${runtime.exists ? 'OK' : 'MISSING'} ${runtime.name}`;
    runtimeSelect.appendChild(option);
  }
  runtimeSelect.value = state.selectedRuntimeId;

  const model = state.meta.modelProfile || {};
  const runtime = state.meta.runtimeProfile || {};
  $('profileStatus').textContent = [
    `model: ${model.fst || ''}`,
    `runtime: ${runtime.version || runtime.runtimeFormat || ''}`,
    `hydro: ${model.hydroFile || ''}`
  ].join('\n');
}

function renderPresets() {
  const select = $('presetSelect');
  select.innerHTML = '';
  for (const preset of state.meta.modulePresets) {
    const option = document.createElement('option');
    option.value = preset.id;
    option.textContent = preset.name;
    select.appendChild(option);
  }
  updatePresetDescription();
}

function updatePresetDescription() {
  const preset = state.meta?.modulePresets.find(p => p.id === $('presetSelect').value);
  $('presetDescription').textContent = preset?.description || '';
}

function renderScenarioList() {
  const wrap = $('scenarioList');
  wrap.innerHTML = '';
  for (const item of state.scenarioList || []) {
    const div = document.createElement('div');
    div.className = `scenario-item ${item.file === state.scenarioFile ? 'active' : ''}`;
    div.innerHTML = `<div class="item-title"><span>${item.name}</span><span class="badge">${item.cases}</span></div><div class="item-meta">${item.file}<br>${item.description || ''}</div>`;
    div.onclick = () => loadScenario(item.file);
    wrap.appendChild(div);
  }
}

function renderInterfaces() {
  const wrap = $('interfaceModes');
  wrap.innerHTML = '';
  for (const mode of state.meta.interfaceModes) {
    const div = document.createElement('div');
    div.className = 'mode-item';
    div.innerHTML = `<div class="item-title"><span>${mode.name}</span><span class="badge ${mode.status}">${mode.status}</span></div><div class="item-meta">${mode.entry}<br>${mode.scope}</div>`;
    wrap.appendChild(div);
  }
}

function renderDocs() {
  const wrap = $('docLinks');
  wrap.innerHTML = '';
  for (const link of state.meta.docLinks) {
    const a = document.createElement('a');
    a.href = link.url;
    a.target = '_blank';
    a.rel = 'noreferrer';
    a.textContent = link.label;
    wrap.appendChild(a);
  }
}

function renderCases() {
  const wrap = $('caseList');
  wrap.innerHTML = '';
  state.scenario.cases.forEach((c, index) => {
    const div = document.createElement('div');
    div.className = `case-item ${index === state.selectedCase ? 'active' : ''}`;
    const setCount = Object.values(c.set || {}).reduce((n, values) => n + Object.keys(values).length, 0);
    div.innerHTML = `<div class="item-title"><span>${c.name || `case_${index + 1}`}</span><span class="badge">${setCount} keys</span></div><div class="item-meta">${c.notes || ''}</div>`;
    div.onclick = () => { state.selectedCase = index; renderAll(); };
    wrap.appendChild(div);
  });
  const c = currentCase();
  $('caseName').value = c.name || '';
  $('caseNotes').value = c.notes || '';
}

function renderModuleSwitches() {
  const wrap = $('moduleSwitches');
  const files = activeFiles();
  const keys = [
    ['CompElast', 'Structure', [1, 2, 3]],
    ['CompInflow', 'InflowWind', [0, 1, 2]],
    ['CompAero', 'Aero', [0, 1, 2, 3]],
    ['CompServo', 'Servo', [0, 1]],
    [files.seaStateCompKey, 'SeaState', [0, 1]],
    ['CompHydro', 'Hydro', [0, 1]],
    ['CompSub', 'SubDyn', [0, 1]],
    ['CompMooring', 'Mooring', [0, 1, 2, 3, 4]],
    ['CompIce', 'Ice', [0, 1, 2]],
    ['MHK', 'MHK', [0, 1, 2]]
  ];
  const fst = currentCase().set?.[files.fst] || {};
  wrap.innerHTML = '';
  for (const [key, label, values] of keys) {
    const div = document.createElement('div');
    div.className = 'toggle';
    const select = document.createElement('select');
    const templateOption = document.createElement('option');
    templateOption.value = '';
    templateOption.textContent = 'template';
    select.appendChild(templateOption);
    for (const value of values) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    }
    select.value = fst[key] ?? '';
    select.onchange = () => {
      if (select.value === '') removeDeep(files.fst, key);
      else setDeep(files.fst, key, Number(select.value));
      renderJson();
    };
    div.innerHTML = `<label>${label}</label><small>${key}</small>`;
    div.appendChild(select);
    wrap.appendChild(div);
  }
}

function renderAdvancedRows() {
  renderSetRows();
  renderMatrixRows();
}

function setEntries() {
  const c = currentCase();
  const rows = [];
  for (const [file, values] of Object.entries(c.set || {})) {
    for (const [key, value] of Object.entries(values)) rows.push({ file, key, value });
  }
  return rows;
}

function baselineMatrixValue(block, i, j) {
  return Number(state.meta?.hydroMatrices?.[block]?.[i - 1]?.[j - 1] ?? 0);
}

function valuesEqual(a, b) {
  const left = Number(a);
  const right = Number(b);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  return Math.abs(left - right) <= Math.max(1, Math.abs(left), Math.abs(right)) * 1e-12;
}

function normalizedMatrixEdits(writeBack = false) {
  const c = currentCase();
  const raw = Array.isArray(c.matrix_edits) ? c.matrix_edits : [];
  const blockOrder = new Map(MATRIX_BLOCKS.map(([block], index) => [block, index]));
  const byCell = new Map();
  for (const edit of raw) {
    const block = String(edit.block || '').trim();
    const i = Number(edit.i);
    const j = Number(edit.j);
    const value = Number(edit.value);
    if (!blockOrder.has(block) || !Number.isInteger(i) || !Number.isInteger(j)) continue;
    if (i < 1 || i > 6 || j < 1 || j > 6 || !Number.isFinite(value)) continue;
    byCell.set(`${block}:${i}:${j}`, { block, i, j, value });
  }
  const edits = Array.from(byCell.values()).sort((a, b) =>
    blockOrder.get(a.block) - blockOrder.get(b.block) || a.i - b.i || a.j - b.j
  );
  if (writeBack) {
    if (edits.length) c.matrix_edits = edits;
    else delete c.matrix_edits;
  }
  return edits;
}

function findMatrixEdit(block, i, j) {
  return normalizedMatrixEdits().find(edit => edit.block === block && edit.i === i && edit.j === j);
}

function hasMatrixEdit(block, i, j) {
  return Boolean(findMatrixEdit(block, i, j));
}

function matrixValue(block, i, j) {
  const edit = findMatrixEdit(block, i, j);
  return edit ? edit.value : baselineMatrixValue(block, i, j);
}

function setMatrixValue(block, i, j, rawValue) {
  const value = Number(String(rawValue).trim());
  if (!Number.isFinite(value)) {
    toast('矩阵单元格必须是有效数字');
    renderMatrixRows();
    return;
  }
  const c = currentCase();
  const baseline = baselineMatrixValue(block, i, j);
  const next = normalizedMatrixEdits().filter(edit => !(edit.block === block && edit.i === i && edit.j === j));
  if (!valuesEqual(value, baseline)) next.push({ block, i, j, value });
  if (next.length) c.matrix_edits = next;
  else delete c.matrix_edits;
  normalizedMatrixEdits(true);
  renderMatrixRows();
  renderJson();
}

function formatMatrixValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '0';
  if (number === 0) return '0';
  const abs = Math.abs(number);
  if (abs >= 1e5 || abs < 1e-3) {
    return number.toExponential(6).replace(/\.?0+e/, 'e').replace('e+', 'e');
  }
  return String(Number(number.toPrecision(10)));
}

function cloneData(value) {
  return JSON.parse(JSON.stringify(value ?? {}));
}

function baseHydroPayload() {
  const meta = state.meta?.hydroTables || {};
  return {
    target_format: targetFormatForRuntime(),
    tables: cloneData(meta.tables || {}),
    schemas: cloneData(meta.schemas || {}),
    format: meta.format || 'legacy_v4',
    runtimeFormat: meta.runtimeFormat || 'v4'
  };
}

function ensureCaseHydroTables() {
  const c = currentCase();
  if (!c.hydrodyn_tables || !c.hydrodyn_tables.tables) {
    const base = baseHydroPayload();
    c.hydrodyn_tables = { target_format: base.target_format, tables: base.tables };
  }
  if (!c.hydrodyn_tables.target_format || (c.hydrodyn_tables.target_format === 'auto_v4_runtime' && targetFormatForRuntime() === 'v5')) {
    c.hydrodyn_tables.target_format = targetFormatForRuntime();
  }
  return c.hydrodyn_tables;
}

function hydroPayloadView() {
  const c = currentCase();
  if (c.hydrodyn_tables?.tables) return c.hydrodyn_tables;
  return baseHydroPayload();
}

function hydroTablesView() {
  return hydroPayloadView().tables || {};
}

function hydroSchemas() {
  return state.meta?.hydroTables?.schemas || {};
}

function hydroRows(tableName) {
  const rows = hydroTablesView()[tableName];
  return Array.isArray(rows) ? rows : [];
}

function hydroObject(tableName) {
  const obj = hydroTablesView()[tableName];
  return obj && !Array.isArray(obj) ? obj : {};
}

function hydroColumns(tableName) {
  const schema = hydroSchemas()[tableName] || [];
  const preferred = HYDRO_VISIBLE_COLUMNS[tableName] || schema;
  const filtered = preferred.filter(col => !schema.length || schema.includes(col));
  return filtered.length ? filtered : schema;
}

function coerceHydroValue(field, raw) {
  const text = String(raw).trim();
  if (field === 'PropPot') return /^true$/i.test(text);
  if (/ID|Mod|Ovrlp|Geom$/.test(field) || ['NOutLoc', 'FDMod'].includes(field)) {
    const n = Number(text);
    return Number.isFinite(n) ? Math.trunc(n) : text;
  }
  return parseValue(text);
}

function setHydroCell(tableName, index, field, rawValue, objectTable = false) {
  const payload = ensureCaseHydroTables();
  if (!payload.tables[tableName]) payload.tables[tableName] = objectTable ? {} : [];
  const target = objectTable ? payload.tables[tableName] : payload.tables[tableName][index];
  if (!target) return;
  target[field] = coerceHydroValue(field, rawValue);
  renderHydroTables();
  renderJson();
}

function deleteHydroRow(tableName, index) {
  const payload = ensureCaseHydroTables();
  if (!Array.isArray(payload.tables[tableName])) payload.tables[tableName] = [];
  const deleted = payload.tables[tableName][index];
  payload.tables[tableName].splice(index, 1);
  if (tableName === 'members' && deleted) {
    const memberId = Number(deleted.MemberID);
    if (Array.isArray(payload.tables.member_coeffs_cyl)) {
      payload.tables.member_coeffs_cyl = payload.tables.member_coeffs_cyl.filter(row => Number(row.MemberID) !== memberId);
    }
    if (Array.isArray(payload.tables.member_coeffs_rec)) {
      payload.tables.member_coeffs_rec = payload.tables.member_coeffs_rec.filter(row => Number(row.MemberID) !== memberId);
    }
  }
  renderHydroTables();
  renderJson();
}

function nextHydroId(rows, key) {
  const used = rows.map(row => Number(row[key])).filter(Number.isFinite);
  return used.length ? Math.max(...used) + 1 : 1;
}

function firstNonZero(values, fallback = 1) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && number !== 0) return number;
  }
  return fallback;
}

function coeffDefault(simple, family, mg = false) {
  if (family === 'Cd') return firstNonZero([simple[mg ? 'SimplCdMG' : 'SimplCd'], simple.SimplCd, simple.SimplCdA, simple.SimplCdB], 1);
  if (family === 'Ca') return firstNonZero([simple[mg ? 'SimplCaMG' : 'SimplCa'], simple.SimplCa, simple.SimplCaA, simple.SimplCaB], 1);
  if (family === 'Cp') return firstNonZero([simple[mg ? 'SimplCpMG' : 'SimplCp'], simple.SimplCp], 1);
  if (family === 'AxCd') return firstNonZero([simple[mg ? 'SimplAxCdMG' : 'SimplAxCd'], simple.SimplAxCd], coeffDefault(simple, 'Cd', mg));
  if (family === 'AxCa') return firstNonZero([simple[mg ? 'SimplAxCaMG' : 'SimplAxCa'], simple.SimplAxCa], coeffDefault(simple, 'Ca', mg));
  if (family === 'AxCp') return firstNonZero([simple[mg ? 'SimplAxCpMG' : 'SimplAxCp'], simple.SimplAxCp], coeffDefault(simple, 'Cp', mg));
  if (family === 'Cb') return firstNonZero([simple[mg ? 'SimplCbMG' : 'SimplCb'], simple.SimplCb], 1);
  return 1;
}

function createMemberCoeffRow(memberId, fields, simple) {
  const row = {};
  for (const field of fields) {
    if (field === 'MemberID') row[field] = memberId;
    else if (field.includes('AxCd')) row[field] = coeffDefault(simple, 'AxCd', field.includes('MG'));
    else if (field.includes('AxCa')) row[field] = coeffDefault(simple, 'AxCa', field.includes('MG'));
    else if (field.includes('AxCp')) row[field] = coeffDefault(simple, 'AxCp', field.includes('MG'));
    else if (field.includes('Cd')) row[field] = coeffDefault(simple, 'Cd', field.includes('MG'));
    else if (field.includes('Ca')) row[field] = coeffDefault(simple, 'Ca', field.includes('MG'));
    else if (field.includes('Cp')) row[field] = coeffDefault(simple, 'Cp', field.includes('MG'));
    else if (field.includes('Cb')) row[field] = coeffDefault(simple, 'Cb', field.includes('MG'));
    else row[field] = 0;
  }
  return row;
}

function repairHydroReferences(payload) {
  const t = payload?.tables;
  if (!t) return [];
  const warnings = [];
  for (const name of ['joints', 'prop_sets_cyl', 'member_coeffs_cyl', 'members']) {
    if (!Array.isArray(t[name])) t[name] = [];
  }

  const fixedJoints = [];
  for (const joint of t.joints) {
    if (Number(joint.JointOvrlp || 0) !== 0) {
      joint.JointOvrlp = 0;
      fixedJoints.push(joint.JointID);
    }
  }
  if (fixedJoints.length) warnings.push(`OpenFAST v4 requires JointOvrlp=0; fixed joints ${fixedJoints.join(', ')}`);

  const propIds = new Set(t.prop_sets_cyl.map(row => Number(row.PropSetID)).filter(Number.isFinite));
  const coeffIds = new Set(t.member_coeffs_cyl.map(row => Number(row.MemberID)).filter(Number.isFinite));
  const coeffFields = hydroSchemas().member_coeffs_cyl || HYDRO_VISIBLE_COLUMNS.member_coeffs_cyl;

  for (const member of t.members) {
    const memberId = Number(member.MemberID);
    if (member.MDivSize === undefined) member.MDivSize = 0.5;
    if (member.MCoefMod === undefined) member.MCoefMod = 1;
    if (member.MHstLMod === undefined) member.MHstLMod = 0;
    if (member.PropPot === undefined) member.PropPot = false;
    const shape = Number(member.MSecGeom || 1);
    if (shape !== 2) {
      for (const field of ['MPropSetID1', 'MPropSetID2']) {
        const propId = Number(member[field]);
        if (Number.isFinite(propId) && propId > 0 && !propIds.has(propId)) {
          t.prop_sets_cyl.push({ PropSetID: propId, PropD: 6, PropThck: 0.06 });
          propIds.add(propId);
          warnings.push(`自动补齐 Member ${memberId} 引用的 PropSetID ${propId}`);
        }
      }
    }
    if (Number(member.MCoefMod || 1) === 3 && Number.isFinite(memberId) && !coeffIds.has(memberId)) {
      t.member_coeffs_cyl.push(createMemberCoeffRow(memberId, coeffFields, t.simple_cyl || {}));
      coeffIds.add(memberId);
      warnings.push(`自动补齐 Member ${memberId} 的独立系数行`);
    }
  }

  t.prop_sets_cyl.sort((a, b) => Number(a.PropSetID) - Number(b.PropSetID));
  t.member_coeffs_cyl.sort((a, b) => Number(a.MemberID) - Number(b.MemberID));
  return warnings;
}

function repairScenarioHydroReferences(scenario) {
  const warnings = [];
  for (const c of scenario.cases || []) {
    for (const warning of repairHydroReferences(c.hydrodyn_tables)) {
      warnings.push(`${c.name || 'case'}: ${warning}`);
    }
  }
  return warnings;
}

function addDefaultMorisonMember() {
  const payload = ensureCaseHydroTables();
  const t = payload.tables;
  for (const name of ['axial', 'joints', 'prop_sets_cyl', 'member_coeffs_cyl', 'members']) {
    if (!Array.isArray(t[name])) t[name] = [];
  }

  if (!t.axial.length) {
    t.axial.push({ AxCoefID: 1, AxCd: 1, AxCa: 1, AxCp: 1, AxFDMod: 0, AxVnCOff: 0, AxFDLoFSc: 1 });
  }
  const axId = Number(t.axial[0].AxCoefID) || 1;
  const joint1 = nextHydroId(t.joints, 'JointID');
  const joint2 = joint1 + 1;
  const propId = nextHydroId(t.prop_sets_cyl, 'PropSetID');
  const memberId = nextHydroId(t.members, 'MemberID');

  t.joints.push({ JointID: joint1, Jointxi: 0, Jointyi: 0, Jointzi: -20, JointAxID: axId, JointOvrlp: 0 });
  t.joints.push({ JointID: joint2, Jointxi: 0, Jointyi: 0, Jointzi: 10, JointAxID: axId, JointOvrlp: 0 });
  t.prop_sets_cyl.push({ PropSetID: propId, PropD: 6, PropThck: 0.06 });

  t.members.push({
    MemberID: memberId,
    MJointID1: joint1,
    MJointID2: joint2,
    MPropSetID1: propId,
    MPropSetID2: propId,
    MSecGeom: 1,
    MSpinOrient: 0,
    MDivSize: 0.5,
    MCoefMod: 3,
    MHstLMod: 0,
    PropPot: false
  });

  const coeffFields = hydroSchemas().member_coeffs_cyl || HYDRO_VISIBLE_COLUMNS.member_coeffs_cyl;
  t.member_coeffs_cyl.push(createMemberCoeffRow(memberId, coeffFields, t.simple_cyl || {}));
  renderAll();
  toast(`已添加 Morison 构件 ${memberId}`);
}

function hydrodynRuntimeErrors(payload = currentCase().hydrodyn_tables) {
  if (!payload?.tables) return [];
  const target = payload.target_format || 'auto_v4_runtime';
  const t = payload.tables;
  const errors = [];
  const v4Target = ['auto_v4_runtime', 'v4', 'legacy_v4'].includes(target);
  if (v4Target) {
    if ((t.prop_sets_rec || []).length || (t.depth_rec || []).length || (t.member_coeffs_rec || []).length) {
      errors.push('当前 openfast_x64.exe 是 v4，不能运行 v5 矩形 HydroDyn 表。');
    }
    for (const member of t.members || []) {
      if (Number(member.MSecGeom || 1) === 2) errors.push(`Member ${member.MemberID} 是矩形构件，当前 v4 runtime 不支持。`);
    }
  }
  const memberIds = new Set((t.members || []).map(row => Number(row.MemberID)));
  const coeffIds = new Set((t.member_coeffs_cyl || []).map(row => Number(row.MemberID)));
  const jointIds = new Set((t.joints || []).map(row => Number(row.JointID)));
  const propIds = new Set((t.prop_sets_cyl || []).map(row => Number(row.PropSetID)));
  const jointById = new Map((t.joints || []).map(row => [Number(row.JointID), row]));
  const propById = new Map((t.prop_sets_cyl || []).map(row => [Number(row.PropSetID), row]));
  const truthy = value => value === true || value === 1 || ['true', 't', '1', '.true.'].includes(String(value).toLowerCase());
  const endpointNearWater = (jointId, propId) => {
    const joint = jointById.get(Number(jointId));
    const prop = propById.get(Number(propId));
    if (!joint || !prop) return false;
    const z = Number(joint.Jointzi);
    const d = Math.abs(Number(prop.PropD));
    return Number.isFinite(z) && Number.isFinite(d) && Math.abs(z) < d / 2;
  };
  for (const member of t.members || []) {
    if (jointIds.size && !jointIds.has(Number(member.MJointID1))) errors.push(`Member ${member.MemberID} 缺少节点 MJointID1=${member.MJointID1}`);
    if (jointIds.size && !jointIds.has(Number(member.MJointID2))) errors.push(`Member ${member.MemberID} 缺少节点 MJointID2=${member.MJointID2}`);
    if (!propIds.has(Number(member.MPropSetID1))) errors.push(`Member ${member.MemberID} 缺少截面属性 MPropSetID1=${member.MPropSetID1}`);
    if (!propIds.has(Number(member.MPropSetID2))) errors.push(`Member ${member.MemberID} 缺少截面属性 MPropSetID2=${member.MPropSetID2}`);
    if (Number(member.MCoefMod || 1) === 3 && !coeffIds.has(Number(member.MemberID))) {
      errors.push(`Member ${member.MemberID} 使用 MCoefMod=3，但缺少成员独立系数行。`);
    }
    if (v4Target && Number(member.MHstLMod || 0) === 1 && !truthy(member.PropPot)) {
      if (endpointNearWater(member.MJointID1, member.MPropSetID1) || endpointNearWater(member.MJointID2, member.MPropSetID2)) {
        errors.push(`Member ${member.MemberID} 的 MHstLMod=1 且端点太接近水面；v4 会报端板穿过水面。可改 MHstLMod=0，或把端点移到水面以下超过半径的位置。`);
      }
    }
  }
  for (const coeff of t.member_coeffs_cyl || []) {
    if (memberIds.size && !memberIds.has(Number(coeff.MemberID))) {
      errors.push(`成员系数 ${coeff.MemberID} 没有对应 Morison member。`);
    }
  }
  return errors;
}

function hydrodynReferenceWarnings(payload = hydroPayloadView()) {
  const t = payload?.tables || {};
  const warnings = [];
  const members = t.members || [];
  const usedJoints = new Set();
  const usedProps = new Set();
  for (const member of members) {
    usedJoints.add(Number(member.MJointID1));
    usedJoints.add(Number(member.MJointID2));
    usedProps.add(Number(member.MPropSetID1));
    usedProps.add(Number(member.MPropSetID2));
  }
  const orphanJoints = (t.joints || []).map(row => Number(row.JointID)).filter(id => Number.isFinite(id) && members.length && !usedJoints.has(id));
  const orphanProps = (t.prop_sets_cyl || []).map(row => Number(row.PropSetID)).filter(id => Number.isFinite(id) && members.length && !usedProps.has(id));
  if (orphanJoints.length) warnings.push(`未被 member 使用的节点: ${orphanJoints.join(', ')}`);
  if (orphanProps.length) warnings.push(`未被 member 使用的截面属性: ${orphanProps.join(', ')}`);
  return warnings;
}

function renderHydroTable(containerId, tableName, { objectTable = false } = {}) {
  const wrap = $(containerId);
  if (!wrap) return;
  const columns = hydroColumns(tableName);
  const rows = objectTable ? [hydroObject(tableName)] : hydroRows(tableName);
  wrap.innerHTML = '';
  if (!columns.length) {
    wrap.innerHTML = '<p class="hint">模板中未找到该表。</p>';
    return;
  }

  const panel = document.createElement('div');
  panel.className = 'data-table-wrap';
  const table = document.createElement('table');
  table.className = 'data-table';
  const head = document.createElement('thead');
  const trh = document.createElement('tr');
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    trh.appendChild(th);
  });
  if (!objectTable) {
    const th = document.createElement('th');
    th.textContent = '';
    trh.appendChild(th);
  }
  head.appendChild(trh);
  table.appendChild(head);

  const body = document.createElement('tbody');
  if (!rows.length || objectTable && !Object.keys(rows[0] || {}).length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = columns.length + (objectTable ? 0 : 1);
    td.className = 'empty-cell';
    td.textContent = objectTable ? '模板中未找到该系数行。' : '当前为 0 行。';
    tr.appendChild(td);
    body.appendChild(tr);
  } else {
    rows.forEach((row, index) => {
      const tr = document.createElement('tr');
      columns.forEach(col => {
        const td = document.createElement('td');
        const input = document.createElement('input');
        input.value = row[col] ?? '';
        input.title = `${HYDRO_TABLE_TITLES[tableName] || tableName}.${col}`;
        input.onchange = () => setHydroCell(tableName, index, col, input.value, objectTable);
        td.appendChild(input);
        tr.appendChild(td);
      });
      if (!objectTable) {
        const td = document.createElement('td');
        const btn = document.createElement('button');
        btn.className = 'remove';
        btn.textContent = '删';
        btn.onclick = () => deleteHydroRow(tableName, index);
        td.appendChild(btn);
        tr.appendChild(td);
      }
      body.appendChild(tr);
    });
  }
  table.appendChild(body);
  panel.appendChild(table);
  wrap.appendChild(panel);
}

function renderHydroTables() {
  if (!$('hydroStatus')) return;
  const payload = hydroPayloadView();
  const t = payload.tables || {};
  const custom = Boolean(currentCase().hydrodyn_tables?.tables);
  const baseWarnings = state.meta?.hydroTables?.warnings || [];
  const runtimeErrors = hydrodynRuntimeErrors(payload);
  const referenceWarnings = hydrodynReferenceWarnings(payload);
  const counts = [
    `格式 ${state.meta?.hydroTables?.format || 'unknown'}`,
    `运行写出 ${payload.target_format || 'auto_v4_runtime'}`,
    `joints ${(t.joints || []).length}`,
    `props ${(t.prop_sets_cyl || []).length}`,
    `members ${(t.members || []).length}`,
    `member Cd ${(t.member_coeffs_cyl || []).length}`
  ];
  const messages = [...baseWarnings, ...referenceWarnings, ...runtimeErrors];
  $('hydroStatus').innerHTML = `${custom ? '当前 case 已启用表格覆盖。' : '当前显示模板表格，编辑后才写入当前 case。'}<br>${counts.join(' | ')}${messages.length ? `<br><span class="danger-text">${messages.map(escapeHtml).join('<br>')}</span>` : ''}`;

  renderHydroTable('hydroMembers', 'members');
  renderHydroTable('hydroJoints', 'joints');
  renderHydroTable('hydroProps', 'prop_sets_cyl');
  renderHydroTable('hydroMemberCoeffs', 'member_coeffs_cyl');
  renderHydroTable('hydroSimple', 'simple_cyl', { objectTable: true });
  renderHydroTable('hydroAxial', 'axial');
}

function renderSetRows() {
  const wrap = $('setRows');
  wrap.innerHTML = '';
  for (const row of setEntries()) {
    const div = document.createElement('div');
    div.className = 'row';
    div.innerHTML = `<label><span>文件</span><input value="${escapeHtml(row.file)}"></label><label><span>Key</span><input value="${escapeHtml(row.key)}"></label><label><span>值</span><input value="${escapeHtml(String(row.value))}"></label><button class="remove">删</button>`;
    const [fileInput, keyInput, valueInput] = div.querySelectorAll('input');
    const sync = () => {
      removeDeep(row.file, row.key);
      row.file = fileInput.value.trim();
      row.key = keyInput.value.trim();
      row.value = parseValue(valueInput.value.trim());
      if (row.file && row.key) setDeep(row.file, row.key, row.value);
      renderJson();
    };
    fileInput.onchange = keyInput.onchange = valueInput.onchange = sync;
    div.querySelector('button').onclick = () => { removeDeep(row.file, row.key); renderAll(); };
    wrap.appendChild(div);
  }
}

function renderMatrixRows() {
  const wrap = $('matrixRows');
  wrap.innerHTML = '';
  normalizedMatrixEdits();

  for (const [block, label] of MATRIX_BLOCKS) {
    const panel = document.createElement('div');
    panel.className = 'matrix-panel';

    const count = normalizedMatrixEdits().filter(edit => edit.block === block).length;
    const title = document.createElement('div');
    title.className = 'matrix-title';
    title.innerHTML = `<strong>${label}</strong><span>${block} | FOCAL_C4_HydroDyn.dat | ${count} 个覆盖值</span>`;
    panel.appendChild(title);

    const table = document.createElement('table');
    table.className = 'matrix-table';

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const corner = document.createElement('th');
    corner.textContent = 'DOF';
    headRow.appendChild(corner);
    DOFS.forEach((dof, index) => {
      const th = document.createElement('th');
      th.innerHTML = `${index + 1}<br>${dof}`;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (let i = 1; i <= 6; i += 1) {
      const tr = document.createElement('tr');
      const rowHead = document.createElement('th');
      rowHead.innerHTML = `${i}<br>${DOFS[i - 1]}`;
      tr.appendChild(rowHead);
      for (let j = 1; j <= 6; j += 1) {
        const td = document.createElement('td');
        const input = document.createElement('input');
        input.type = 'text';
        input.inputMode = 'decimal';
        input.value = formatMatrixValue(matrixValue(block, i, j));
        input.dataset.block = block;
        input.dataset.i = String(i);
        input.dataset.j = String(j);
        input.title = `${block}[${i},${j}] 模板值 ${formatMatrixValue(baselineMatrixValue(block, i, j))}`;
        input.classList.toggle('edited', hasMatrixEdit(block, i, j));
        input.onchange = () => setMatrixValue(block, i, j, input.value);
        td.appendChild(input);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    panel.appendChild(table);
    wrap.appendChild(panel);
  }
}

function renderCatalog() {
  const wrap = $('catalog');
  const q = ($('catalogSearch').value || '').toLowerCase();
  wrap.innerHTML = '';
  for (const [file, rows] of Object.entries(state.meta.templateKeys)) {
    const filtered = rows.filter(r => !q || file.toLowerCase().includes(q) || r.key.toLowerCase().includes(q));
    if (!filtered.length) continue;
    const box = document.createElement('div');
    box.className = 'catalog-file';
    box.innerHTML = `<h3>${file}</h3>`;
    for (const row of filtered) {
      const line = document.createElement('div');
      line.className = 'catalog-row';
      line.innerHTML = `<span>${row.line}</span><span>${row.key}</span><span>${escapeHtml(row.value)}</span><button>加入</button>`;
      line.querySelector('button').onclick = () => {
        setDeep(file, row.key, parseValue(row.value.replace(/^"|"$/g, '')));
        toast(`已加入 ${row.key}`);
        renderAll();
      };
      box.appendChild(line);
    }
    wrap.appendChild(box);
  }
}

function renderJson() {
  $('jsonEditor').value = JSON.stringify(state.scenario, null, 2);
}

function parseValue(value) {
  if (/^(true|false)$/i.test(value)) return /^true$/i.test(value);
  if (/^-?\d+(\.\d+)?(e[+-]?\d+)?$/i.test(value)) return Number(value);
  return value;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function collectForm() {
  state.scenarioFile = $('scenarioFile').value.trim() || 'ui_scenario.json';
  state.scenario.name = $('scenarioName').value.trim() || 'ui_scenario';
  state.scenario.description = $('scenarioDescription').value.trim();
  state.scenario.model_id = state.selectedModelId || state.meta?.selectedModelId;
  state.scenario.runtime_id = state.selectedRuntimeId || state.meta?.selectedRuntimeId;
  const c = currentCase();
  c.name = $('caseName').value.trim() || c.name;
  c.notes = $('caseNotes').value.trim();
  normalizedMatrixEdits(true);
  repairScenarioHydroReferences(state.scenario);
}

function cleanupScenarioForSave(data) {
  repairScenarioHydroReferences(data);
  for (const c of data.cases || []) {
    if (Array.isArray(c.matrix_edits) && c.matrix_edits.length === 0) delete c.matrix_edits;
  }
  return data;
}

async function loadMeta() {
  const params = new URLSearchParams();
  if (state.selectedModelId) params.set('model', state.selectedModelId);
  if (state.selectedRuntimeId) params.set('runtime', state.selectedRuntimeId);
  const suffix = params.toString() ? `?${params}` : '';
  state.meta = await api(`/api/meta${suffix}`);
  state.selectedModelId = state.meta.selectedModelId || '';
  state.selectedRuntimeId = state.meta.selectedRuntimeId || '';
  localStorage.setItem('openfastGui.modelId', state.selectedModelId);
  localStorage.setItem('openfastGui.runtimeId', state.selectedRuntimeId);
  const list = await api('/api/scenarios');
  state.scenarioList = list.scenarios;
}

async function loadScenario(file) {
  const data = await api(`/api/scenario?file=${encodeURIComponent(file)}`);
  state.scenarioFile = data.file;
  state.scenario = data.data;
  if (state.scenario.model_id) state.selectedModelId = state.scenario.model_id;
  if (state.scenario.runtime_id) state.selectedRuntimeId = state.scenario.runtime_id;
  await loadMeta();
  state.selectedCase = 0;
  renderAll();
  toast(`已载入 ${file}`);
}

async function saveScenario() {
  collectForm();
  let data = state.scenario;
  if ($('jsonEditor').value.trim()) {
    try { data = JSON.parse($('jsonEditor').value); state.scenario = data; }
    catch (err) { throw new Error(`JSON 格式错误: ${err.message}`); }
  }
  cleanupScenarioForSave(state.scenario);
  const saved = await api('/api/scenario', {
    method: 'POST',
    body: JSON.stringify({ file: state.scenarioFile, data: state.scenario })
  });
  state.scenarioFile = saved.file;
  await loadMeta();
  renderAll();
  toast(`已保存 ${saved.file}`);
}

async function startJob(generateOnly) {
  if (state.jobRunning) throw new Error('A job is already running. Wait for it to finish first.');
  collectForm();
  const hydroErrors = hydrodynRuntimeErrors();
  if (hydroErrors.length) throw new Error(hydroErrors.join('；'));
  await saveScenario();
  const data = await api('/api/jobs', {
    method: 'POST',
    body: JSON.stringify({
      file: state.scenarioFile,
      scenario: state.scenario,
      options: {
        generateOnly,
        overwrite: $('overwriteRun').checked,
        continueOnFail: $('continueOnFail').checked,
        modelId: state.selectedModelId,
        runtimeId: state.selectedRuntimeId
      }
    })
  });
  state.currentJob = data.jobId;
  state.jobRunning = true;
  setJobButtons(false);
  setActiveTab('runlog');
  pollJob();
}

function setJobButtons(enabled) {
  $('generateBtn').disabled = !enabled;
  $('runBtn').disabled = !enabled;
}

async function pollJob() {
  if (!state.currentJob) return;
  const job = await api(`/api/jobs/${state.currentJob}`);
  const elapsed = job.elapsed_s !== undefined ? ` ${Math.round(job.elapsed_s)}s` : '';
  $('jobStatus').textContent = `${job.status}${elapsed} ${job.returncode !== undefined ? `(${job.returncode})` : ''}`;
  $('runLog').textContent = job.output || (['queued', 'running'].includes(job.status) ? '等待 OpenFAST 输出...' : '');
  $('runLog').scrollTop = $('runLog').scrollHeight;
  if (['queued', 'running'].includes(job.status)) {
    state.pollTimer = setTimeout(pollJob, 1200);
  } else {
    toast(job.status === 'done' ? '任务完成' : '任务失败');
    state.jobRunning = false;
    setJobButtons(true);
    await loadMeta();
  }
}

function applyPreset() {
  const preset = state.meta.modulePresets.find(p => p.id === $('presetSelect').value);
  if (!preset) return;
  const files = activeFiles();
  const c = currentCase();
  c.set = structuredClone(preset.set || {});
  setDeep(files.fst, 'TMax', Number($('quickTMax').value || 120));
  if (preset.id.includes('wind')) {
    setDeep(files.inflow, 'HWindSpeed', Number($('quickWind').value || 12.8));
  }
  if (preset.id.includes('wave')) {
    setDeep(files.sea, 'WaveMod', Number($('quickWaveMod').value || 1));
    setDeep(files.sea, 'WaveHs', Number($('quickHs').value || 2));
    setDeep(files.sea, 'WaveTp', Number($('quickTp').value || 10));
    setDeep(files.sea, 'WaveDir', Number($('quickWaveDir').value || 0));
  }
  renderAll();
  toast(`已应用 ${preset.name}`);
}

function setActiveTab(name) {
  document.querySelectorAll('.tab').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
  document.querySelectorAll('.tab-page').forEach(page => page.classList.toggle('active', page.id === `tab-${name}`));
}

function bindEvents() {
  document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => setActiveTab(btn.dataset.tab));
  $('modelSelect').onchange = async () => {
    collectForm();
    state.selectedModelId = $('modelSelect').value;
    state.selectedRuntimeId = '';
    localStorage.setItem('openfastGui.modelId', state.selectedModelId);
    localStorage.removeItem('openfastGui.runtimeId');
    await loadMeta();
    delete currentCase().hydrodyn_tables;
    renderAll();
  };
  $('runtimeSelect').onchange = async () => {
    collectForm();
    state.selectedRuntimeId = $('runtimeSelect').value;
    localStorage.setItem('openfastGui.runtimeId', state.selectedRuntimeId);
    await loadMeta();
    delete currentCase().hydrodyn_tables;
    renderAll();
  };
  $('presetSelect').onchange = updatePresetDescription;
  $('applyPresetBtn').onclick = applyPreset;
  $('addCaseBtn').onclick = () => { collectForm(); state.scenario.cases.push(emptyCase()); state.selectedCase = state.scenario.cases.length - 1; renderAll(); };
  $('newScenarioBtn').onclick = () => { state.scenarioFile = 'ui_scenario.json'; state.scenario = { name: 'ui_scenario', description: 'Created from visual UI', model_id: state.selectedModelId, runtime_id: state.selectedRuntimeId, cases: [emptyCase()] }; state.selectedCase = 0; renderAll(); };
  $('addSetBtn').onclick = () => { setDeep(activeFiles().fst, 'TMax', 120); renderAll(); };
  $('addMatrixBtn').onclick = () => { delete currentCase().matrix_edits; renderAll(); toast('已清空矩阵修改'); };
  $('addMorisonBtn').onclick = addDefaultMorisonMember;
  $('resetHydroTablesBtn').onclick = () => { delete currentCase().hydrodyn_tables; renderAll(); toast('已恢复模板 HydroDyn 表格'); };
  $('formatJsonBtn').onclick = () => { collectForm(); renderJson(); };
  $('saveBtn').onclick = () => saveScenario().catch(err => toast(err.message));
  $('generateBtn').onclick = () => startJob(true).catch(err => toast(err.message));
  $('runBtn').onclick = () => startJob(false).catch(err => toast(err.message));
  $('refreshBtn').onclick = async () => { await loadMeta(); renderAll(); };
  $('catalogSearch').oninput = renderCatalog;
  $('caseName').onchange = () => { currentCase().name = $('caseName').value.trim(); renderAll(); };
  $('caseNotes').onchange = () => { currentCase().notes = $('caseNotes').value.trim(); renderJson(); };
}

async function init() {
  bindEvents();
  await loadMeta();
  if (state.scenarioList?.length) {
    const first = state.scenarioList.find(s => s.file === 'steady_wind.json') || state.scenarioList[0];
    await loadScenario(first.file);
  } else {
    normalizeScenario();
    renderAll();
  }
}

init().catch(err => {
  console.error(err);
  toast(err.message);
});
