const state = {
  meta: null,
  scenarioFile: 'ui_scenario.json',
  scenario: { name: 'ui_scenario', description: 'Created from visual UI', cases: [] },
  selectedCase: 0,
  selectedModelId: localStorage.getItem('openfastGui.modelId') || '',
  selectedRuntimeId: localStorage.getItem('openfastGui.runtimeId') || '',
  currentJob: null,
  pollTimer: null,
  jobRunning: false,
  plotComparison: localStorage.getItem('openfastGui.plotComparison'),
  parallelWorkers: Number(localStorage.getItem('openfastGui.parallelWorkers') || 1),
  activeTab: localStorage.getItem('openfastGui.activeTab') || 'compose',
  scenarioQuery: '',
  selectedModelFile: '',
  selectedOutlistFile: '',
  resultsCatalog: null,
  selectedResultFiles: [],
  selectedResultChannels: [],
  resultData: null,
  resultView: 'time',
  resultLoading: false,
  resultError: '',
  resultScenarioFilter: 'all',
  jsonDirty: false
};

const $ = (id) => document.getElementById(id);
const DOFS = ['Surge', 'Sway', 'Heave', 'Roll', 'Pitch', 'Yaw'];
const MATRIX_BLOCKS = [
  ['CLin', 'AddCLin 线性刚度'],
  ['BLin', 'AddBLin 线性阻尼'],
  ['BQuad', 'AddBQuad 二次阻尼/拖曳']
];
const DLC11_ROWS = [
  { wind: 4, hs: 1.10, tp: 8.52, gamma: 1.00 },
  { wind: 6, hs: 1.18, tp: 8.31, gamma: 1.00 },
  { wind: 8, hs: 1.32, tp: 8.01, gamma: 1.00 },
  { wind: 10, hs: 1.54, tp: 7.65, gamma: 1.00 },
  { wind: 12, hs: 1.84, tp: 7.44, gamma: 1.00 },
  { wind: 14, hs: 2.19, tp: 7.46, gamma: 1.00 },
  { wind: 16, hs: 2.60, tp: 7.64, gamma: 1.35 },
  { wind: 18, hs: 3.06, tp: 8.05, gamma: 1.59 },
  { wind: 20, hs: 3.62, tp: 8.52, gamma: 1.82 },
  { wind: 22, hs: 4.03, tp: 8.99, gamma: 1.82 },
  { wind: 24, hs: 4.52, tp: 9.45, gamma: 1.89 }
];
const FOCAL_TABLE24_ROWS = [
  {
    id: 'E11_E15', waveStart: 11, waveEnd: 15, seaState: 'Operational / DLC 1.2',
    hs: 3.1, tp: 8.96, gamma: 1.80, duration: 9294.4,
    referenceUrl: '/assets/irregular_wave/focal_e11_e15_calibration.png'
  },
  {
    id: 'E21_E25', waveStart: 21, waveEnd: 25, seaState: '1-year extreme / DLC 1.6',
    hs: 8.1, tp: 12.8, gamma: 2.75, duration: 9754.4,
    referenceUrl: '/assets/irregular_wave/focal_e21_e25_calibration.png'
  }
];
const FOCAL_MODE_FREQUENCIES = {
  Surge: 1 / 80.79,
  Pitch: 1 / 30.79,
  Tower: 0.458
};
const RESULT_COMMON_CHANNELS = [
  ['Wave1Elev', 'WaveElev', 'WaveElev1'],
  ['PtfmSurge', 'Surge'],
  ['PtfmHeave', 'Heave'],
  ['PtfmPitch', 'Pitch'],
  ['RotSpeed', 'GenSpeed'],
  ['GenPwr', 'GenTq'],
  ['FairTen1', 'FAIRTEN1', 'FairHTen1']
];
const RESULT_COLORS = ['#14756e', '#b34a3c', '#2f6f9f', '#9a6a18', '#5b6f3a', '#8b5a83', '#4d5967', '#16839a'];
const DLC_PARAM_HELP = [
  ['WindType', 'InflowWind', '1 是稳态风，3 是 TurbSim .bts 全场湍流风。'],
  ['HWindSpeed', 'InflowWind', '稳态风速；学习模式直接用它控制入流。'],
  ['FileName_BTS', 'InflowWind', '正式 NTM 模式使用的 .bts 风场文件名。'],
  ['WaveMod', 'SeaState', '2 表示不规则波 JONSWAP/PM。'],
  ['WaveHs', 'SeaState', '有效波高 Hs，对应论文 Table 12。'],
  ['WaveTp', 'SeaState', '谱峰周期 Tp，对应论文 Table 12。'],
  ['WavePkShp', 'SeaState', 'JONSWAP Gamma；Table 12 中的 Gamma Shape Factor。'],
  ['WaveSeed(1)', 'SeaState', '波浪随机种子；多 seed 时逐个改变。'],
  ['TMax', '主 .fst', 'OpenFAST 仿真总时长。'],
  ['WaveTMax', 'SeaState', '波浪时程长度，应大于 TMax。'],
  ['CompInflow/Aero/Servo', '主 .fst', '入流、气动和控制模块开关。'],
  ['CompSeaSt/Hydro/Mooring', '主 .fst', '海况、水动力和系泊模块开关。']
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

function setQuickValue(id, value, fallback) {
  const el = $(id);
  el.value = value ?? fallback;
  el.dataset.dirty = '0';
}

function renderQuickInputs() {
  const files = activeFiles();
  const c = currentCase();
  const fst = c.set?.[files.fst] || {};
  const inflow = c.set?.[files.inflow] || {};
  const sea = c.set?.[files.sea] || {};
  setQuickValue('quickTMax', fst.TMax, 120);
  setQuickValue('quickWind', inflow.HWindSpeed, 12.8);
  setQuickValue('quickWaveMod', sea.WaveMod, 0);
  setQuickValue('quickHs', sea.WaveHs, 2);
  setQuickValue('quickTp', sea.WaveTp, 10);
  setQuickValue('quickWavePkShp', sea.WavePkShp, 'DEFAULT');
  setQuickValue('quickWaveDir', sea.WaveDir, 0);
}

function syncQuickInputsToCase() {
  const files = activeFiles();
  const c = currentCase();
  const hasInflow = Boolean(c.set?.[files.inflow]);
  const hasSea = Boolean(c.set?.[files.sea]);
  const windDirty = $('quickWind').dataset.dirty === '1';
  const waveDirty = ['quickWaveMod', 'quickHs', 'quickTp', 'quickWavePkShp', 'quickWaveDir'].some(id => $(id).dataset.dirty === '1');
  setDeep(files.fst, 'TMax', Number($('quickTMax').value || 120));
  if (hasInflow || windDirty) setDeep(files.inflow, 'HWindSpeed', Number($('quickWind').value || 0));
  if (hasSea || waveDirty) {
    setDeep(files.sea, 'WaveMod', Number($('quickWaveMod').value || 0));
    setDeep(files.sea, 'WaveHs', Number($('quickHs').value || 0));
    setDeep(files.sea, 'WaveTp', Number($('quickTp').value || 0));
    setDeep(files.sea, 'WavePkShp', parseValue($('quickWavePkShp').value.trim() || 'DEFAULT'));
    setDeep(files.sea, 'WaveDir', Number($('quickWaveDir').value || 0));
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
  renderQuickInputs();
  renderRunOptions();
  renderReferenceFigures();
  renderDlcLearning();
  renderFocalWaveReproduction();
  renderModuleSwitches();
  renderAdvancedRows();
  renderModelStructure();
  renderOutlistEditor();
  renderHydroTables();
  renderCatalog();
  renderResultsWorkspace();
  renderJson();
  setActiveTab(state.activeTab, false);
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

function scenarioHasComparisonMetadata() {
  return Boolean(
    state.scenario.reference_figures?.length ||
    (state.scenario.cases || []).some(c => c.comparison || c.experiment_id || c.reference_figures?.length)
  );
}

function plotComparisonEnabled() {
  if (state.plotComparison === null) return scenarioHasComparisonMetadata();
  return state.plotComparison === 'true';
}

function renderRunOptions() {
  const plot = $('plotComparison');
  if (plot) plot.checked = plotComparisonEnabled();
  const workers = $('parallelWorkers');
  if (workers) workers.value = String(Math.min(4, Math.max(1, state.parallelWorkers || 1)));
}

function resultScenarioSlug(value) {
  return String(value || '').trim().replace(/[^0-9A-Za-z_.-]+/g, '_').replace(/^_+|_+$/g, '') || 'scenario';
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatResultNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  const magnitude = Math.abs(number);
  if (magnitude !== 0 && (magnitude >= 1e5 || magnitude < 1e-3)) return number.toExponential(4);
  return Number(number.toPrecision(6)).toString();
}

function resultFiles() {
  return state.resultsCatalog?.files || [];
}

function selectedResultRows() {
  const selected = new Set(state.selectedResultFiles);
  return resultFiles().filter(row => selected.has(row.id));
}

function filteredResultRows() {
  const query = ($('resultFileSearch')?.value || '').trim().toLowerCase();
  return resultFiles().filter(row => {
    if (state.resultScenarioFilter !== 'all' && row.scenario !== state.resultScenarioFilter) return false;
    return !query || [row.scenario, row.case, row.file, row.label].some(value => String(value || '').toLowerCase().includes(query));
  });
}

function availableResultChannels() {
  const rows = selectedResultRows();
  const byName = new Map();
  for (const row of rows) {
    for (const channel of row.channels || []) {
      if (!channel.name || channel.index === 0 || channel.name === row.independent?.name) continue;
      const key = channel.name.toLowerCase();
      if (!byName.has(key)) byName.set(key, { name: channel.name, units: new Set(), files: 0 });
      const item = byName.get(key);
      if (channel.unit) item.units.add(channel.unit);
      item.files += 1;
    }
  }
  return [...byName.values()]
    .map(row => ({ name: row.name, unit: [...row.units].join(' / '), files: row.files }))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

function invalidateResultAnalysis() {
  state.resultData = null;
  state.resultError = '';
}

function selectCommonResultChannels(render = true) {
  const available = availableResultChannels();
  const lookup = new Map(available.map(row => [row.name.toLowerCase(), row.name]));
  const selected = [];
  for (const aliases of RESULT_COMMON_CHANNELS) {
    const found = aliases.map(alias => lookup.get(alias.toLowerCase())).find(Boolean);
    if (found && !selected.includes(found)) selected.push(found);
    if (selected.length >= 8) break;
  }
  if (!selected.length) selected.push(...available.slice(0, 4).map(row => row.name));
  state.selectedResultChannels = selected;
  invalidateResultAnalysis();
  if (render) renderResultsWorkspace();
}

function selectPrimaryResults() {
  const candidates = filteredResultRows().filter(row => row.primary && !row.error).slice(0, 6);
  const fallback = filteredResultRows().filter(row => !row.error).slice(0, 1);
  state.selectedResultFiles = (candidates.length ? candidates : fallback).map(row => row.id);
  selectCommonResultChannels(false);
  renderResultsWorkspace();
}

async function loadResultsCatalog({ preserve = true, preferScenario = false } = {}) {
  try {
    const payload = await api('/api/results');
    state.resultsCatalog = payload;
    const valid = new Set(resultFiles().map(row => row.id));
    state.selectedResultFiles = preserve ? state.selectedResultFiles.filter(id => valid.has(id)) : [];
    const preferredScenario = resultScenarioSlug(state.scenario.name);
    if (preferScenario && resultFiles().some(row => row.scenario === preferredScenario)) {
      state.resultScenarioFilter = preferredScenario;
    } else if (!new Set(resultFiles().map(row => row.scenario)).has(state.resultScenarioFilter)) {
      state.resultScenarioFilter = 'all';
    }
    if (!state.selectedResultFiles.length) selectPrimaryResults();
    else {
      const available = new Set(availableResultChannels().map(row => row.name));
      state.selectedResultChannels = state.selectedResultChannels.filter(name => available.has(name));
      if (!state.selectedResultChannels.length) selectCommonResultChannels(false);
    }
    state.resultError = '';
  } catch (error) {
    state.resultsCatalog = { summary: { scenarios: 0, cases: 0, files: 0 }, files: [] };
    state.resultError = error.message;
  }
  renderResultsWorkspace();
}

function renderResultFileList() {
  const wrap = $('resultFileList');
  if (!wrap) return;
  const rows = filteredResultRows();
  const selected = new Set(state.selectedResultFiles);
  $('resultFileCount').textContent = `${selected.size} / 6 已选 · ${rows.length} 可见`;
  wrap.innerHTML = '';
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty-state">没有匹配的结果文件</div>';
    return;
  }
  for (const row of rows) {
    const label = document.createElement('label');
    label.className = `result-file-item ${selected.has(row.id) ? 'selected' : ''} ${row.error ? 'invalid' : ''}`;
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selected.has(row.id);
    checkbox.disabled = Boolean(row.error);
    checkbox.onchange = () => {
      if (checkbox.checked && state.selectedResultFiles.length >= 6) {
        checkbox.checked = false;
        toast('最多同时比较 6 个结果文件');
        return;
      }
      if (checkbox.checked) state.selectedResultFiles.push(row.id);
      else state.selectedResultFiles = state.selectedResultFiles.filter(id => id !== row.id);
      const available = new Set(availableResultChannels().map(channel => channel.name));
      state.selectedResultChannels = state.selectedResultChannels.filter(name => available.has(name));
      if (!state.selectedResultChannels.length) selectCommonResultChannels(false);
      invalidateResultAnalysis();
      renderResultsWorkspace();
    };
    const copy = document.createElement('span');
    copy.className = 'result-file-copy';
    const duration = Number.isFinite(Number(row.timeEnd)) && Number.isFinite(Number(row.timeStart)) ? `${formatResultNumber(row.timeEnd - row.timeStart)} s` : 'duration —';
    copy.innerHTML = `<strong>${escapeHtml(row.case)} / ${escapeHtml(row.file)}</strong><span>${escapeHtml(row.scenario)} · ${row.format || 'unknown'} · ${formatBytes(row.size)}</span><small>${row.channelCount || 0} channels · ${duration}${row.primary ? ' · primary' : ''}${row.error ? ` · ${escapeHtml(row.error)}` : ''}</small>`;
    label.append(checkbox, copy);
    wrap.appendChild(label);
  }
}

function renderResultChannelList() {
  const wrap = $('resultChannelList');
  if (!wrap) return;
  const query = ($('resultChannelSearch')?.value || '').trim().toLowerCase();
  const rows = availableResultChannels().filter(row => !query || `${row.name} ${row.unit}`.toLowerCase().includes(query));
  const selected = new Set(state.selectedResultChannels);
  $('resultChannelCount').textContent = `${selected.size} / 8 已选 · ${availableResultChannels().length} 可用`;
  wrap.innerHTML = '';
  if (!selectedResultRows().length) {
    wrap.innerHTML = '<div class="empty-state">先选择结果文件</div>';
    return;
  }
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty-state">没有匹配的通道</div>';
    return;
  }
  for (const row of rows) {
    const label = document.createElement('label');
    label.className = `result-channel-item ${selected.has(row.name) ? 'selected' : ''}`;
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selected.has(row.name);
    checkbox.onchange = () => {
      if (checkbox.checked && state.selectedResultChannels.length >= 8) {
        checkbox.checked = false;
        toast('最多同时分析 8 个通道');
        return;
      }
      if (checkbox.checked) state.selectedResultChannels.push(row.name);
      else state.selectedResultChannels = state.selectedResultChannels.filter(name => name !== row.name);
      invalidateResultAnalysis();
      renderResultsWorkspace();
    };
    const name = document.createElement('span');
    name.innerHTML = `<strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.unit || '—')} · ${row.files}/${selectedResultRows().length} files</small>`;
    label.append(checkbox, name);
    wrap.appendChild(label);
  }
}

function renderResultsWorkspace() {
  if (!$('resultCatalogStatus')) return;
  const summary = state.resultsCatalog?.summary || { scenarios: 0, cases: 0, files: 0 };
  $('resultCatalogStatus').textContent = `${summary.scenarios || 0} scenarios · ${summary.cases || 0} cases · ${summary.files || 0} files`;
  const scenarios = [...new Set(resultFiles().map(row => row.scenario))].sort((a, b) => a.localeCompare(b));
  const scenarioSelect = $('resultScenarioFilter');
  scenarioSelect.innerHTML = ['<option value="all">全部场景</option>', ...scenarios.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)].join('');
  scenarioSelect.value = scenarios.includes(state.resultScenarioFilter) ? state.resultScenarioFilter : 'all';
  renderResultFileList();
  renderResultChannelList();
  renderResultAnalysis();
}

async function analyzeSelectedResults() {
  if (!state.selectedResultFiles.length) {
    state.resultError = '至少选择一个结果文件。';
    renderResultAnalysis();
    return;
  }
  if (!state.selectedResultChannels.length) {
    state.resultError = '至少选择一个分析通道。';
    renderResultAnalysis();
    return;
  }
  const startText = $('resultStart').value.trim();
  const endText = $('resultEnd').value.trim();
  state.resultLoading = true;
  state.resultError = '';
  renderResultAnalysis();
  try {
    state.resultData = await api('/api/results/analyze', {
      method: 'POST',
      body: JSON.stringify({
        files: state.selectedResultFiles,
        channels: state.selectedResultChannels,
        start: startText === '' ? null : Number(startText),
        end: endText === '' ? null : Number(endText),
        maxPoints: Math.min(8000, Math.max(200, Number($('resultMaxPoints').value) || 4000)),
        includePsd: true
      })
    });
  } catch (error) {
    state.resultData = null;
    state.resultError = error.message;
  } finally {
    state.resultLoading = false;
    renderResultAnalysis();
  }
}

function resultSeriesGroups(mode) {
  const groups = new Map();
  for (const result of state.resultData?.cases || []) {
    if (mode === 'psd') {
      for (const row of result.psd || []) {
        const unit = row.unit || 'PSD';
        if (!groups.has(unit)) groups.set(unit, []);
        groups.get(unit).push({ label: `${result.id} · ${row.name}`, x: row.frequency, y: row.values, unit });
      }
    } else {
      const x = result.independent?.values || [];
      for (const row of result.series || []) {
        const unit = row.unit || '—';
        if (!groups.has(unit)) groups.set(unit, []);
        groups.get(unit).push({ label: `${result.id} · ${row.name}`, x, y: row.values, unit, xUnit: result.independent?.unit || '' });
      }
    }
  }
  return groups;
}

function resultColor(label) {
  let hash = 0;
  for (const character of label) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return RESULT_COLORS[Math.abs(hash) % RESULT_COLORS.length];
}

function axisLabel(value) {
  const number = Number(value);
  const magnitude = Math.abs(number);
  if (magnitude !== 0 && (magnitude >= 1e4 || magnitude < 1e-2)) return number.toExponential(2);
  return Number(number.toPrecision(4)).toString();
}

function drawResultCanvas(canvas, entries, mode, unit) {
  const width = Math.max(620, Math.round(canvas.getBoundingClientRect().width || 900));
  const height = 330;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const context = canvas.getContext('2d');
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, width, height);
  const margin = { left: 76, right: 22, top: 20, bottom: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const points = [];
  for (const entry of entries) {
    for (let index = 0; index < Math.min(entry.x.length, entry.y.length); index += 1) {
      const x = Number(entry.x[index]);
      const rawY = Number(entry.y[index]);
      const y = mode === 'psd' ? Math.log10(rawY) : rawY;
      if (Number.isFinite(x) && Number.isFinite(y)) points.push([x, y]);
    }
  }
  if (!points.length) return;
  let xMin = Infinity;
  let xMax = -Infinity;
  let yMin = Infinity;
  let yMax = -Infinity;
  for (const [x, y] of points) {
    xMin = Math.min(xMin, x);
    xMax = Math.max(xMax, x);
    yMin = Math.min(yMin, y);
    yMax = Math.max(yMax, y);
  }
  if (xMin === xMax) { xMin -= 0.5; xMax += 0.5; }
  if (yMin === yMax) { yMin -= 0.5; yMax += 0.5; }
  const yPad = (yMax - yMin) * 0.06;
  yMin -= yPad;
  yMax += yPad;
  const px = value => margin.left + (value - xMin) / (xMax - xMin) * plotWidth;
  const py = value => margin.top + plotHeight - (value - yMin) / (yMax - yMin) * plotHeight;

  context.strokeStyle = '#dfe7e5';
  context.lineWidth = 1;
  context.fillStyle = '#64716e';
  context.font = '10px Cascadia Mono, Consolas, monospace';
  for (let tick = 0; tick <= 5; tick += 1) {
    const xValue = xMin + (xMax - xMin) * tick / 5;
    const x = px(xValue);
    context.beginPath(); context.moveTo(x, margin.top); context.lineTo(x, margin.top + plotHeight); context.stroke();
    context.textAlign = 'center'; context.fillText(axisLabel(xValue), x, height - 25);
    const yValue = yMin + (yMax - yMin) * tick / 5;
    const y = py(yValue);
    context.beginPath(); context.moveTo(margin.left, y); context.lineTo(margin.left + plotWidth, y); context.stroke();
    context.textAlign = 'right'; context.fillText(mode === 'psd' ? `10^${axisLabel(yValue)}` : axisLabel(yValue), margin.left - 8, y + 3);
  }
  context.strokeStyle = '#80908c';
  context.beginPath(); context.moveTo(margin.left, margin.top); context.lineTo(margin.left, margin.top + plotHeight); context.lineTo(margin.left + plotWidth, margin.top + plotHeight); context.stroke();

  for (const entry of entries) {
    context.strokeStyle = resultColor(entry.label);
    context.lineWidth = 1.35;
    context.beginPath();
    let started = false;
    for (let index = 0; index < Math.min(entry.x.length, entry.y.length); index += 1) {
      const xValue = Number(entry.x[index]);
      const rawY = Number(entry.y[index]);
      const yValue = mode === 'psd' ? Math.log10(rawY) : rawY;
      if (!Number.isFinite(xValue) || !Number.isFinite(yValue)) { started = false; continue; }
      const x = px(xValue);
      const y = py(yValue);
      if (!started) { context.moveTo(x, y); started = true; }
      else context.lineTo(x, y);
    }
    context.stroke();
  }

  context.fillStyle = '#47534f';
  context.textAlign = 'center';
  context.font = '11px Segoe UI, Arial, sans-serif';
  context.fillText(mode === 'psd' ? 'Frequency (Hz)' : `${state.resultData?.cases?.[0]?.independent?.name || 'Time'} (${entries[0]?.xUnit || 's'})`, margin.left + plotWidth / 2, height - 6);
  context.save();
  context.translate(14, margin.top + plotHeight / 2);
  context.rotate(-Math.PI / 2);
  context.fillText(mode === 'psd' ? `PSD (${unit}, log scale)` : unit, 0, 0);
  context.restore();
}

function renderResultCharts() {
  const wrap = $('resultCharts');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!state.resultData) {
    wrap.innerHTML = '<div class="empty-state">选择结果文件和通道后加载分析</div>';
    return;
  }
  const groups = resultSeriesGroups(state.resultView);
  if (!groups.size) {
    wrap.innerHTML = `<div class="empty-state">${state.resultView === 'psd' ? '所选数据不足以计算 PSD' : '没有可绘制的数据'}</div>`;
    return;
  }
  for (const [unit, entries] of groups) {
    const figure = document.createElement('figure');
    figure.className = 'result-chart-block';
    const caption = document.createElement('figcaption');
    caption.innerHTML = `<strong>${state.resultView === 'psd' ? '功率谱密度' : '时程'} · ${escapeHtml(unit)}</strong><span>${entries.length} traces</span>`;
    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-label', `${state.resultView} ${unit} chart`);
    const legend = document.createElement('div');
    legend.className = 'result-chart-legend';
    legend.innerHTML = entries.map(entry => `<span><i style="background:${resultColor(entry.label)}"></i>${escapeHtml(entry.label)}</span>`).join('');
    figure.append(caption, canvas, legend);
    wrap.appendChild(figure);
    requestAnimationFrame(() => drawResultCanvas(canvas, entries, state.resultView, unit));
  }
}

