# neb-helper 快速教程

这份教程帮助你快速理解 `neb-helper` 现在能做什么，以及在一个已有 NEB 结果基础上怎么继续推进。完整字段和高级功能说明见 [user_guide_zh.md](user_guide_zh.md)。

## 1. 工具定位

`neb-helper` 现在分成两层：

- `make`：从 `initial` / `final` 两个端点出发，构造 NEB 初猜。它基本继承原来的 `nebmake_v2`。
- `result`：读取已经跑出来的 NEB 结果，或从已有结构信息派生后续 TS/DIMER 工作流。目前已经实现 `analyze`、`dimer`、`slice` 和 `tsguess`。

也就是说：

```text
从端点造路径：neb-helper make
从已有结果汇总能垒：neb-helper analyze
从 IS/FS 端点直接生成 TS/DIMER 初猜：neb-helper tsguess
从已有路径派生下一步：neb-helper dimer / slice
```

所有 image 编号默认都是 Python/ASE 风格的 0-based index。`image_003` 就是第 4 张 image。

## 2. 安装

在仓库根目录执行：

```powershell
cd D:\code\neb-helper
pip install -e .
```

安装后检查命令是否可用：

```powershell
neb-helper --version
neb-helper --help
```

如果只想临时从源码运行，也可以先不安装，用当前 Python 环境把 `src` 加进 `PYTHONPATH`，但日常开发建议使用 `pip install -e .`。

## 3. 常用命令总览

```powershell
neb-helper make config.yaml
neb-helper analyze D:\code\nebresult\example1
neb-helper tsguess examples\tsguess\sc_dmf_c2h4.yaml
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
neb-helper dimer examples\dimer\dimer_guess.yaml
neb-helper slice --source D:\code\nebresult --range 0 3
```

兼容旧入口：

```powershell
nebmake-v2 config.yaml
neb-helper config.yaml
```

其中 `neb-helper config.yaml` 会自动等价于 `neb-helper make config.yaml`。

### Python API：在 IDE 中使用

安装后也可以完全不走命令行，直接在 Python 脚本里导入：

```python
from neb_helper import analyze_neb, generate_dimer_guess, generate_ts_guess, slice_band

_, summary = analyze_neb(
    input_path=r"D:\code\nebresult\example1",
    output_image=r"D:\tmp\neb_result.png",
    summary_path=r"D:\tmp\result.txt",
)
print(summary.forward_barrier)
```

如果你更喜欢显式的 API 入口，也可以写：

```python
from neb_helper.api import load_config, make_neb_path, load_ts_guess_config
```

仓库里有可直接改路径运行的脚本模板：

```text
examples/python_api/analyze_result.py
examples/python_api/dimer_guess.py
examples/python_api/ts_guess.py
examples/python_api/slice_band.py
examples/python_api/make_from_config.py
```

## 4. make：从端点构造 NEB 初猜

先生成一个模板配置：

```powershell
neb-helper make --write-template nebmake.yaml
```

如果想看完整字段示例，可以参考：

```text
examples/make/nebmake_v2_example.yaml
```

这份文件来自旧 `nebmake`，适合当作配置字典和注释参考；它不是自包含算例，运行前要替换 `initial`、`final`、原子编号和模型路径。

最小配置大概长这样：

```yaml
initial: initial.cif
final: final.cif
n_images: 5

background:
  method: mic_linear
  idpp: true

dimer_vector:
  enabled: false

output:
  directory: v2_output
  images_prefix: image
  trajectory: neb_initial_path.xyz
  cp2k_band: band.txt
```

运行：

```powershell
neb-helper make nebmake.yaml
```

典型输出：

```text
v2_output\image_000.xyz
v2_output\image_001.xyz
...
v2_output\band.txt
v2_output\neb_initial_path.xyz
v2_output\diagnostics.csv
```

`band.txt` 是 CP2K `&BAND` 里可用的 `&REPLICA` 片段。你仍然需要把它放进自己的 CP2K 输入文件框架里。

## 5. analyze：分析已有 NEB 结果

`analyze` 是从旧 `nebresult.py` 迁移来的通用结果分析命令。它负责读已有 NEB 结果、画能量曲线、写 summary，不做化学反应类型的自动判断。

最常用方式是给一个结果目录：

```powershell
neb-helper analyze D:\code\nebresult\example1
```

如果目录里有 `.ener` 文件，它会优先按 CP2K `.ener` 读取。默认输出：

```text
D:\code\nebresult\example1\neb_result.png
D:\code\nebresult\example1\result.txt
```

`result.txt` 会包含：

