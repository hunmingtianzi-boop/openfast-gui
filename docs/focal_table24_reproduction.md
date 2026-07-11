# FOCAL Campaign 4 Table 24 不规则波复现

## 原始出处

截图中的 Table 24、Figure 25 和 Figure 26 来自：

Eben Lenfest and Matthew Fowler. *Floating Offshore Wind Controls Advanced Laboratory (FOCAL) Experimental Program - Campaign 4: 1:70 Model-Scale Test of the IEA-Wind 15MW Reference Turbine and VolturnUS-S Platform*. University of Maine Advanced Structures and Composites Center, Report No. 23-57-1183, 2023.

公开数据集为 [FOCAL Campaign IV: Integrated System Control: Turbine + Hull](https://wdh.energy.gov/ds/focal/focal.campaign4)，DOI `10.21947/1972267`。配套的同行评审论文为 Fowler et al., *Machines* 2023, 11, 865, DOI [`10.3390/machines11090865`](https://doi.org/10.3390/machines11090865)。

报告文件不随仓库提交，请从上述公开数据源获取。

## Table 24 参数

| Wave ID | 海况 | Hs (m) | Tp (s) | Gamma |
|---|---|---:|---:|---:|
| E11-E15 | operational sea state / DLC 1.2 | 3.1 | 8.96 | 1.80 |
| E21-E25 | 1-year extreme sea state / DLC 1.6 | 8.1 | 12.8 | 2.75 |

每组五个编号表示同一 JONSWAP 统计海况的五个随机实现。它们的时程不同，但 Hs、Tp、Gamma 和目标谱相同。

## 图的读法

上图是校准探头第 2 个测点的瞬时波面高程。`Hs` 不是最大波峰，而是有效波高；对近似平稳高斯海面可用 `Hs ~= 4 * std(eta)` 检查。

下图是波面高程功率谱密度，单位为 `m^2/Hz`。报告规定不规则波 PSD 使用 `2000-8000 s`。谱下面积是波面方差，因而 `4 * sqrt(integral(PSD df))` 应接近 Hs。谱峰应接近 `1/Tp`：E11-E15 约为 `0.1116 Hz`，E21-E25 约为 `0.0781 Hz`。

Surge、Pitch、Tower 竖线是系统模态频率，不是波浪参数。它们用于判断波能是否落在结构共振区。Figure 26 中 Tower 标记按图读取约为 `0.458 Hz`；同一报告 Table 16 对另一条明确列出的 floating fore-aft/fixed-TMD 条件给出 `0.406 Hz`，报告没有解释两者差异，因此 GUI 将模态线作为可追溯绘图配置，而不把它当作 Table 24 的海况参数。

## 两种复现

真实数据重画读取 Campaign 4 CSV；可通过 `FOCAL_C4_IRREGULAR_DATA`
环境变量指定实验数据目录。

运行：

```powershell
python .\user_tools\plot_irregular_wave_experiment.py --calibration-figures
```

OpenFAST 统计复现使用 `WaveMod=2`，并分别写入 `WaveHs`、`WaveTp`、`WavePkShp` 和五个不同的 `WaveSeed(1)`。这会得到统计意义相同的 JONSWAP 波，但不会恢复水池造波机的原始相位序列。若要让 OpenFAST 使用原始实验波面时程，需要把实验时程整理成 SeaState `WaveMod=5` 的外部波面文件。

GUI 的 DLC 页面提供 Table 24 生成器。它只生成场景 JSON，不自动运行；运行完成后可生成五种子时程和 PSD 聚合图。

E11-E15 与 E21-E25 的 case 可以并行计算。GUI 的“并行工况”默认值为 1，当前 32 GB 内存工作站建议设置为 2；聚合图仍会等待对应波组的 5 个 seed 全部成功完成后生成。
