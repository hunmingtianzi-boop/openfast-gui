# OpenFAST GUI

本仓库是一个面向 FOCAL C4 与 IEA-15-240-RWT 的本地 OpenFAST 可视化工况编辑器。它提供模型依赖发现、场景 JSON、常用 OpenFAST 参数、OutList 输出通道、HydroDyn 6x6 阻尼/刚度矩阵，以及 HydroDyn Morison 构件和系数表的编辑能力。

## 目录

```text
webui/                    浏览器前端
user_tools/               本地 HTTP 服务、场景运行器、HydroDyn 表格解析写回
work_c4/                  FOCAL C4 兼容修复与 OpenFAST 输入辅助函数
scenarios/                示例工况 JSON
scripts/                  PowerShell 快捷入口
bin/                      本机 OpenFAST 可执行文件目录，不提交
FOCAL_OpenFast_C4-main/   本机 FOCAL C4 模型模板目录，不提交
runs/                     生成的 case 和仿真输出，不提交
reports/                  本地报告和图，不提交
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
- Morison 圆柱构件的节点、属性、member-based 系数表。
- 默认以 `MCoefMod=3` 新增构件，并自动补齐同 `MemberID` 的 member coefficient 行。
- v5 矩形构件字段可被识别，但当前 OpenFAST v4 runtime 下会阻止运行。

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

## 开发检查

```powershell
python -m py_compile .\user_tools\openfast_input.py .\user_tools\results_workspace.py .\user_tools\hydrodyn_tables.py .\user_tools\run_scenario.py .\user_tools\ui_server.py .\work_c4\config.py .\work_c4\driver_c4.py
python -m unittest .\user_tools\test_openfast_input.py .\user_tools\test_results_workspace.py .\user_tools\test_hydrodyn_tables.py .\user_tools\test_focal_wave_plot.py .\user_tools\test_parallel_runner.py
```

模板模型缺失时，依赖真实 C4 模板的测试会自动跳过；纯解析和 v5 表头测试仍可运行。