```text
forward_barrier_eV
reverse_barrier_eV
reaction_energy_eV
peak_image_index
每张 image 的 path_A 和 energy_eV
```

也可以显式指定文件：

```powershell
neb-helper analyze --energy-file D:\calc\neb-r-0-1.ener
neb-helper analyze --energy-file D:\calc\neb-r-0-1.ener --restart-file D:\calc\neb.restart
neb-helper analyze --traj-file D:\calc\neb_relax.traj --images-per-band 7
```

如果同一个结果目录要反复分析，推荐写成 YAML：

```powershell
neb-helper analyze analyze_result.yaml
```

示例：

```yaml
input:
  path: D:\code\nebresult\example1
  # energy_file: neb-r-0-1.ener
  # restart_file: neb.restart
  # traj_file: neb_relax.traj
  # xyz_glob: "*Replica*.xyz"
  energy_unit: hartree
  relative: true

output:
  image: D:\tmp\neb_result.png
  summary: D:\tmp\result.txt
  write_xyz: false

plot:
  smooth: true
  dpi: 600
  font: Times New Roman
```

YAML 里的普通路径相对于配置文件所在目录解析；`xyz_glob` 相对于结果目录解析。

更完整的 CP2K `.ener`、`.restart`、ASE `.traj` 和常见问题说明见 [analyze YAML 教程](analyze_zh.md)。

如果只想写到临时目录，避免覆盖原结果：

```powershell
neb-helper analyze D:\code\nebresult\example1 --output-image D:\tmp\neb_result.png --summary D:\tmp\result.txt
```

常用选项：

```text
--energy-file PATH         显式指定 CP2K .ener
--restart-file PATH        显式指定 CP2K .restart，用于读取结构
--traj-file PATH           显式指定 ASE .traj
--image-count N            .ener 无法自动推断 image 数时手动指定
--line-index N             读取 .ener 第几行，默认 -1 表示最后一行
--energy-unit hartree|ev   输入能量单位，CP2K .ener 通常是 hartree
--absolute-energy          不把能量平移到 image 0
--no-smooth                不平滑曲线
--output-image PATH        图像输出路径
--summary PATH             summary 输出路径
--write-xyz                有结构时额外写 neb_traj.xyz
```

## 6. tsguess：从 IS/FS 端点生成 TS/DIMER 初猜

`tsguess` 适合这样的情况：你已经有可靠的 reactant/product 端点，但直接线性插值会产生坏键，或者金属/酸位点强吸附导致 DIMER 初猜容易滑回反应物侧。它会从 IS/FS 生成一组候选 TS 结构，并可选地写出 CP2K `&DIMER_VECTOR`。

典型运行方式只有一个 YAML：

```powershell
neb-helper tsguess examples\tsguess\sc_dmf_c2h4.yaml
```

仓库里的 `examples\tsguess\sc_dmf_c2h4.yaml` 是配置模板。真实 Sc/u-Sc CIF 不随仓库提交；运行前需要把 `initial` / `final` 改成你自己的端点结构，或把对应 CIF 放在 YAML 同目录。

配置文件至少需要这些信息：

```yaml
initial: Sc_DMF_C2H4_IS-1.cif
final: Sc_DMF_C2H4_FS-1.cif

atom_indices_1_based: true
active_atoms: "577-598"

path:
  method: active_idpp
  base: initial
  fractions: [0.70, 0.75, 0.78, 0.80]

reaction_coordinates:
  forming_bonds:
    - [578, 594]
    - [581, 593]
  weakening_bonds:
    - [577, 582]

selection:
  prefer_fraction: 0.75
  forming_range: [2.10, 2.45]
  weakening_min: 3.0

dimer_vector:
  enabled: true
  source: local_tangent
  tangent_fractions: [0.70, 0.78]
  atoms: active
  remove_translation: active
```

这些字段的含义是：

```text
initial/final             IS/FS 端点结构，原子数和原子顺序必须一致
atom_indices_1_based      原子编号是否按 GaussView/VESTA 常见的 1-based 解释
active_atoms              只移动和检查的反应中心区域
path.fractions            要生成候选结构的反应进度
path.base                 非 active 原子来自 initial、final 或 linear 背景
forming_bonds             希望在 TS 附近正在形成的键
weakening_bonds           希望在 TS 附近已经削弱的键
selection                 如何给候选结构打分并推荐一个 fraction
dimer_vector              如何从候选路径局部切线生成 CP2K DIMER_VECTOR
```

默认输出在 `candidate_outputs.directory` 指定的目录里，例如：

