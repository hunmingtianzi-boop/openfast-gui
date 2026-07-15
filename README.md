# OpenFAST GUI

面向 OpenFAST 工程模型的本地可视化工作台，重点支持 **IEA‑15‑240‑RWT + OpenFAST v5** 的场景配置、HydroDyn/Morison 几何编辑、不规则波批量计算与响应 PSD 分析，同时保留 FOCAL C4 + OpenFAST v4 兼容工作流。

界面采用中文主文案、英文辅助说明。模型模板、OpenFAST 可执行文件、原始数据和仿真结果均留在本机；仓库只保存 GUI、运行工具、测试和可复用场景定义。

## 当前能力 / Highlights

- **运行就绪检查**：统一检查模型根目录、主 `.fst`、OpenFAST runtime、模块输入文件、场景归属和覆盖目标；阻断项会在全局状态条和相关页面就地显示。
- **模型与运行时配置**：GUI 内校验并保存本机路径；本地覆盖按字段合并，不会丢失默认 profile 的 `.fst`、HydroDyn 或依赖文件定义。
- **主模块与场景编辑**：以有语义的中英双语选项配置 `CompInflow`、`CompAero`、`CompSeaSt`、`CompHydro`、`CompMooring` 等开关，避免场景与模型上下文混用。
- **HydroDyn/Morison 联动编辑**：节点、圆柱/矩形截面、构件和水动力系数成组维护；添加、删除或修改共享节点时，关联构件同步更新。
- **XYZ 几何校核器**：使用仓库内置 Three.js 显示 3D、XY、XZ、YZ 视图，支持水面、海床、波向、节点编号和 `MDivSize` 估算离散点图层；图形与表格选择双向联动。
- **结构化几何诊断**：即时定位无效坐标、零长度构件、缺失端点/截面、无效尺寸、孤立节点、未引用截面和 v4/v5 格式不兼容。
- **批量场景运行**：每个 case 在独立 `runs/` 副本中生成和运行，支持 1–4 个并行 worker、断点续跑、失败后继续和同名输出覆盖。
- **结果与 PSD**：读取 OpenFAST ASCII `.out` 和二进制 `.outb`，显示时程、统计量和 Welch PSD；多随机种子场景可自动生成聚合响应 PSD。
- **工程扩展**：包含模块插件编辑器、OutList、线性化模态、VTK 查看、TurbSim、FAST.Farm 和独立模块 driver 配置入口。

## 5 分钟启动 / Quick start

要求：Windows、PowerShell、Python 3.10+。

```powershell
git clone https://github.com/hunmingtianzi-boop/openfast-gui.git
cd openfast-gui
pip install -r .\requirements.txt
.\scripts\08_start_ui.ps1
```

浏览器打开：

```text
http://127.0.0.1:8765
```

端口被占用时：

```powershell
.\scripts\08_start_ui.ps1 -Port 8766
```

进入 GUI 后，先在顶部 **“模型、运行时与当前场景 / Model, runtime and current scenario”** 区域完成以下配置：

1. 选择模型 profile。
2. 选择与模型格式一致的 OpenFAST runtime。
3. 在“模型与运行时路径”中填写本机模型根目录和 `OpenFAST.exe`。
4. 确认全局状态条没有阻断项，再编辑或运行场景。

## OpenFAST v5 与 IEA‑15MW

当前主开发基线为：

- `IEA-15-240-RWT UMaineSemi`
- `OpenFAST v5.0.0 official` 或兼容的 v5 runtime
- SeaState + HydroDyn v5 输入格式
- MoorDyn 浮式系泊工作流

OpenFAST v4 继续用于已有 FOCAL C4 输入，不建议用它运行包含矩形 Morison 截面的 v5 HydroDyn 模型。GUI 会在模型、runtime 或 HydroDyn 格式不匹配时阻止提交运行。

共享模型配置位于 [config/model_profiles.json](config/model_profiles.json)。`${WORKSPACE_ROOT}` 表示本仓库的父目录；GUI 保存的本机路径位于被 Git 忽略的 `config/local_model_profiles.json`，因此换电脑时只需重新配置路径，无需修改公共 profile。

> 仓库不附带 NREL/OpenFAST 可执行文件、完整 IEA/FOCAL 模型、实验原始数据或运行结果。请按各模型和工具的许可要求自行准备。

## IEA‑15MW Y 形 Morison 示例

[scenarios/iea_15_240_umaine_y_morison_rectangular.json](scenarios/iea_15_240_umaine_y_morison_rectangular.json) 提供当前 GUI 的综合示例：

- VolturnUS‑S Y 形三柱布局；
- 三根矩形下浮箱和三根圆形上斜撑；
- 圆柱与矩形截面、共享节点和 member-based 系数联动；
- 五个随机种子的 600 s JONSWAP 不规则波试跑；
- `TMax = WaveTMax = 600 s`；
- 以 100–600 s 时间窗生成 `Wave1Elev`、`PtfmSurge`、`PtfmHeave`、`PtfmPitch` 聚合 PSD。

