# OpenFAST GUI

本仓库是一个面向 FOCAL C4、IEA-15-240-RWT 及其它 OpenFAST 模型的本地可视化工作台。它提供模型依赖发现、模块插件编辑、场景 JSON、OutList、HydroDyn Morison/矩阵、通用结果、线性化模态、VTK 三维查看，以及 TurbSim、FAST.Farm 和模块 driver 接口。

## 目录

```text
webui/                    浏览器前端
user_tools/               本地服务、模块插件、场景运行器和后处理
work_c4/                  FOCAL C4 兼容修复与 OpenFAST 输入辅助函数
scenarios/                示例工况 JSON
scripts/                  PowerShell 快捷入口
bin/                      本机 OpenFAST 可执行文件目录，不提交
FOCAL_OpenFast_C4-main/   本机 FOCAL C4 模型模板目录，不提交
runs/                     生成的 case 和仿真输出，不提交
reports/                  本地报告和图，不提交
tool_inputs/              本地 TurbSim/FAST.Farm 输入，不提交
```

## 本机准备

1. 安装 Python 3.10+。
2. 安装依赖：

```powershell
pip install -r .\requirements.txt
```

3. 放置 OpenFAST 可执行文件：

```text
bin\openfast_x64.exe
```

也可以用环境变量覆盖：

```powershell
$env:OPENFAST_EXE = "D:\path\to\openfast_x64.exe"
```

4. 放置 FOCAL C4 模型模板，使主输入文件位于：

```text
FOCAL_OpenFast_C4-main\FOCAL_OpenFast_C4-main\FOCAL_C4.fst
```

也可以用环境变量覆盖模型模板位置：

```powershell
$env:FOCAL_C4_MODEL_TEMPLATE = "D:\path\to\FOCAL_OpenFast_C4-main"
```

本仓库默认不提交 OpenFAST exe、模型模板、实验数据和运行输出，避免 GitHub 仓库过大，也避免把本机二进制和结果误推上去。

## 启动网站

```powershell
.\scripts\08_start_ui.ps1
```

然后打开：

```text
http://127.0.0.1:8765
```

页面顶部可以选择模型模板和 OpenFAST runtime。当前配置包含：

- `FOCAL C4 semi-submersible` + `OpenFAST v4.0.0 bundled`
- `IEA-15-240-RWT UMaineSemi` + `OpenFAST 2026 dev build`

模型和 runtime 来自 [config/model_profiles.json](config/model_profiles.json)。换电脑或换安装路径时，可以复制一份本地覆盖配置到 `config/local_model_profiles.json`；该文件被 `.gitignore` 忽略，不会上传。

如果 8765 端口被占用：

```powershell
.\scripts\08_start_ui.ps1 -Port 8766
```

## 运行工况

列出场景：

```powershell
python .\user_tools\run_scenario.py --list-scenarios
```

只生成输入文件，不调用 OpenFAST：

```powershell
.\scripts\06_run_scenario_file.ps1 -Scenario .\scenarios\steady_wind.json -GenerateOnly -Overwrite
```

运行场景：

```powershell
.\scripts\06_run_scenario_file.ps1 -Scenario .\scenarios\steady_wind.json -Overwrite -ContinueOnFail
```

并行运行独立 case（默认仍为 1，GUI 中可选择 1-4）：

```powershell
.\scripts\06_run_scenario_file.ps1 -Scenario .\scenarios\focal_irregular_wave_compare.json -Workers 2 -Resume -Overwrite -ContinueOnFail
```

每个 case 使用独立运行目录。`Resume` 会复用已有的成功 summary 与 OpenFAST 输出，仅运行缺失或失败的 case。并行模式会在主进程中按场景顺序更新 `scenario_results.json`，全部 case 完成后再生成聚合图。单个 case 失败且未启用 `ContinueOnFail` 时，不再提交尚未启动的 case；已经启动的 worker 会正常收尾。

命令行指定 IEA-15-240 模型并只生成输入：

```powershell
.\scripts\06_run_scenario_file.ps1 `
  -Scenario .\scenarios\iea_15_240_steady_wind.json `
  -Model "D:\OpenFast\FOCAL_C4_clean_workspace\02_starting_model\best_reproducible_model\OpenFAST_input_files" `
  -OpenFastExe "D:\OpenFast\FOCAL_C4_clean_workspace\02_starting_model\best_reproducible_model\OpenFAST_input_files\OpenFAST_Release.exe" `
  -RuntimeFormat v5 `
  -Compatibility none `
  -Fst IEA-15-240-RWT-UMaineSemi.fst `
  -GenerateOnly `
  -Overwrite
```

手动覆盖常用参数：

```powershell
.\scripts\07_run_general_case.ps1 `
  -Name wind12p8_wave2m `
  -TMax 180 `
  -WindSpeed 12.8 `
  -WaveMod 1 `
  -WaveHs 2 `
  -WaveTp 10 `
  -Overwrite