function renderResultStats() {
  const body = $('resultStatsBody');
  if (!body) return;
  body.innerHTML = '';
  if (!state.resultData) {
    body.innerHTML = '<tr><td colspan="11" class="empty-cell">尚未加载分析</td></tr>';
    return;
  }
  for (const result of state.resultData.cases || []) {
    for (const row of result.statistics || []) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${escapeHtml(result.id)}</td><td><strong>${escapeHtml(row.name)}</strong></td><td>${escapeHtml(row.unit || '—')}</td><td>${formatResultNumber(row.min)}</td><td>${formatResultNumber(row.max)}</td><td>${formatResultNumber(row.mean)}</td><td>${formatResultNumber(row.std)}</td><td>${formatResultNumber(row.rms)}</td><td>${formatResultNumber(row.absMax)}</td><td>${formatResultNumber(row.range)}</td><td>${row.count ?? 0}</td>`;
      body.appendChild(tr);
    }
  }
  if (!body.children.length) body.innerHTML = '<tr><td colspan="11" class="empty-cell">没有统计数据</td></tr>';
}

function renderResultAnalysis() {
  if (!$('resultAnalysisPanel') && !$('resultCharts')) return;
  const error = $('resultError');
  error.hidden = !state.resultError;
  error.textContent = state.resultError || '';
  $('resultWarnings').innerHTML = (state.resultData?.warnings || []).map(value => `<div>${escapeHtml(value)}</div>`).join('');
  $('resultLoading').hidden = !state.resultLoading;
  $('resultAnalyzeBtn').disabled = state.resultLoading;
  $('resultViewTime').classList.toggle('active', state.resultView === 'time');
  $('resultViewPsd').classList.toggle('active', state.resultView === 'psd');
  for (const id of ['resultExportCsvBtn', 'resultExportPngBtn', 'resultPrintBtn']) $(id).disabled = !state.resultData || state.resultLoading;
  if (!state.resultLoading) {
    renderResultCharts();
    renderResultStats();
  }
}

function setResultView(mode) {
  state.resultView = mode === 'psd' ? 'psd' : 'time';
  renderResultAnalysis();
}

function downloadResultBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportResultsCsv() {
  if (!state.resultData) return;
  const rows = [['case', 'independent', 'independent_unit', 'channel', 'unit', 'value']];
  for (const result of state.resultData.cases || []) {
    const independent = result.independent || {};
    for (const series of result.series || []) {
      for (let index = 0; index < Math.min(independent.values?.length || 0, series.values?.length || 0); index += 1) {
        rows.push([result.id, independent.values[index], independent.unit || '', series.name, series.unit || '', series.values[index]]);
      }
    }
  }
  const csv = rows.map(row => row.map(value => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n');
  downloadResultBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `openfast-results-${state.resultView}.csv`);
}

function exportResultsPng() {
  const canvases = [...document.querySelectorAll('#resultCharts canvas')];
  if (!canvases.length) return;
  const gap = 20;
  const width = Math.max(...canvases.map(canvas => canvas.width));
  const height = canvases.reduce((sum, canvas) => sum + canvas.height, 0) + gap * (canvases.length - 1);
  const merged = document.createElement('canvas');
  merged.width = width;
  merged.height = height;
  const context = merged.getContext('2d');
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, width, height);
  let top = 0;
  for (const canvas of canvases) {
    context.drawImage(canvas, 0, top);
    top += canvas.height + gap;
  }
  merged.toBlob(blob => { if (blob) downloadResultBlob(blob, `openfast-results-${state.resultView}.png`); }, 'image/png');
}

function printResults() {
  document.body.classList.add('print-results');
  const cleanup = () => document.body.classList.remove('print-results');
  window.addEventListener('afterprint', cleanup, { once: true });
  window.print();
  setTimeout(cleanup, 1000);
}

function renderJobFigures(job = {}) {
  const panel = $('jobFiguresPanel');
  const wrap = $('jobFigures');
  if (!panel || !wrap) return;
  const figures = job.comparisonFigures || [];
  panel.style.display = figures.length ? '' : 'none';
  wrap.innerHTML = '';
  for (const figure of figures) {
    const card = document.createElement('div');
    card.className = 'reference-card';
    const img = document.createElement('img');
    img.src = figure.url || '';
    img.alt = figure.label || 'comparison figure';
    const caption = document.createElement('div');
    caption.className = 'reference-caption';
    const warnings = Array.isArray(figure.warnings) && figure.warnings.length ? ` | ${figure.warnings.join('；')}` : '';
    caption.textContent = `${figure.label || '运行结果图'}${figure.source ? ` | ${figure.source}` : ''}${warnings}`;
    card.appendChild(img);
    card.appendChild(caption);
    wrap.appendChild(card);
  }
}

function formatElapsed(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function latestOpenFastProgress(output = '') {
  const pattern = /(?:\[([^\]]+)\]\s*)?Time:\s*([0-9.]+)\s+of\s+([0-9.]+)\s+seconds/g;
  let latest = null;
  for (const match of output.matchAll(pattern)) {
    const current = Number(match[2]);
    const total = Number(match[3]);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) continue;
    latest = {
      caseName: match[1] || '',
      current,
      total,
      percent: Math.min(100, Math.max(0, 100 * current / total))
    };
  }
  return latest;
}

function recentWorkerProgress(output = '', limit = 4) {
  const pattern = /(?:\[([^\]]+)\]\s*)?Time:\s*([0-9.]+)\s+of\s+([0-9.]+)\s+seconds/g;
  const byCase = new Map();
  for (const match of output.matchAll(pattern)) {
    const caseName = match[1] || 'OpenFAST';
    const current = Number(match[2]);
    const total = Number(match[3]);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) continue;
    const row = { caseName, current, total, percent: Math.min(100, Math.max(0, 100 * current / total)) };
    byCase.delete(caseName);
    byCase.set(caseName, row);
  }
  return [...byCase.values()].slice(-limit);
}

function renderJobState(job = { status: 'idle' }) {
  const status = job.status || 'idle';
  const active = ['queued', 'running'].includes(status);
  const statusLabels = { idle: '空闲', queued: '排队中', running: '运行中', done: '已完成', failed: '失败' };
  const label = statusLabels[status] || status;
  const elapsed = job.elapsed_s !== undefined ? formatElapsed(job.elapsed_s) : '';
  const progress = latestOpenFastProgress(job.output || '');
  const workers = Number(job.workers || 1);
  if (job.workers && $('parallelWorkers')) {
    state.parallelWorkers = Math.min(4, Math.max(1, workers));
    $('parallelWorkers').value = String(state.parallelWorkers);
    localStorage.setItem('openfastGui.parallelWorkers', String(state.parallelWorkers));
  }
  const progressCurrent = progress ? String(Number(progress.current.toFixed(1))) : '';
  const progressTotal = progress ? String(Number(progress.total.toFixed(1))) : '';
  const concurrencyLabel = workers > 1 ? ` · ${workers} 并行` : '';
  const progressLabel = progress
    ? `${progress.caseName ? `${progress.caseName} · ` : ''}${progressCurrent} / ${progressTotal} s · ${progress.percent.toFixed(1)}%`
    : active && workers > 1
      ? `${workers} 个 case 并行运行`
      : job.scenarioFile || (status === 'idle' ? '尚未运行' : '等待结果');

  const topButton = $('jobStatusButton');
  if (topButton) topButton.dataset.status = status;
  if ($('topJobStatus')) $('topJobStatus').textContent = `${label}${concurrencyLabel}${elapsed ? ` · ${elapsed}` : ''}`;
  if ($('topJobProgress')) $('topJobProgress').textContent = progressLabel;
  if ($('jobStatus')) {
    $('jobStatus').textContent = `${status}${workers > 1 ? ` · ${workers} workers` : ''}${elapsed ? ` · ${elapsed}` : ''}${job.returncode !== undefined ? ` · code ${job.returncode}` : ''}`;
    $('jobStatus').dataset.status = status;
  }
  if ($('runProgressText')) $('runProgressText').textContent = progressLabel;
  if ($('runProgressBar')) $('runProgressBar').style.width = `${progress ? progress.percent : status === 'done' ? 100 : 0}%`;
  const workerWrap = $('workerProgress');
  if (workerWrap) {
    const rows = workers > 1 ? recentWorkerProgress(job.output || '', workers) : [];
    workerWrap.hidden = workers <= 1 || (!active && !rows.length);
    if (!workerWrap.hidden) {
      workerWrap.innerHTML = rows.length
        ? rows.map(row => {
          const current = String(Number(row.current.toFixed(1)));
          const total = String(Number(row.total.toFixed(1)));
          return `<div class="worker-progress-item"><div class="worker-progress-head"><strong>${escapeHtml(row.caseName)}</strong><span>${current} / ${total} s · ${row.percent.toFixed(1)}%</span></div><div class="worker-progress-track"><span style="width:${row.percent}%"></span></div></div>`;
        }).join('')
        : Array.from({ length: workers }, (_, index) => `<div class="worker-progress-item waiting"><div class="worker-progress-head"><strong>Worker ${index + 1}</strong><span>初始化中</span></div><div class="worker-progress-track"><span></span></div></div>`).join('');
    }
  }
  if ($('runLog')) {
    $('runLog').textContent = job.output || (active ? '等待 OpenFAST 输出...' : status === 'idle' ? '尚未运行任务。' : '任务没有控制台输出。');
    if (active) $('runLog').scrollTop = $('runLog').scrollHeight;
  }
  state.jobRunning = active;
  setJobButtons(!active);
}

function updatePlotComparisonPreference() {
  const enabled = Boolean($('plotComparison')?.checked);
  state.plotComparison = enabled ? 'true' : 'false';
  localStorage.setItem('openfastGui.plotComparison', state.plotComparison);
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
  const query = state.scenarioQuery.trim().toLowerCase();
  const items = (state.scenarioList || []).filter(item => {
    if (!query) return true;
    return [item.name, item.file, item.description].some(value => String(value || '').toLowerCase().includes(query));
  });
  if (!items.length) {
    wrap.innerHTML = '<div class="empty-state">没有匹配的场景</div>';
    return;
  }
  for (const item of items) {
    const div = document.createElement('div');
    div.className = `scenario-item ${item.file === state.scenarioFile ? 'active' : ''}`;
    div.innerHTML = `<div class="item-title"><span>${escapeHtml(item.name)}</span><span class="badge">${item.cases}</span></div><div class="item-file">${escapeHtml(item.file)}</div><div class="item-meta">${escapeHtml(item.description || '')}</div>`;
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
    div.innerHTML = `<div class="item-title"><span>${escapeHtml(mode.name)}</span><span class="badge ${escapeHtml(mode.status)}">${escapeHtml(mode.status)}</span></div><div class="item-meta">${escapeHtml(mode.entry)}<br>${escapeHtml(mode.scope)}</div>`;
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

function dlcWindToken(value) {
  return String(value).replace('.', 'p');
}

function dlcSelectedRow() {
  const selected = Number($('dlcWindSpeed')?.value || 8);
  return DLC11_ROWS.find(row => row.wind === selected) || DLC11_ROWS.find(row => row.wind === 8) || DLC11_ROWS[0];
}

function isIeaModelSelected() {
  const files = activeFiles();
  return state.selectedModelId === 'iea_15_240_umaine' || String(files.fst || '').includes('IEA-15-240');
}

function isFocalModelSelected() {
  const files = activeFiles();
  return state.selectedModelId === 'focal_c4' || String(files.fst || '').includes('FOCAL_C4');
}

function isFocalRuntimeSelected() {
  return state.meta?.runtimeProfile?.runtimeFormat === 'v4';
}

function focalSelectedRows() {
  const selected = $('focalWaveGroup')?.value || 'both';
  return selected === 'both' ? FOCAL_TABLE24_ROWS : FOCAL_TABLE24_ROWS.filter(row => row.id === selected);
}

function renderFocalWaveReproduction() {
  const body = $('focalWaveTableBody');
  if (!body) return;
  const selectedIds = new Set(focalSelectedRows().map(row => row.id));
  body.innerHTML = '';
  for (const row of FOCAL_TABLE24_ROWS) {
    const tr = document.createElement('tr');
    tr.className = selectedIds.has(row.id) ? 'selected' : '';
    tr.innerHTML = `<td>E${row.waveStart}-E${row.waveEnd}</td><td>${row.seaState}</td><td>${row.hs.toFixed(1)}</td><td>${row.tp}</td><td>${row.gamma.toFixed(2)}</td><td>2000-8000 s</td>`;
    tr.onclick = () => {
      $('focalWaveGroup').value = row.id;
      renderFocalWaveReproduction();
    };
    body.appendChild(tr);
  }
  const count = focalSelectedRows().length * 5;
  const status = $('focalWaveStatus');
  if (status) {
    status.innerHTML = isFocalModelSelected() && isFocalRuntimeSelected()
      ? `将生成 ${count} 个 wave-only case；Wave ID 用于标签，OpenFAST 随机相位由 WaveSeed(1) 生成。`
      : '<span class="danger-text">请先选择 FOCAL C4 模型和 OpenFAST v4 runtime。</span>';
  }
}

function renderDlcLearning() {
  const select = $('dlcWindSpeed');
  if (!select) return;
  const currentValue = select.value || '8';
  if (!select.options.length) {
    for (const row of DLC11_ROWS) {
      const option = document.createElement('option');
      option.value = row.wind;
      option.textContent = `${row.wind} m/s | Hs ${row.hs} m | Tp ${row.tp} s | Gamma ${row.gamma}`;
      select.appendChild(option);
    }
  }
  select.value = DLC11_ROWS.some(row => String(row.wind) === currentValue) ? currentValue : '8';
  const selected = dlcSelectedRow();

  const status = $('dlcStatus');
  if (status) {
    status.innerHTML = [
      isIeaModelSelected()
        ? '当前模型适配 IEA 15MW / UMaineSemi。'
        : '<span class="danger-text">请先在顶部模型模板中选择 IEA-15-240-RWT UMaineSemi。</span>',
      `当前选择: Wind=${selected.wind} m/s, Hs=${selected.hs} m, Tp=${selected.tp} s, Gamma=${selected.gamma}.`
    ].join('<br>');
  }

  const body = $('dlcTableBody');
  if (body) {
    body.innerHTML = '';
    for (const row of DLC11_ROWS) {
      const tr = document.createElement('tr');
      tr.className = row.wind === selected.wind ? 'selected' : '';
      tr.innerHTML = `<td>${row.wind}</td><td>${row.hs.toFixed(2)}</td><td>${row.tp.toFixed(2)}</td><td>${row.gamma.toFixed(2)}</td><td>DLC 1.1 NTM, aligned wind/wave 0 deg</td>`;
      tr.onclick = () => {
        select.value = row.wind;
        renderDlcLearning();
      };
      body.appendChild(tr);
    }
  }

  const help = $('dlcParamHelp');
  if (help && !help.children.length) {
    for (const [key, file, description] of DLC_PARAM_HELP) {
      const card = document.createElement('div');
      card.className = 'param-help-card';
      card.innerHTML = `<strong>${escapeHtml(key)}</strong><span>${escapeHtml(file)} | ${escapeHtml(description)}</span>`;
      help.appendChild(card);
    }
  }
}

function fileDir(fileName) {
  const normalized = String(fileName || '').replaceAll('\\', '/');
  const index = normalized.lastIndexOf('/');
  return index >= 0 ? normalized.slice(0, index) : '';
}

function dlcNumber(id, fallback) {
  const value = Number($(id)?.value);
  return Number.isFinite(value) ? value : fallback;
}

function dlcBtsSourceForCase(template, row, seedIndex, windSeed) {
  return String(template || '')
    .replaceAll('{seed}', String(seedIndex))
    .replaceAll('{windSeed}', String(windSeed))
    .replaceAll('{wind}', dlcWindToken(row.wind))
    .replaceAll('{wind_speed}', String(row.wind));
}

function paperMetricsComparison(row) {
  return {
    mode: 'paper_metrics',
    label: `DLC 1.1 NTM row: Wind=${row.wind} m/s, Hs=${row.hs} m, Tp=${row.tp} s, Gamma=${row.gamma}`,
    reference: 'NREL/TP-5000-76773 Section 4, Table 12 and Figures 21-24 checks',
    start_time_s: 100,
    limits: {
      platform_pitch_abs_max_deg: 6,
      horizontal_offset_abs_max_m: 25,
      rna_accel_abs_max_mps2: 1.5,
      fairlead_tension_abs_max_kN: 22286
    }
  };
}

function buildDlcCase(row, seedIndex, options) {
  const files = activeFiles();
  const windToken = dlcWindToken(row.wind);
  const seedText = String(seedIndex).padStart(2, '0');
  const modePrefix = options.windMode === 'ntm_formal' ? 'ntm' : 'steady';
  const caseName = `dlc1p1_${modePrefix}_U${windToken}_seed${seedText}`;
  const windSeed = options.windSeedBase + seedIndex - 1;
  const waveSeed = options.waveSeedBase + seedIndex - 1;
  const inflowDir = fileDir(files.inflow);
  const windDir = inflowDir ? `${inflowDir}/Wind` : 'Wind';
  const btsName = `${caseName}.bts`;
  const btsTarget = `${windDir}/${btsName}`;
  const fileNameBts = `Wind/${btsName}`;
  const set = {
    [files.fst]: {
      TMax: options.tmax,
      CompInflow: 1,
      CompAero: 2,
      CompServo: 1,
      [files.seaStateCompKey]: 1,
      CompHydro: 1,
      CompMooring: isIeaModelSelected() ? 3 : files.defaultMooring
    },
    [files.inflow]: options.windMode === 'ntm_formal'
      ? { WindType: 3, HWindSpeed: row.wind, FileName_BTS: fileNameBts }
      : { WindType: 1, HWindSpeed: row.wind, FileName_BTS: 'none' },
    [files.sea]: {
      WaveMod: 2,
      WaveTMax: options.tmax + 250,
      WaveDT: 0.25,
      WaveHs: row.hs,
      WaveTp: row.tp,
      WavePkShp: row.gamma,
      WvLowCOff: 0.111527,
      WvHiCOff: 3.2,
      WaveDir: 0,
      'WaveSeed(1)': waveSeed
    }
  };
  const caseData = {
    name: caseName,
    fst: files.fst,
    hydro_file: state.meta?.modelProfile?.hydroFile || '',
    set,
    dlc_metadata: {
      dlc_id: 'DLC 1.1',
      wind_model: options.windMode,
      wind_speed: row.wind,
      wave_hs: row.hs,
      wave_tp: row.tp,
      gamma: row.gamma,
      seed_index: seedIndex,
      wind_seed: windSeed,
      wave_seed: waveSeed
    },
    comparison: options.plotMetrics ? paperMetricsComparison(row) : undefined,
    notes: options.windMode === 'ntm_formal'
      ? 'Formal DLC 1.1 NTM case. Requires the referenced TurbSim .bts file before OpenFAST can run.'
      : 'Training case using steady wind with the DLC 1.1 wave condition; useful for learning and quick parameter checks.',
    timeout: 7200
  };
  if (!caseData.hydro_file) delete caseData.hydro_file;
  if (!caseData.comparison) delete caseData.comparison;
  if (options.windMode === 'ntm_formal') {
    caseData.turbsim_input = {
      target: `${windDir}/${caseName}.in`,
      wind_model: 'NTM',
      wind_speed: row.wind,
      seed: windSeed,
      analysis_time: options.tmax + 120,
      timestep: 0.05,
      hub_height: 150,
      grid_height: 252,
      grid_width: 252,
      iec_turbulence_class: 'B'
    };
    const source = dlcBtsSourceForCase(options.btsSource, row, seedIndex, windSeed).trim();
    if (source) caseData.assets = [{ source, target: btsTarget }];
  }
  return caseData;
}

function generateDlcCases() {
  collectForm();
  if (!isIeaModelSelected()) {
    throw new Error('请先选择 IEA-15-240-RWT UMaineSemi 模型，再生成 DLC 1.1 工况。');
  }
  const row = dlcSelectedRow();
  const seedCount = Math.max(1, Math.min(12, Math.trunc(dlcNumber('dlcSeedCount', 6))));
  const options = {
    windMode: $('dlcWindMode').value,
    tmax: Math.max(60, dlcNumber('dlcTMax', 600)),
    windSeedBase: Math.trunc(dlcNumber('dlcWindSeedBase', 10101)),
    waveSeedBase: Math.trunc(dlcNumber('dlcWaveSeedBase', -561580799)),
    btsSource: $('dlcBtsSource').value || '',
    plotMetrics: Boolean($('dlcPlotMetrics').checked)
  };
  const cases = [];
  for (let seed = 1; seed <= seedCount; seed += 1) {
    cases.push(buildDlcCase(row, seed, options));
  }
  const windToken = dlcWindToken(row.wind);
  state.scenarioFile = `iea_dlc1p1_${options.windMode}_U${windToken}.json`;
  state.scenario = {
    name: `iea_dlc1p1_${options.windMode}_U${windToken}`,
    description: `DLC 1.1 learning pack for IEA 15MW UMaineSemi: U=${row.wind} m/s, Hs=${row.hs} m, Tp=${row.tp} s, Gamma=${row.gamma}, seeds=${seedCount}.`,
    model_id: state.selectedModelId,
    runtime_id: state.selectedRuntimeId,
    cases
  };
  state.selectedCase = 0;
  state.plotComparison = options.plotMetrics ? 'true' : 'false';
  localStorage.setItem('openfastGui.plotComparison', state.plotComparison);
  renderAll();
  toast(`已生成 ${seedCount} 个 DLC 1.1 case`);
}

function buildFocalWaveCase(row, waveId) {
  const files = activeFiles();
  const waveLabel = `E${waveId}`;
  const set = {
    [files.fst]: {
      TMax: row.duration,
      CompInflow: 0,
      CompAero: 0,
      CompServo: 0,
      [files.seaStateCompKey]: 1,
      CompHydro: 1,
      CompMooring: files.defaultMooring
    },
    [files.sea]: {
      WaveMod: 2,
      WaveStMod: 0,
      WaveTMax: row.duration,
      WaveDT: 0.041833001,
      WaveHs: row.hs,
      WaveTp: row.tp,
      WavePkShp: row.gamma,
      WvLowCOff: 0,
      WvHiCOff: 75.098,
      WaveDir: 0,
      WaveNDAmp: false,
      'WaveSeed(1)': waveId
    }
  };
  return {
    name: `focal_${waveLabel.toLowerCase()}_jonswap`,
    fst: files.fst,
    set,
    focal_wave: {
      group: row.id,
      wave_id: waveLabel,
      reproduction_level: 'statistical_openfast_jonswap',
      hs: row.hs,
      tp: row.tp,
      gamma: row.gamma,
      psd_window_s: [2000, 8000]
    },
    notes: `FOCAL Table 24 ${waveLabel}: statistical OpenFAST JONSWAP realization; not the original basin phase seed.`,
    timeout: 7200
  };
}

function generateFocalWaveCases() {
  collectForm();
  if (!isFocalModelSelected() || !isFocalRuntimeSelected()) {
    throw new Error('请先选择 FOCAL C4 模型和 OpenFAST v4 runtime，再生成 Table 24 工况。');
  }
  const rows = focalSelectedRows();
  const cases = [];
  for (const row of rows) {
    for (let waveId = row.waveStart; waveId <= row.waveEnd; waveId += 1) {
      cases.push(buildFocalWaveCase(row, waveId));
    }
  }
  const token = rows.length === 2 ? 'e11_e25' : rows[0].id.toLowerCase();
  const shouldPlot = Boolean($('focalWavePlot').checked);
  state.scenarioFile = `focal_table24_${token}.json`;
  state.scenario = {
    name: `focal_table24_${token}`,
    description: 'FOCAL Campaign 4 Table 24 five-seed statistical reproduction using OpenFAST JONSWAP waves.',
    model_id: state.selectedModelId,
    runtime_id: state.selectedRuntimeId,
    reference_figures: rows.map(row => ({
      label: `实验参考 E${row.waveStart}-E${row.waveEnd}: five wave seeds and PSD`,
      url: row.referenceUrl,
      source: 'UMaine ASCC Report 23-57-1183, Figure 25/26; local FOCAL Campaign 4 CSV'
    })),
    aggregate_plot: {
      type: 'focal_wave_calibration',
      groups: rows.map(row => row.id),
      mode_frequencies_hz: FOCAL_MODE_FREQUENCIES,
      psd_window_s: [2000, 8000]
    },
    cases
  };
  state.selectedCase = 0;
  state.plotComparison = shouldPlot ? 'true' : 'false';
  localStorage.setItem('openfastGui.plotComparison', state.plotComparison);
  renderAll();
  toast(`已生成 ${cases.length} 个 FOCAL Table 24 case`);
}

function renderCases() {
  const wrap = $('caseList');
  wrap.innerHTML = '';
  state.scenario.cases.forEach((c, index) => {
    const div = document.createElement('div');
    div.className = `case-item ${index === state.selectedCase ? 'active' : ''}`;
    const setCount = Object.values(c.set || {}).reduce((n, values) => n + Object.keys(values).length, 0);
    div.innerHTML = `<div class="item-title"><span>${escapeHtml(c.name || `case_${index + 1}`)}</span><span class="badge">${setCount} keys</span></div><div class="item-meta">${escapeHtml(c.notes || '')}</div>`;
    div.onclick = () => { collectForm(); state.selectedCase = index; renderAll(); };
    wrap.appendChild(div);
  });
  const c = currentCase();
  if ($('caseCount')) $('caseCount').textContent = `${state.selectedCase + 1} / ${state.scenario.cases.length} · ${state.scenario.cases.length} cases`;
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
    const hydroFile = state.meta?.modelProfile?.hydroFile || 'HydroDyn.dat';
    const title = document.createElement('div');
    title.className = 'matrix-title';
    title.innerHTML = `<strong>${label}</strong><span>${block} | ${hydroFile} | ${count} 个覆盖值</span>`;
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

function renderModelStructure() {
  const structure = state.meta?.modelStructure || {};
  const nodes = Array.isArray(structure.nodes) ? structure.nodes : [];
  const edges = Array.isArray(structure.edges) ? structure.edges : [];
  const summary = structure.summary || {};
  const summaryEl = $('modelSummary');
  const list = $('modelFileList');
  const details = $('modelDependencyList');
  if (!summaryEl || !list || !details) return;

  summaryEl.textContent = `${summary.files || 0} 个文件 · ${summary.existing || 0} 存在 · ${summary.missing || 0} 缺失 · ${summary.outListFiles || 0} 个文件含输出通道`;
  const warnings = [...(structure.warnings || [])];
  if (summary.missing) warnings.push(`${summary.missing} 个引用文件不存在；可能属于未启用模块，运行前仍应核对。`);
  $('modelWarnings').innerHTML = warnings.map(value => `<div>${escapeHtml(value)}</div>`).join('');

  if (!nodes.some(node => node.id === state.selectedModelFile)) {
    state.selectedModelFile = structure.main || nodes[0]?.id || '';
  }
  const query = ($('modelFileSearch')?.value || '').trim().toLowerCase();
  const matchingIds = new Set();
  if (query) {
    for (const edge of edges) {
      if ([edge.key, edge.reference, edge.source, edge.target].some(value => String(value || '').toLowerCase().includes(query))) {
        matchingIds.add(edge.source);
        matchingIds.add(edge.target);
      }
    }
  }
  const filtered = nodes.filter(node => !query || node.id.toLowerCase().includes(query) || node.kind.toLowerCase().includes(query) || matchingIds.has(node.id));
  list.innerHTML = '';
  if (!filtered.length) list.innerHTML = '<div class="empty-state">没有匹配的模型文件</div>';
  for (const node of filtered) {
    const incoming = edges.filter(edge => edge.target === node.id).length;
    const outgoing = edges.filter(edge => edge.source === node.id).length;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `model-file-item ${node.id === state.selectedModelFile ? 'active' : ''} ${node.exists ? '' : 'missing'}`;
    button.innerHTML = `<span class="model-file-main"><strong>${escapeHtml(node.id)}</strong><span>${escapeHtml(node.kind)} · depth ${node.depth}</span></span><span class="model-file-stats"><span class="badge ${node.exists ? '' : 'missing'}">${node.exists ? 'OK' : 'MISSING'}</span><span>${incoming} in / ${outgoing} out${node.outListCount ? ` / ${node.outListCount} OutList` : ''}</span></span>`;
    button.onclick = () => { state.selectedModelFile = node.id; renderModelStructure(); };
    list.appendChild(button);
  }

  const selected = nodes.find(node => node.id === state.selectedModelFile);
  $('modelDependencyTitle').textContent = selected ? selected.id : '引用关系';
  details.innerHTML = '';
  if (!selected) {
    details.innerHTML = '<div class="empty-state">选择一个文件查看引用</div>';
    return;
  }
  const related = edges.filter(edge => edge.source === selected.id || edge.target === selected.id);
  const meta = document.createElement('div');
  meta.className = 'model-file-meta';
  meta.innerHTML = `<div><span>绝对路径</span><code>${escapeHtml(selected.path)}</code></div><div><span>类型</span><strong>${escapeHtml(selected.kind)}</strong></div><div><span>普通参数</span><strong>${selected.scalarCount || 0}</strong></div><div><span>OutList</span><strong>${selected.outListCount || 0}</strong></div>`;
  details.appendChild(meta);
  if (!related.length) {
    details.insertAdjacentHTML('beforeend', '<div class="empty-state">没有发现文件引用</div>');
    return;
  }
  for (const edge of related) {
    const outgoing = edge.source === selected.id;
    const row = document.createElement('button');
    row.type = 'button';
    row.className = `dependency-row ${edge.exists ? '' : 'missing'}`;
    const other = outgoing ? edge.target : edge.source;
    row.innerHTML = `<span class="dependency-direction">${outgoing ? '引用 →' : '← 被引用'}</span><span class="dependency-target"><strong>${escapeHtml(other)}</strong><small>${escapeHtml(edge.key || 'table reference')} · line ${edge.line}${edge.exists ? '' : ' · MISSING'}</small></span>`;
    row.onclick = () => { state.selectedModelFile = other; renderModelStructure(); };
    details.appendChild(row);
  }
}

function normalizedOutlistEdits() {
  const c = currentCase();
  if (Array.isArray(c.outlist_edits)) return c.outlist_edits;
  if (c.outlist_edits && typeof c.outlist_edits === 'object') {
    const rows = [];
    for (const [file, edits] of Object.entries(c.outlist_edits)) {
      for (const edit of (Array.isArray(edits) ? edits : [edits])) rows.push({ file, ...edit });
    }
    c.outlist_edits = rows;
    return rows;
  }
  return [];
}

function templateOutlistSection(file, sectionIndex) {
  return (state.meta?.outLists?.[file] || []).find(section => Number(section.section) === Number(sectionIndex));
}

function effectiveOutlistChannels(file, sectionIndex) {
  const edit = normalizedOutlistEdits().find(row => row.file === file && Number(row.section || 0) === Number(sectionIndex));
  return [...(edit?.channels || templateOutlistSection(file, sectionIndex)?.channels || [])];
}

function sameChannels(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function setOutlistChannels(file, sectionIndex, values) {
  const channels = [];
  for (const raw of values) {
    const value = String(raw || '').trim().replace(/^"|"$/g, '');
    if (value && !channels.includes(value)) channels.push(value);
  }
  const c = currentCase();
  const next = normalizedOutlistEdits().filter(row => !(row.file === file && Number(row.section || 0) === Number(sectionIndex)));
  const baseline = [...(templateOutlistSection(file, sectionIndex)?.channels || [])];
  if (!sameChannels(channels, baseline)) next.push({ file, section: Number(sectionIndex), channels });
  if (next.length) c.outlist_edits = next;
  else delete c.outlist_edits;
  renderOutlistEditor();
  renderJson();
}

function resetCurrentOutlistFile() {
  const file = state.selectedOutlistFile;
  if (!file) return;
  const c = currentCase();
  const next = normalizedOutlistEdits().filter(row => row.file !== file);
  if (next.length) c.outlist_edits = next;
  else delete c.outlist_edits;
  renderOutlistEditor();
  renderJson();
  toast(`已恢复 ${file} 的模板输出通道`);
}

function renderOutlistEditor() {
  const select = $('outlistFileSelect');
  const wrap = $('outlistSections');
  const status = $('outlistStatus');
  if (!select || !wrap || !status) return;
  const files = Object.keys(state.meta?.outLists || {}).sort((a, b) => a.localeCompare(b));
  if (!files.includes(state.selectedOutlistFile)) state.selectedOutlistFile = files[0] || '';
  select.innerHTML = files.map(file => `<option value="${escapeHtml(file)}">${escapeHtml(file)}</option>`).join('');
  select.value = state.selectedOutlistFile;
  const edits = normalizedOutlistEdits();
  const modifiedFiles = new Set(edits.map(row => row.file));
  status.textContent = `${files.length} 个文件含输出区块 · 当前 case 修改了 ${modifiedFiles.size} 个文件`;
  wrap.innerHTML = '';
  if (!state.selectedOutlistFile) {
    wrap.innerHTML = '<div class="empty-state">当前模型没有发现 OutList 区块</div>';
    return;
  }
  const sections = state.meta.outLists[state.selectedOutlistFile] || [];
  for (const section of sections) {
    const sectionIndex = Number(section.section || 0);
    const channels = effectiveOutlistChannels(state.selectedOutlistFile, sectionIndex);
    const edited = edits.some(row => row.file === state.selectedOutlistFile && Number(row.section || 0) === sectionIndex);
    const block = document.createElement('section');
    block.className = 'outlist-section';
    const head = document.createElement('div');
    head.className = 'outlist-section-head';
    head.innerHTML = `<div><strong>Section ${sectionIndex + 1}</strong><span>line ${section.headerLine}-${section.endLine} · ${channels.length} channels</span></div><span class="badge ${edited ? 'edited' : ''}">${edited ? '已修改' : '模板'}</span>`;
    block.appendChild(head);
    const rows = document.createElement('div');
    rows.className = 'outlist-channel-list';
    if (!channels.length) rows.innerHTML = '<div class="empty-state">当前没有输出通道</div>';
    channels.forEach((channel, index) => {
      const row = document.createElement('div');
      row.className = 'outlist-channel-row';
      const order = document.createElement('span');
      order.textContent = String(index + 1);
      const input = document.createElement('input');
      input.value = channel;
      input.setAttribute('aria-label', `输出通道 ${index + 1}`);
      input.onchange = () => {
        const next = [...channels];
        next[index] = input.value;
        setOutlistChannels(state.selectedOutlistFile, sectionIndex, next);
      };
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'remove';
      remove.textContent = '删';
      remove.title = `删除 ${channel}`;
      remove.onclick = () => setOutlistChannels(state.selectedOutlistFile, sectionIndex, channels.filter((_, itemIndex) => itemIndex !== index));
      row.append(order, input, remove);
      rows.appendChild(row);
    });
    block.appendChild(rows);
    const add = document.createElement('div');
    add.className = 'outlist-add-row';
    const addInput = document.createElement('input');
    addInput.placeholder = '输入 OpenFAST 输出通道名';
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'mini-button';
    addButton.textContent = '添加通道';
    const commit = () => {
      const value = addInput.value.trim();
      if (!value) return;
      setOutlistChannels(state.selectedOutlistFile, sectionIndex, [...channels, value]);
    };
    addButton.onclick = commit;
    addInput.onkeydown = event => { if (event.key === 'Enter') commit(); };
    add.append(addInput, addButton);
    block.appendChild(add);
    wrap.appendChild(block);
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
  state.jsonDirty = false;
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
  syncQuickInputsToCase();
  normalizedMatrixEdits(true);
  repairScenarioHydroReferences(state.scenario);
}

function cleanupScenarioForSave(data) {
  repairScenarioHydroReferences(data);
  for (const c of data.cases || []) {
    if (Array.isArray(c.matrix_edits) && c.matrix_edits.length === 0) delete c.matrix_edits;
    if (Array.isArray(c.outlist_edits) && c.outlist_edits.length === 0) delete c.outlist_edits;
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
  await loadResultsCatalog({ preserve: false, preferScenario: true });
  state.selectedCase = 0;
  renderAll();
  toast(`已载入 ${file}`);
}

async function saveScenario() {
  collectForm();
  let data = state.scenario;
  if (state.jsonDirty && $('jsonEditor').value.trim()) {
    try { data = JSON.parse($('jsonEditor').value); state.scenario = data; }
    catch (err) { throw new Error(`JSON 格式错误: ${err.message}`); }
  } else {
    renderJson();
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
        resume: $('resumeCompleted').checked,
        plotComparison: $('plotComparison').checked && !generateOnly,
        workers: Math.min(4, Math.max(1, Number($('parallelWorkers').value) || 1)),
        modelId: state.selectedModelId,
        runtimeId: state.selectedRuntimeId
      }
    })
  });
  state.currentJob = data.jobId;
  state.jobRunning = true;
  renderJobFigures({ comparisonFigures: [] });
  renderJobState({ status: 'queued', scenarioFile: state.scenarioFile, workers: state.parallelWorkers, output: '' });
  setActiveTab('runlog');
  pollJob();
}

function setJobButtons(enabled) {
  $('generateBtn').disabled = !enabled;
  $('runBtn').disabled = !enabled;
  $('parallelWorkers').disabled = !enabled;
  $('resumeCompleted').disabled = !enabled;
}

async function pollJob() {
  if (!state.currentJob) return;
  if (state.pollTimer) clearTimeout(state.pollTimer);
  const job = await api(`/api/jobs/${state.currentJob}`);
  renderJobState(job);
  if (['queued', 'running'].includes(job.status)) {
    state.pollTimer = setTimeout(pollJob, 1200);
  } else {
    toast(job.status === 'done' ? '任务完成' : '任务失败');
    renderJobFigures(job);
    await loadMeta();
    await loadResultsCatalog({ preserve: false, preferScenario: true });
  }
}

async function restoreLatestJob() {
  const payload = await api('/api/jobs');
  const jobs = payload.jobs || [];
  const job = jobs.find(item => ['queued', 'running'].includes(item.status)) || jobs[0];
  if (!job) {
    renderJobState({ status: 'idle' });
    return;
  }
  state.currentJob = job.id;
  renderJobState(job);
  renderJobFigures(job);
  if (['queued', 'running'].includes(job.status)) pollJob();
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
    setDeep(files.sea, 'WavePkShp', parseValue($('quickWavePkShp').value.trim() || 'DEFAULT'));
    setDeep(files.sea, 'WaveDir', Number($('quickWaveDir').value || 0));
  }
  renderAll();
  toast(`已应用 ${preset.name}`);
}

function setActiveTab(name, persist = true) {
  if (!$(`tab-${name}`)) name = 'compose';
  state.activeTab = name;
  document.querySelectorAll('.tab').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
  document.querySelectorAll('.tab-page').forEach(page => page.classList.toggle('active', page.id === `tab-${name}`));
  if (persist) localStorage.setItem('openfastGui.activeTab', name);
  if (persist) document.querySelector(`.tab[data-tab="${name}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  if (name === 'results' && state.resultData) requestAnimationFrame(renderResultCharts);
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
    state.selectedModelFile = '';
    state.selectedOutlistFile = '';
    delete currentCase().hydrodyn_tables;
    renderAll();
  };
  $('runtimeSelect').onchange = async () => {
    collectForm();
    state.selectedRuntimeId = $('runtimeSelect').value;
    localStorage.setItem('openfastGui.runtimeId', state.selectedRuntimeId);
    await loadMeta();
    state.selectedModelFile = '';
    state.selectedOutlistFile = '';
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
  $('dlcGenerateBtn').onclick = () => { try { generateDlcCases(); } catch (err) { toast(err.message); } };
  $('focalWaveGenerateBtn').onclick = () => { try { generateFocalWaveCases(); } catch (err) { toast(err.message); } };
  ['focalWaveGroup', 'focalWavePlot'].forEach(id => {
    const el = $(id);
    if (el) el.oninput = renderFocalWaveReproduction;
  });
  ['dlcWindSpeed', 'dlcWindMode', 'dlcSeedCount', 'dlcTMax', 'dlcWindSeedBase', 'dlcWaveSeedBase', 'dlcBtsSource', 'dlcPlotMetrics'].forEach(id => {
    const el = $(id);
    if (el) el.oninput = renderDlcLearning;
  });
  $('formatJsonBtn').onclick = () => { collectForm(); renderJson(); };
  $('saveBtn').onclick = () => saveScenario().catch(err => toast(err.message));
  $('generateBtn').onclick = () => startJob(true).catch(err => toast(err.message));
  $('runBtn').onclick = () => startJob(false).catch(err => toast(err.message));
  $('refreshBtn').onclick = async () => { await loadMeta(); await loadResultsCatalog(); renderAll(); await restoreLatestJob(); };
  $('jobStatusButton').onclick = () => setActiveTab('runlog');
  $('scenarioSearch').oninput = () => { state.scenarioQuery = $('scenarioSearch').value; renderScenarioList(); };
  $('plotComparison').onchange = updatePlotComparisonPreference;
  $('parallelWorkers').onchange = () => {
    state.parallelWorkers = Math.min(4, Math.max(1, Number($('parallelWorkers').value) || 1));
    $('parallelWorkers').value = String(state.parallelWorkers);
    localStorage.setItem('openfastGui.parallelWorkers', String(state.parallelWorkers));
  };
  $('catalogSearch').oninput = renderCatalog;
  $('modelFileSearch').oninput = renderModelStructure;
  $('outlistFileSelect').onchange = () => { state.selectedOutlistFile = $('outlistFileSelect').value; renderOutlistEditor(); };
  $('resetOutlistFileBtn').onclick = resetCurrentOutlistFile;
  $('resultRefreshBtn').onclick = () => loadResultsCatalog();
  $('resultScenarioFilter').onchange = () => { state.resultScenarioFilter = $('resultScenarioFilter').value; renderResultsWorkspace(); };
  $('resultFileSearch').oninput = renderResultFileList;
  $('resultSelectPrimaryBtn').onclick = selectPrimaryResults;
  $('resultChannelSearch').oninput = renderResultChannelList;
  $('resultSelectCommonBtn').onclick = () => selectCommonResultChannels();
  $('resultClearChannelsBtn').onclick = () => { state.selectedResultChannels = []; invalidateResultAnalysis(); renderResultsWorkspace(); };
  $('resultAnalyzeBtn').onclick = analyzeSelectedResults;
  $('resultViewTime').onclick = () => setResultView('time');
  $('resultViewPsd').onclick = () => setResultView('psd');
  $('resultExportCsvBtn').onclick = exportResultsCsv;
  $('resultExportPngBtn').onclick = exportResultsPng;
  $('resultPrintBtn').onclick = printResults;
  $('jsonEditor').oninput = () => { state.jsonDirty = true; };
  ['quickTMax', 'quickWind', 'quickWaveMod', 'quickHs', 'quickTp', 'quickWavePkShp', 'quickWaveDir'].forEach(id => {
    $(id).oninput = () => {
      $(id).dataset.dirty = '1';
      syncQuickInputsToCase();
      renderJson();
    };
  });
  $('caseName').onchange = () => { currentCase().name = $('caseName').value.trim(); renderAll(); };
  $('caseNotes').onchange = () => { currentCase().notes = $('caseNotes').value.trim(); renderJson(); };
}

async function init() {
  bindEvents();
  renderJobFigures({ comparisonFigures: [] });
  renderJobState({ status: 'idle' });
  await loadMeta();
  if (state.scenarioList?.length) {
    const first = state.scenarioList.find(s => s.file === 'focal_irregular_wave_compare.json') || state.scenarioList[0];
    await loadScenario(first.file);
  } else {
    normalizeScenario();
    renderAll();
    await loadResultsCatalog();
  }
  window.addEventListener('resize', () => {
    clearTimeout(state.resultResizeTimer);
    state.resultResizeTimer = setTimeout(() => {
      if (state.activeTab === 'results' && state.resultData) renderResultCharts();
    }, 160);
  });
  await restoreLatestJob();
}

init().catch(err => {
  console.error(err);
  toast(err.message);
});
