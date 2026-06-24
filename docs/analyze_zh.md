# `neb-helper analyze` YAML 教程

`analyze` 用来读取已经跑完或正在整理的 NEB 结果，生成能量曲线和 `result.txt`。它不判断具体反应机理，只回答几个通用问题：

```text
这条 band 有多少张 image？
最高点是哪张 image？
正向能垒是多少？
反向能垒是多少？
反应能是多少？
每张 image 的 path 坐标和相对能量是多少？
```

命令行方式仍然可用：

```powershell
neb-helper analyze D:\code\nebresult\example1
```

如果同一个结果要反复分析，或者需要固定输出目录、字体、DPI、是否写 xyz，推荐写成 YAML：

```powershell
neb-helper analyze analyze_result.yaml
```

也可以显式指定：

```powershell
neb-helper analyze --config analyze_result.yaml
```

仓库里有一个模板：

```powershell
examples\analyze\analyze_result.yaml
```

## 1. 最小配置：自动发现结果目录

如果一个目录里已经有 CP2K `.ener`，最小配置只需要：

```yaml
input:
  path: D:\code\nebresult\example1
```

运行：

```powershell
neb-helper analyze analyze_result.yaml
```

默认输出在结果目录旁边：

```text
D:\code\nebresult\example1\neb_result.png
D:\code\nebresult\example1\result.txt
```

目录自动发现的优先级是：

```text
1. .ener
2. .restart
3. .traj
```

如果目录中有 `.ener`，`analyze` 会优先使用它读取能量和 path 距离；结构会尝试从 replica xyz 或 restart 文件补充。

## 2. 推荐配置：输出到临时目录

为了避免覆盖原计算目录里的图和 summary，可以把输出写到单独目录：

```yaml
input:
  path: D:\code\nebresult\example1
  energy_unit: hartree
  relative: true

output:
  image: D:\tmp\example1_neb_result.png
  summary: D:\tmp\example1_result.txt

plot:
  smooth: true
  dpi: 600
  font: Times New Roman
```

字段含义：

```text
input.path         结果目录、.ener、.restart 或 .traj
input.energy_unit  输入能量单位；CP2K .ener 通常是 hartree
input.relative     是否把 image 0 平移为 0 eV
output.image       能量曲线图片路径
output.summary     result.txt 路径
plot.smooth        是否平滑曲线
plot.dpi           图片 DPI
plot.font          Matplotlib 字体
```

`result.txt` 会包含：

```text
source
forward_barrier_eV
reverse_barrier_eV
reaction_energy_eV
peak_image_index
image path_A energy_eV
```

## 3. 显式读取 CP2K `.ener`

如果你不想依赖目录自动发现，可以直接指定 `.ener`：

```yaml
input:
  energy_file: D:\calc\neb-r-0-1.ener
  image_count: 7
  line_index: -1
  energy_unit: hartree
  relative: true

output:
  image: D:\tmp\neb_result.png
  summary: D:\tmp\result.txt
```

说明：

```text
image_count  .ener 无法自动推断 image 数时手动指定
line_index   读取第几条 numeric line；-1 表示最后一条
```

CP2K `.ener` 通常是 Hartree。默认会转换成 eV，并以 image 0 为零点：

```text
energy_eV(image i) = (E_i - E_0) * 27.211386245988
```

如果你已经提前转成 eV：

```yaml
input:
  energy_file: D:\calc\neb_profile.ener
  energy_unit: ev
```

如果你想保留绝对能量：

```yaml
input:
  energy_file: D:\calc\neb-r-0-1.ener
  relative: false
```

## 4. `.ener + .restart`：同时读能量和结构

如果想把分析到的结构也写成多帧 xyz，推荐同时给 `.ener` 和 `.restart`：

```yaml
input:
  energy_file: D:\calc\neb-r-0-1.ener
  restart_file: D:\calc\neb.restart
  energy_unit: hartree
  relative: true

output:
  image: D:\tmp\neb_result.png
  summary: D:\tmp\result.txt
  write_xyz: true
  xyz: D:\tmp\neb_traj.xyz
```

运行后额外输出：

```text
D:\tmp\neb_traj.xyz
```

这个 xyz 适合后续检查最高点附近结构，或者继续配合 `slice` / `dimer` 做下一步处理。

## 5. replica xyz：用结构文件补充 path

如果你有每张 image 的 xyz，可以用 `xyz_glob` 指定：

```yaml
input:
  energy_file: D:\calc\neb-r-0-1.ener
  xyz_glob: "image_*.xyz"
  image_count: 7
  xyz_index: "-1"
```

`xyz_glob` 是相对于结果目录解析的。对于上面的例子，结果目录来自 `energy_file` 所在目录，也就是：

```text
D:\calc
```

因此实际匹配的是：

```text
D:\calc\image_*.xyz
```

`xyz_index: "-1"` 表示如果每个 xyz 是多帧文件，读取最后一帧。

## 6. ASE `.traj`

如果输入是 ASE optimizer / NEB trajectory：

```yaml
input:
  traj_file: D:\calc\neb_relax.traj
  images_per_band: 7
  band_index: -1
  relative: true
  mic: true

output:
  image: D:\tmp\traj_neb_result.png
  summary: D:\tmp\traj_result.txt
```

说明：

```text
images_per_band  每条 band 有多少张 image
band_index        读取第几条 band；-1 表示最后一条
mic               从结构计算 path 距离时是否使用最小镜像
```

如果 `.traj` 里只保存了一条 band，通常可以不写 `images_per_band`；如果保存了多轮优化过程，建议显式写出来。

## 7. 路径规则

YAML 中的普通路径相对于配置文件所在目录解析：

```text
analyze_result.yaml
neb_result/
  neb-r-0-1.ener
```

可以写：

```yaml
input:
  energy_file: neb_result/neb-r-0-1.ener
```

`xyz_glob` 是一个例外：它相对于结果目录解析，而不是相对于 YAML 文件目录。这样可以直接写：

```yaml
input:
  energy_file: D:\calc\neb-r-0-1.ener
  xyz_glob: "*Replica*.xyz"
```

而不需要写完整 glob 路径。

## 8. 常见问题

### 能垒看起来大了很多

先检查 `energy_unit`。CP2K `.ener` 通常是 Hartree，默认设置是：

```yaml
input:
  energy_unit: hartree
```

如果你的输入已经是 eV，必须改成：

```yaml
input:
  energy_unit: ev
```

### peak image 编号和可视化软件对不上

`neb-helper` 输出的 `peak_image_index` 是 0-based。`peak_image_index: 3` 对应第 4 张 image，也通常对应文件：

```text
image_003.xyz
```

### 不想覆盖原始结果

把输出路径写到临时目录：

```yaml
output:
  image: D:\tmp\neb_result.png
  summary: D:\tmp\result.txt
```

### 只想快速看图，不写 summary

```yaml
output:
  write_summary: false
```

### 想把结构导出给后续工具

需要有可读取的结构来源，例如 `.restart`、`.traj` 或 replica xyz，然后打开：

```yaml
output:
  write_xyz: true
  xyz: D:\tmp\neb_traj.xyz
```

## 9. 后续工作流

`analyze` 通常是结果整理的第一步。根据 `result.txt` 和能量曲线，你可以继续：

```text
最高点附近结构合理，但 band 太长：neb-helper slice
最高点附近有相邻 image 可用：neb-helper dimer
只有 IS/FS，已有路径不理想：neb-helper tsguess
```