```

## HydroDyn 编辑范围

当前 UI 支持：

- `AddCLin`、`AddBLin`、`AddBQuad` 三个 6x6 矩阵。
- `NAxCoef`、`NJoints`、`NPropSets`、`NCoefMembers`、`NMembers` 等数量字段与对应表格行同步维护。
- Morison 圆柱/矩形构件、节点、属性、simple/depth/member-based 系数表。
- 默认以 `MCoefMod=3` 新增构件，并自动补齐同 `MemberID` 的 member coefficient 行。
- v5 矩形构件可以编辑；只有原生 v5 HydroDyn 模板配合 v5 runtime 才允许写出，legacy/v4 模板会阻止运行。

## 模块编辑器

“模块编辑”页按插件识别 OpenFAST、InflowWind、SeaState、HydroDyn、MoorDyn/MAP、ElastoDyn、AeroDyn/OLAF、ServoDyn/ROSCO、BeamDyn、SubDyn、ExtPtfm、TurbSim 和 FAST.Farm。每个实际模型文件均提供：

- 按源文件 section 排列的类型化标量控件。
- 自动发现的带单位表格和 6x6 矩阵。
- 重复 key 与 YAML 的行号级格式保留写回。
- 未识别或需要增删行时的完整原文覆盖。
- 当前模块官方文档入口和关键参数预检。

结构化修改保存在 case 的 `input_edits`，完整原文保存在 `input_file_overrides`。runner 只对复制到 `runs/` 的输入应用修改，不写模型模板。插件架构和场景字段见 [docs/module_plugin_architecture.md](docs/module_plugin_architecture.md)。

## 模型结构与 OutList

“模型结构”页会从主 `.fst` 开始递归扫描引用文件，同时纳入模型 profile 中显式配置的文件，显示引用方向、字段、行号、缺失文件和每个文件的普通参数/OutList 数量。扫描只读取模型目录；外部路径会显示为依赖，但不会递归读取。

“输出通道”页按 case 维护各模块的 OutList。修改保存在场景中的 `outlist_edits`：

```json
{
  "outlist_edits": [
    {
      "file": "FOCAL_C4_HydroDyn.dat",
      "section": 0,
      "channels": ["HydroFxi", "HydroFyi", "HydroFzi"]
    }
  ]
}
```

runner 只在复制出的 `runs/<scenario>/<case>/` 目录内写回这些区块，并在 `scenario_summary.json` 的 `outlist_changes` 中记录修改。旧场景没有 `outlist_edits` 时行为不变。

## 结果工作台

“结果分析”页会扫描 `runs/` 下已有的 OpenFAST 主输出和模块输出，支持 ASCII `.out` 与二进制 `.outb`：

- 同时选择最多 6 个结果文件、8 个通道。
- 按时间窗读取数据，并将浏览器显示点数限制在 200-8000；统计量仍使用该时间窗的完整数据。
- 按单位分图显示时程，避免不同物理量共用错误的纵轴。
- 使用 Welch 方法计算 PSD。
- 输出最小值、最大值、均值、标准差、RMS、绝对极值、范围和样本数。
- 导出当前显示数据 CSV、图表 PNG，或通过打印保存 PDF。

大文件分析采用按通道读取，并限制单次原始数据量。超过限制时，界面会要求缩小时间窗或减少通道，不会尝试把整个结果文件发送到浏览器。

## 线性化与 VTK

“线性化 / VTK”页扫描 `runs/`：

- 读取 `.lin` 中的 A/B/C/D 矩阵，对 A 矩阵做特征值分析并显示频率、阻尼、稳定性和主导状态。
- 读取 ASCII legacy `.vtk`、ASCII XML `.vtp` 和 `.pvd` 清单，并使用仓库内置的 Three.js 三维查看器显示点、线和面。
- OpenFAST 的线性化可用“线性化设置”预设启用；VTK 可用“VTK 可视化输出”预设启用。

二进制或 appended-data VTP 仍应先通过 ParaView/VTK 转为 ASCII VTP，再由浏览器查看。

## TurbSim、FAST.Farm 与外部接口

“外部接口”页可以生成 TurbSim `.in` 和 FAST.Farm `.fstf` 基准输入、编辑原文、配置可执行文件并启动已安装的工具。外部工具路径保存在被 Git 忽略的 `config/local_tool_profiles.json`，也可通过以下环境变量提供：

- `TURBSIM_EXE`, `FASTFARM_EXE`
- `AERODYN_DRIVER_EXE`, `HYDRODYN_DRIVER_EXE`, `BEAMDYN_DRIVER_EXE`, `SUBDYN_DRIVER_EXE`
- `OPENFAST_LIBRARY`, `OPENFAST_SIMULINK_SFUNC`

仓库不附带这些 NREL 可执行文件。本机未配置某个工具时，GUI 会显示 `not-installed` 并禁止启动。已配置工具先在 `runs/external_tools/` 中建立独立运行副本，不直接向模型模板写输出。FAST.Farm 输入格式以[官方 v5 文档](https://openfast.readthedocs.io/en/main/source/user/fast.farm/InputFiles.html)为准；TurbSim 参考[官方用户指南入口](https://openfast.readthedocs.io/en/main/source/user/turbsim/index.html)。

## 开发检查

```powershell
python -m py_compile .\user_tools\module_plugins.py .\user_tools\openfast_input.py .\user_tools\results_workspace.py .\user_tools\linearization_workspace.py .\user_tools\visualization_workspace.py .\user_tools\tool_inputs.py .\user_tools\run_scenario.py .\user_tools\ui_server.py
python -m unittest .\user_tools\test_openfast_input.py .\user_tools\test_module_plugins.py .\user_tools\test_results_workspace.py .\user_tools\test_linearization_workspace.py .\user_tools\test_visualization_workspace.py .\user_tools\test_tool_inputs.py .\user_tools\test_hydrodyn_tables.py .\user_tools\test_focal_wave_plot.py .\user_tools\test_parallel_runner.py
```

模板模型缺失时，依赖真实 C4 模板的测试会自动跳过；纯解析和 v5 表头测试仍可运行。