在 HydroDyn 页面选择构件后，左侧 XYZ 视图用于几何核对，右侧表单仍是唯一数据入口。首版三维视图不允许拖动节点，避免误改工程参数。

场景中的 `Cd=0.8` 是用于几何和流程验证的未标定先验值，不应直接作为最终设计或论文结论。正式统计建议增加随机种子并使用更长记录。

## 运行不规则波与生成 PSD

GUI 中加载上述场景，确认 readiness 通过后点击运行即可。命令行等价入口：

```powershell
.\scripts\06_run_scenario_file.ps1 `
  -Scenario .\scenarios\iea_15_240_umaine_y_morison_rectangular.json `
  -Workers 4 `
  -Resume `
  -Overwrite `
  -ContinueOnFail
```

`Resume` 会复用已经成功的 OpenFAST 输出，只补跑缺失或失败的 case。场景完成后，聚合 PSD 默认生成在：

```text
runs/iea_15_240_umaine_y_morison_rectangular/comparison/
  response_psd_aggregate.png
  response_psd_aggregate.pdf
  response_psd_aggregate.json
```

结果页也可以手动选择最多 6 个输出文件和 8 个通道，在指定时间窗内查看时程、统计量与 Welch PSD。

## HydroDyn/Morison 几何规则

- 圆柱构件由两端 `PropD` 生成等径圆柱或锥台。
- 矩形构件由两端 `PropA/PropB` 生成可渐变棱柱。
- `MSpinOrient` 按 HydroDyn v5 的构件轴右手规则解释。
- `PropThck` 参与有效性检查；首版不绘制空心内壁。
- `MDivSize` 图层显示 `ceil(构件长度 / MDivSize)` 的估算离散位置，不替代 OpenFAST `.HD.sum` 中的实际计算节点。
- 海床使用 `Z = -WtrDpth`，波向 `0°` 指向 `+X`、`90°` 指向 `+Y`。

前端几何诊断负责即时反馈，保存和运行前仍以后端 HydroDyn 校验为权威结果。

## 数据与运行安全

- GUI 只读取模型模板；所有输入修改应用到 `runs/<scenario>/<case>/` 中的副本。
- 不复制、移动或覆盖用户的原始模型目录。
- 场景保存使用 revision 检查；另一个标签页已更新同一场景时，旧页面的保存和运行请求会被拒绝，避免静默覆盖。
- 后端会拒绝场景模型、所选模型和 runtime 不一致的运行请求。
- `runs/`、`webui/assets/run_plots/`、本机路径配置、二进制和原始数据均由 `.gitignore` 排除。

## 场景与命令行

列出场景：

```powershell
python .\user_tools\run_scenario.py --list-scenarios
```

仅生成输入，不启动 OpenFAST：

```powershell
.\scripts\06_run_scenario_file.ps1 `
  -Scenario .\scenarios\iea_15_240_steady_wind.json `
  -GenerateOnly `
  -Overwrite
```

场景 JSON 支持：

- `model_id`、`runtime_id`
- 多 case 参数覆盖 `set`
- `hydrodyn_tables`
- `input_edits`、`input_file_overrides`
- `outlist_edits`
- `comparison`
- `response_psd`

更多示例和字段说明见 [scenarios/README.md](scenarios/README.md)。

## 仓库结构

```text
webui/        浏览器前端、HydroDyn 几何与 Three.js 查看器
user_tools/   本地 API、模型解析、场景运行、结果与 PSD 后处理
config/       公共模型/runtime profile；本机覆盖文件不提交
scenarios/    可复用场景 JSON
scripts/      PowerShell 启动与运行入口
docs/         模块插件与复现实验说明
runs/         本机生成的 case、OpenFAST 输出和图表，不提交
```

模块插件与数据流说明见 [docs/module_plugin_architecture.md](docs/module_plugin_architecture.md)。

## 开发与回归测试

运行全部 Python 测试：

```powershell
python -m unittest discover -s user_tools -p "test_*.py"
```

检查前端语法与 HydroDyn 几何：

```powershell
node --check .\webui\app.js
node --check .\webui\hydro_geometry.js
node --check .\webui\hydro_viewer.js
node --test .\webui\test_hydro_geometry.js
```

依赖真实模型模板的测试在模板缺失时会跳过；解析、readiness、v5 格式、场景并行和纯几何测试仍可独立运行。

## 项目状态

当前版本定位为本地工程研究工具，重点保证输入副本隔离、模型/runtime 一致性和 HydroDyn 几何可核对。用于设计认证、载荷定型或论文定量结论前，请结合官方 OpenFAST 文档、模型来源说明和独立验证结果进行复核。