```text
tsguess_outputs\ts_guess_t0p700.cif
tsguess_outputs\ts_guess_t0p750.cif
tsguess_outputs\ts_guess_recommended_t0p750.cif
tsguess_outputs\metrics.csv
tsguess_outputs\notes.md
tsguess_outputs\dimer_vector.inc
tsguess_outputs\dimer_direction_check_minus_center_plus.xyz
```

推荐的检查顺序：

1. 打开 `metrics.csv`，确认 forming / weakening 距离是否符合预期。
2. 打开 `ts_guess_recommended_*.cif`，检查结构本身有没有坏键、穿插或不合理近接。
3. 打开 `dimer_direction_check_minus_center_plus.xyz`，看 `minus -> center -> plus` 是否沿反应坐标变化。
4. 把推荐结构和 `dimer_vector.inc` 放入 CP2K DIMER 输入，先跑一个短计算检查前几十步趋势。

`check.amplitude` 只影响 `minus-center-plus.xyz` 的可视化位移大小，不影响推荐结构，也不改变写入 CP2K 的 `DIMER_VECTOR`。大体系里如果方向看不清，可以把它从 `0.1` 调到 `0.5` 或 `1.0`。

如果 `minus -> plus` 看起来和你习惯的 IS -> FS 方向相反，通常不影响 DIMER 搜索，因为 `v` 和 `-v` 是同一条方向轴。只有在你想让可视化标签更直观时，才需要把：

```yaml
tangent_fractions: [0.70, 0.78]
```

改成：

```yaml
tangent_fractions: [0.78, 0.70]
```

### Python API：运行 tsguess

```python
from neb_helper import generate_ts_guess

result = generate_ts_guess(r"D:\code\neb-helper\examples\tsguess\sc_dmf_c2h4.yaml")

print(result.recommended_fraction)
print(result.recommended_structure)
print(result.metrics_path)
print(result.dimer_vector_path)
print(result.check_path)
```

也可以先显式读取配置：

```python
from neb_helper import generate_ts_guess, load_ts_guess_config

spec = load_ts_guess_config(r"D:\path\to\tsguess.yaml")
result = generate_ts_guess(spec)
```

## 7. dimer：从已有 image pair 生成 DIMER 初猜

当你已经有一条 NEB 路径，并判断鞍点大概在两张 image 之间，可以用 `dimer` 生成：

- DIMER 初始结构 `ts_guess.xyz`
- CP2K `&DIMER_VECTOR` 片段 `dimer_vector.inc`

例如鞍点大概在 `image_001` 和 `image_002` 中间：

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
```

如果命令行参数较多，也可以把同样的信息放进 YAML：

```powershell
neb-helper dimer examples\dimer\dimer_guess.yaml
```

最小 YAML 形态：

```yaml
source: ./neb_path
between: [1, 2]
fraction: 0.5

atom_indices_1_based: true
active_atoms: "577-598"
atoms: active
```

默认读取：

```text
D:\code\nebresult\image_000.xyz
D:\code\nebresult\image_001.xyz
D:\code\nebresult\image_002.xyz
...
```

默认写出：

```text
D:\code\nebresult\dimer_guess_001_002\ts_guess.xyz
D:\code\nebresult\dimer_guess_001_002\dimer_vector.inc
```

如果不确定鞍点在 pair 中的哪个位置，可以一次生成多个初猜：

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.25 --fraction 0.5 --fraction 0.75
```

这会生成类似：

```text
ts_guess_f0p250.xyz
dimer_vector_f0p250.inc
ts_guess_f0p500.xyz
dimer_vector_f0p500.inc
ts_guess_f0p750.xyz
dimer_vector_f0p750.inc
```

### 只保留反应中心方向

