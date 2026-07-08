# FOCAL C4 model template

把 FOCAL C4 模型模板放在这里，并保持下面的嵌套结构：

```text
FOCAL_OpenFast_C4-main\FOCAL_OpenFast_C4-main\FOCAL_C4.fst
FOCAL_OpenFast_C4-main\FOCAL_OpenFast_C4-main\FOCAL_C4_HydroDyn.dat
FOCAL_OpenFast_C4-main\FOCAL_OpenFast_C4-main\FOCAL_C4_ElastoDyn.dat
```

运行器会在每个 case 启动前把这个模板完整复制到 `runs/<scenario>/<case>/`，然后只修改复制出的输入文件。

模型模板默认不提交到 GitHub。