对大体系，DIMER_VECTOR 不一定应该包含所有原子。可以只保留 `active_atoms`：

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "10,12,13,48" --atoms active
```

如果你的原子编号来自 GaussView 等 1-based 界面，加上：

```powershell
--atom-indices-1-based
```

### dimer 常用选项

```text
--source PATH              已有 NEB image 所在目录
--between LEFT RIGHT       用 LEFT -> RIGHT 两张 image 定义方向
--fraction X               在 LEFT 和 RIGHT 之间插值，默认 0.5，可重复
--atoms active|all|LIST    DIMER_VECTOR 保留哪些原子分量
--active-atoms LIST        --atoms active 时使用的原子列表
--frozen-atoms LIST        这些原子的方向分量置零
--no-normalize             不归一化 DIMER_VECTOR
--output-dir PATH          指定输出目录
```

## 8. slice：裁剪已有 NEB 路径

如果一条 NEB 里只有某一段是你真正关心的反应过程，可以把这一段裁出来，重新编号，生成新的 CP2K-ready band。

例如你判断 `image_000` 到 `image_003` 是真正的质子转移过程，`image_003` 之后主要是构象变化：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

默认输出：

```text
D:\code\nebresult\slice_000_003\image_000.xyz
D:\code\nebresult\slice_000_003\image_001.xyz
D:\code\nebresult\slice_000_003\image_002.xyz
D:\code\nebresult\slice_000_003\image_003.xyz
D:\code\nebresult\slice_000_003\band.txt
D:\code\nebresult\slice_000_003\neb_sliced_path.xyz
D:\code\nebresult\slice_000_003\source_map.csv
```

`source_map.csv` 会记录新 image 对应旧路径中的哪个位置，方便检查重采样来源。

### 重采样裁剪段

如果想把 `0-3` 这一段重新加密，比如生成 7 个中间 image：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

注意：这里的 `--resample-n-images 7` 指 7 个中间 image，不含端点，所以总共会输出 9 张：

```text
image_000.xyz ... image_008.xyz
```

重采样不是简单拿首尾端点直线插值，而是沿旧路径累计 MIC 距离做分段线性插值，因此会尽量保留旧路径形状。

### 反向裁剪

如果要反过来用 product 到 reactant 的方向：

```powershell
neb-helper slice --source D:\code\nebresult --range 3 0
```

## 9. 当前质子转移案例的推荐用法

你的当前判断是：

```text
image_000 - image_003：感兴趣的质子转移过程
image_003 之后：大概率是质子转移后的构象变化
```

先用 `analyze` 保存一份通用能量汇总：

```powershell
neb-helper analyze D:\code\nebresult
```

然后可以分两条路线推进。

### 路线 A：如果已有可靠 IS/FS，直接生成 TS/DIMER 初猜

如果你已经有明确的 IS/FS 端点，且知道关键成键/断键编号，可以先写一个 `tsguess.yaml`：

```powershell
neb-helper tsguess tsguess.yaml
```

然后检查输出的：

```text
ts_guess_recommended_*.cif
metrics.csv
dimer_vector.inc
dimer_direction_check_minus_center_plus.xyz
```

这条路线适合直接从端点准备 DIMER 计算，不依赖已有 NEB image pair。

### 路线 B：从已有 NEB image pair 改用 DIMER

如果你认为 TS 大概在 `image_001` 和 `image_002` 之间：

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "你的反应中心原子" --atoms active
```

然后用输出的：

```text
ts_guess.xyz
dimer_vector.inc
```

去准备 CP2K DIMER 计算。

### 路线 C：继续做 NEB，但裁剪路径

先裁出真正关心的段：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

如果需要更密的初猜：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

这里要注意：`image_003` 是否能直接当新 product 端点，需要你后续用几何优化和频率确认。`neb-helper slice` 只负责生成候选路径，不替你判断它是不是稳定极小点。

## 10. 文件命名约定

默认输入 image 文件名：

```text
image_000.xyz
image_001.xyz
image_002.xyz
```

如果你的前缀或后缀不同，可以指定：

```powershell
neb-helper slice --source D:\code\nebresult --prefix replica --suffix xyz --range 0 3
neb-helper dimer --source D:\code\nebresult --prefix replica --suffix xyz --between 1 2
```

## 11. 常见问题

### 找不到 image 文件

确认目录里是否真的是 `image_000.xyz` 这种命名。必要时用 `--prefix` 和 `--suffix`。

### 原子数、元素顺序或 PBC 不一致

`dimer` 和 `slice` 会检查 image 是否兼容。它们要求同一条路径里的 image 有相同原子数、元素顺序、PBC；有 PBC 时还要求 cell 一致。

### DIMER_VECTOR 变成零向量

常见原因是 `--atoms active` 但没有给 `--active-atoms`，或者 active atoms 在两张 image 之间没有位移。可以试：

```powershell
--atoms all
```

或者重新检查 active atom 列表。

### 1-based 和 0-based 混淆

默认是 0-based。来自 GaussView 的编号通常是 1-based，需要加：

```powershell
--atom-indices-1-based
```

## 12. 现在还不建议自动化的部分

`analyze` 目前已经迁移了通用能量曲线和 summary。仍然暂缓的是更强的化学诊断层，例如：

```text
自动识别质子转移 CV
自动判断哪些键长需要画出来
自动区分反应坐标变化和构象松弛
自动从某张 image 生成 endpoint candidate 并判定它是否该作为新端点
```

这些判断目前仍然比较 case by case。更稳妥的做法是先用当前工具把人工判断后的步骤做扎实：

```text
analyze：整理能量、路径长度、峰值 image
slice：裁剪出真正关心的路径段
dimer：从可疑 TS 区间生成 DIMER 初猜
```
