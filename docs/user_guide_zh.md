# neb-helper 完整功能手册

这份文档按功能模块系统介绍 `neb-helper` 当前已经实现的能力。快速上手请先看 [quickstart_zh.md](quickstart_zh.md)。

## 1. 总体结构

`neb-helper` 是一个 NEB 工作流工具箱，当前主要有四类命令：

```powershell
neb-helper make     # 从 initial/final 构造 NEB 初猜，可选 MLFF 预优化和 MLFF-NEB
neb-helper analyze  # 从已有 NEB 结果读取能量、画图、写 summary
neb-helper dimer    # 从已有 NEB image pair 生成 DIMER 初猜和 DIMER_VECTOR
neb-helper slice    # 从已有 NEB band 裁剪/重采样一段路径
```

Python 包结构大致是：

```text
neb_helper/
  make/      # 原 nebmake_v2：从端点构造路径
  result/    # 读取已有 NEB 结果并派生后续输入
  common/    # 共享几何、MIC、CP2K band 等基础工具
```

旧兼容入口仍然可用：

```powershell
nebmake-v2 config.yaml
neb-helper config.yaml   # 等价于 neb-helper make config.yaml
```

## 2. 安装和依赖

开发模式安装：

```powershell
cd D:\code\neb-helper
pip install -e .
```

基础依赖包括：

```text
ase
numpy
matplotlib
PyYAML
```

如果要用 MACE：

```powershell
pip install -e ".[ml]"
```

如果要用 DeepMD/DP，建议在你的 conda 环境中按 DeepMD 官方方式安装，因为 DeepMD 对 CUDA、Python、系统库版本比较敏感。

检查命令：

```powershell
neb-helper --version
neb-helper --help
neb-helper make --help
neb-helper analyze --help
neb-helper dimer --help
neb-helper slice --help
```

### 2.1 Python API / IDE 用法

`neb-helper` 不只是命令行工具，也可以作为普通 Python 包导入。推荐 IDE 用户先用 editable 安装：

```powershell
cd D:\code\neb-helper
pip install -e .
```

之后脚本里可以直接导入顶层 API：

```python
from neb_helper import analyze_neb, generate_dimer_guess, slice_band

_, summary = analyze_neb(
    input_path=r"D:\code\nebresult\example1",
    output_image=r"D:\tmp\neb_result.png",
    summary_path=r"D:\tmp\result.txt",
)
print(summary.forward_barrier)
```

也可以使用显式门面模块：

```python
from neb_helper.api import load_config, make_neb_path

spec = load_config(r"D:\path\to\nebmake.yaml")
result = make_neb_path(spec)
print(result["output_dir"])
```

当前稳定脚本入口包括：

```text
load_config
make_neb_path
analyze_neb
analyze_neb_files
generate_dimer_guess
slice_band
read_neb_energy
summarize_barrier
```

示例脚本在：

```text
examples/python_api/
```

## 3. 文件和编号约定

### 3.1 image 编号

默认所有原子编号和 image 编号都是 0-based：

```text
image_000.xyz -> 第 0 张 image
image_003.xyz -> 第 3 张 image，也就是第 4 张
atom index 0  -> 第 1 个原子
```

如果原子编号来自 GaussView 等 1-based 软件，可以在 `make` 配置里写：

```yaml
atom_indices_1_based: true
```

或在 `dimer` 命令里加：

```powershell
--atom-indices-1-based
```

### 3.2 结构兼容性

`make` 的 `initial` 和 `final` 要求：

```text
原子数相同
元素顺序相同
PBC flags 相同
cell 相同或足够接近
```

`dimer` 和 `slice` 读取已有 image 时，也会检查 image 之间是否兼容。

## 4. make：从端点构造 NEB 路径

`make` 是目前功能最多的模块，配置入口是 YAML 或 JSON：

```powershell
neb-helper make config.yaml
```

生成模板：

```powershell
neb-helper make --write-template nebmake.yaml
```

一个最小配置：

```yaml
initial: initial.cif
final: final.cif
n_images: 5

background:
  method: mic_linear
  idpp: true

output:
  directory: v2_output
```

`n_images` 是中间 image 数，不包含两个端点。`n_images: 5` 会输出 7 张结构：

```text
image_000.xyz ... image_006.xyz
```

### 4.1 make 配置总览

当前 `make` 支持这些顶层字段：

```yaml
initial: initial.cif
final: final.cif
n_images: 5
atom_indices_1_based: false
active_atoms: []
frozen_atoms: []
endpoint_reorder: {}
background: {}
waypoints: []
torsions: []
relax: {}
neb_relax: {}
dimer_vector: {}
pbc: {}
output: {}
```

下面逐块说明。

### 4.2 initial / final / n_images

```yaml
initial: reactant.cif
final: product.cif
n_images: 7
```

- `initial`：反应物端点结构，ASE 能读的格式通常都可以。
- `final`：产物端点结构。
- `n_images`：中间 image 数量，不包含端点。

如果端点原子顺序不同，不能直接 NEB。可以先用 `endpoint_reorder` 自动重排一端。

### 4.3 active_atoms / frozen_atoms

```yaml
active_atoms: [10, 12, 13, 48]
frozen_atoms: [0, 1, 2, 3, 4]
```

`active_atoms` 的用途：

- waypoint 默认用它定义反应中心。
- `relax.freeze_active: true` 时固定这些原子，只让环境响应。
- `dimer_vector.atoms: active` 时只输出这些原子的 DIMER_VECTOR 分量。

`frozen_atoms` 的用途：

- `relax` / `neb_relax` 中作为固定原子。
- `dimer_vector.zero_frozen_atoms: true` 时把这些原子的方向分量置零。

如果 `atom_indices_1_based: true`，也可以写字符串：

```yaml
atom_indices_1_based: true
active_atoms: "11,13,14,49"
frozen_atoms: "1-15,21-115"
```

### 4.4 endpoint_reorder：端点原子顺序校正

当 `initial` 和 `final` 的元素组成相同但原子顺序不同，可以启用：

```yaml
endpoint_reorder:
  enabled: true
  mode: final_by_initial
  output: v2_output/final_reordered.cif
  mapping: v2_output/final_reorder_mapping.csv
  copy_reference_cell: true
  max_distance: 1.0
  output_format:
```

字段说明：

```text
enabled              是否启用端点重排
mode                 final_by_initial 或 initial_by_final
output               写出重排后的结构；空值表示只在内存中用
mapping              写出 reference_index,target_index,symbol,distance_A
copy_reference_cell  是否把参考端点 cell/PBC 复制给目标端点
max_distance         匹配距离安全阈值，超过则报错
output_format        ASE 写出格式，空值时按后缀推断
```

常用模式是：

```yaml
mode: final_by_initial
```

表示以 `initial` 的原子顺序为准重排 `final`。

### 4.5 background：背景路径

```yaml
background:
  method: mic_linear
  idpp: true
```

当前支持：

```text
method: mic_linear    使用 MIC 位移做 Cartesian 线性插值
idpp: true            在背景路径上做 ASE IDPP 插值
```

注意：waypoints 和 torsions 会在背景路径之后覆盖相应原子或二面角控制。

### 4.6 waypoints：手摆中间结构控制点

waypoint 用于给路径增加人工控制点，尤其适合只手摆反应中心，不手摆整个骨架。

```yaml
active_atoms: [10, 12, 13, 48]

waypoints:
  - file: mid_active_atoms.xyz
    fraction: 0.5
    active_atoms_only: true
```

字段说明：

```text
file               waypoint 结构文件
image              指定 waypoint 对应哪张 image
fraction           指定 waypoint 在路径上的比例位置
atoms              为这个 waypoint 指定原子列表
active_atoms_only  true 表示只用 active atoms；false 表示 waypoint 是完整结构
```

`image` 和 `fraction` 二选一。都不写时，多个 waypoint 会均匀分布。

#### 4.6.1 只控制反应中心

```yaml
active_atoms: [10, 12, 13, 48]
waypoints:
  - file: mid_active_atoms.xyz
    image: 3
    active_atoms_only: true
```

`mid_active_atoms.xyz` 可以只包含 `active_atoms` 这些原子，顺序要和 `active_atoms` 列表一致。

#### 4.6.2 控制完整结构

```yaml
waypoints:
  - file: mid_full.xyz
    fraction: 0.5
    active_atoms_only: false
```

这会把 waypoint 当完整结构控制点。

### 4.7 torsions：二面角/单键旋转控制

对于单键旋转类路径，直接 Cartesian 插值可能很差，可以显式控制二面角。

```yaml
torsions:
  - name: rotate_fragment
    dihedral: [10, 12, 13, 48]
    rotating_group: [48, 49]
    start_deg: 30.0
    end_deg: 170.0
    apply_endpoints: false
```

字段说明：

```text
name             名称，仅用于标识
dihedral         ASE 二面角定义 [i, j, k, l]
rotating_group   跟着旋转的一侧 fragment 原子列表
start_deg        起点角度；不写则从 initial 读
end_deg          终点角度；不写则从 final 读
values_deg       手动给每张 image 的角度
apply_endpoints  是否也改端点；通常 false
```

`rotating_group` 必须包含 dihedral 的第 4 个原子 `l`，并且不要把键另一侧误放进去。

### 4.8 relax：逐张 image 预优化

`relax` 是对每张 image 独立做短程优化，不含 NEB 弹簧和切向投影。它适合让环境或骨架先响应手摆的反应中心。

```yaml
relax:
  enabled: true
  calculator:
    type: mace
    model: MACE/multihead_lora_replay_finetune.model
    head: zeo_reico_head
    device: cuda
    dtype: float32
    kwargs: {}
  steps: 100
  fmax: 0.2
  maxstep: 0.05
  optimizer: BFGS
  relax_endpoints: false
  freeze_active: true
  logfile: relax.log
  trajectory: relax.traj
  log_to_screen: true
```

字段说明：

```text
enabled          是否启用逐 image 预优化
calculator       ASE calculator 配置
steps            最大优化步数
fmax             收敛阈值
maxstep          optimizer 最大单步位移
optimizer        BFGS 或 FIRE
relax_endpoints  是否也优化端点；通常 false
freeze_active    是否固定 active_atoms 和 torsion 相关原子
logfile          优化日志文件名；空值不写
trajectory       优化轨迹文件名；空值不写
log_to_screen    是否在屏幕显示优化表格
```

常见用法是：

```yaml
freeze_active: true
```

让反应中心保持你手摆或 torsion 控制的路径，只让环境/骨架局部响应。

### 4.9 calculator：计算器配置

`relax.calculator` 和 `neb_relax.calculator` 共用同一套字段：

```yaml
calculator:
  type: mace
  model: path/to/model
  head:
  device: cuda
  dtype: float32
  kwargs: {}
```

支持的 `type`：

```text
none       不使用 calculator
emt        ASE 内置 EMT，测试用
lj         ASE 内置 Lennard-Jones，测试用
dp         DeepMD calculator
deepmd     DeepMD calculator
deepmd-kit DeepMD calculator
mace       MACE calculator
```

#### 4.9.1 MACE 示例

```yaml
calculator:
  type: mace
  model: MACE/multihead_lora_replay_finetune.model
  head: zeo_reico_head
  device: cuda
  dtype: float32
  kwargs: {}
```

也可以用 MACE foundation model 名称，例如：

```yaml
calculator:
  type: mace
  model: mace_mp
  device: cuda
  dtype: float32
```

#### 4.9.2 DeepMD / DP 示例

```yaml
calculator:
  type: dp
  model: DPA3/DPA3_finetune_zeo_iter011_reico_SiAlGaCHO_abacus_01.pth
  head: Omat24
  kwargs: {}
```

具体可用字段取决于当前环境的 `deepmd` calculator 接口。

### 4.10 neb_relax：真正的 MLFF-NEB 优化

`neb_relax` 会把整条 band 作为 NEB 优化，含弹簧、切向投影和可选 climbing image。

```yaml
neb_relax:
  enabled: true
  calculator:
    type: mace
    model: MACE/multihead_lora_replay_finetune.model
    head: zeo_reico_head
    device: cuda
    dtype: float32
    kwargs: {}
  force_evaluator: auto
  force_batch_size: 2
  steps: 200
  fmax: 0.5
  maxstep: 0.05
  optimizer: BFGS
  climb: true
  method: improvedtangent
  k: 0.1
  parallel: false
  remove_rotation_and_translation: false
  shared_calculator: auto
  freeze_active: false
  logfile: neb_relax.log
  trajectory: neb_relax.traj
  log_to_screen: true
  energy_log: neb_relax.ener
  write_image_trajectories: true
  image_trajectory_suffix: _neb_traj.xyz
  image_trajectory_format: extxyz
  write_current_outputs: true
  current_output_interval: 1
```

字段说明：

```text
enabled                          是否启用 MLFF-NEB
force_evaluator                  ase / auto / batch
force_batch_size                 批量取力 chunk 大小；空或 0 表示整条 band 一次送入
steps                            最大 NEB 优化步数
fmax                             收敛阈值
maxstep                          optimizer 最大单步位移
optimizer                        BFGS 或 FIRE
climb                            是否 climbing image
method                           ASE NEB method，例如 improvedtangent
k                                spring 常数
parallel                         ASE NEB parallel
remove_rotation_and_translation  是否去除整体平移/转动
shared_calculator                auto / true / false
freeze_active                    是否固定 active/torsion 原子
logfile                          NEB 优化日志
trajectory                       ASE optimizer trajectory
energy_log                       CP2K .ener 风格能量记录
write_image_trajectories         是否为每张 image 写 NEB 优化过程多帧轨迹
write_current_outputs            是否边优化边覆盖写出当前 image_*.xyz / band.txt
current_output_interval          live output 间隔
```

#### 4.10.1 force_evaluator

```yaml
force_evaluator: auto
```

推荐先用 `auto`：

```text
ase     ASE 默认逐 image 调 calculator，最稳但慢
auto    MACE/DeepMD 时尝试批量取力，不支持则回退 ASE
batch   强制批量取力；不支持时报错
```

如果 GPU 爆显存，减小：

```yaml
force_batch_size: 2
```

甚至：

```yaml
force_batch_size: 1
```

#### 4.10.2 live output

```yaml
write_current_outputs: true
current_output_interval: 1
```

开启后，NEB 优化过程中会定期覆盖输出当前可用的：

```text
image_000.xyz
image_001.xyz
...
neb_initial_path.xyz
band.txt
```

这适合长时间 MLFF-NEB：你可以边跑边打开当前结构，如果路径已经够好，可以停止后直接使用当前文件。

#### 4.10.3 image trajectory

```yaml
write_image_trajectories: true
image_trajectory_suffix: _neb_traj.xyz
image_trajectory_format: extxyz
```

会输出：

```text
image_000_neb_traj.xyz
image_001_neb_traj.xyz
...
```

用于检查每张 image 在 NEB 优化过程中的演化。

### 4.11 dimer_vector：从 make 生成的路径导出 CP2K DIMER_VECTOR

这是 `make` 流程里的可选功能，不同于 `neb-helper dimer` 命令。

```yaml
dimer_vector:
  enabled: true
  file: dimer_vector.inc
  image: auto
  atoms: active
  zero_frozen_atoms: true
  normalize: true
  scale: 1.0
```

字段说明：

```text
enabled            是否写 DIMER_VECTOR
file               输出文件名，相对 output.directory
image              auto / middle / max_energy / 0-based image index
atoms              active / all / 原子列表
zero_frozen_atoms  是否把 frozen_atoms 分量置零
normalize          是否归一化向量
scale              归一化后缩放
```

`image: auto` 的逻辑：

```text
如果 neb_relax.energy_log 存在，选最后一步能量最高的内部 image
否则选中间内部 image
```

注意：这个功能需要完整 image list，因为它用 `image-1` 和 `image+1` 取切向方向。不能选端点。

### 4.12 pbc：周期边界处理

```yaml
pbc:
  wrap_policy: never
  output_wrap: false
  fail_if_outside: false
  eps: 1.0e-12
  tol: 1.0e-8
```

字段说明：

```text
wrap_policy       never / always，内部是否主动 wrap
output_wrap       写给 CP2K 前是否强制 wrap 回 box
fail_if_outside   如果输出结构仍有原子在 box 外，是否报错
eps               wrap 到 [0, 1-eps]
tol               判断越界的容差
```

默认策略是保守保持路径连续：

```yaml
wrap_policy: never
output_wrap: false
```

如果你的 CP2K 输入严格要求坐标在主晶胞内，可以考虑：

```yaml
output_wrap: true
```

但要小心跨边界分子或片段被视觉上切开。

### 4.13 output：输出控制

```yaml
output:
  directory: v2_output
  images_prefix: image
  trajectory: neb_initial_path.xyz
  cp2k_band: band.txt
  diagnostics: diagnostics.csv
  write_vasp: false
  save_initial_guess: true
  initial_guess_directory: initial_guess
```

字段说明：

```text
directory                 输出目录
images_prefix             单张 image 文件名前缀
trajectory                多帧 xyz 路径；空值表示不写
cp2k_band                 CP2K &REPLICA 片段；空值表示不写
diagnostics               路径诊断 CSV；空值表示不写
write_vasp                是否同时写 00/POSCAR, 01/POSCAR ...
save_initial_guess        若启用 relax/neb_relax，是否保存优化前路径
initial_guess_directory   优化前路径保存目录
```

`diagnostics.csv` 包含：

```text
image
min_scaled_pbc
max_scaled_pbc
outside_box_before_output_wrap
max_mic_jump_from_previous
```

### 4.14 完整 make 示例：MACE 初猜 + MLFF-NEB

```yaml
initial: reactant.cif
final: product.cif
n_images: 7
atom_indices_1_based: false

active_atoms: [10, 12, 13, 48]
frozen_atoms: [0, 1, 2, 3, 4]

background:
  method: mic_linear
  idpp: true

relax:
  enabled: true
  calculator:
    type: mace
    model: MACE/multihead_lora_replay_finetune.model
    head: zeo_reico_head
    device: cuda
    dtype: float32
    kwargs: {}
  steps: 100
  fmax: 0.2
  maxstep: 0.05
  optimizer: BFGS
  relax_endpoints: false
  freeze_active: true
  log_to_screen: true

neb_relax:
  enabled: true
  calculator:
    type: mace
    model: MACE/multihead_lora_replay_finetune.model
    head: zeo_reico_head
    device: cuda
    dtype: float32
    kwargs: {}
  force_evaluator: auto
  force_batch_size: 2
  steps: 200
  fmax: 0.5
  maxstep: 0.05
  optimizer: BFGS
  climb: true
  method: improvedtangent
  k: 0.1
  shared_calculator: auto
  freeze_active: false
  energy_log: neb_relax.ener
  write_current_outputs: true
  current_output_interval: 1

dimer_vector:
  enabled: true
  file: dimer_vector.inc
  image: auto
  atoms: active
  zero_frozen_atoms: true
  normalize: true

output:
  directory: v2_output
  images_prefix: image
  trajectory: neb_initial_path.xyz
  cp2k_band: band.txt
  diagnostics: diagnostics.csv
  save_initial_guess: true
  initial_guess_directory: initial_guess
```

运行：

```powershell
neb-helper make config.yaml
```

## 5. analyze 命令：分析已有 NEB 结果

`analyze` 是从旧 `nebresult.py` 迁移来的通用分析流程。它读取已有 NEB 结果，输出能量曲线和 summary，适合先把一次 NEB 的主要数值整理清楚。

最常用方式是给一个结果目录：

```powershell
neb-helper analyze D:\code\nebresult\example1
```

如果目录中有 CP2K `.ener` 文件，会优先按 `.ener` 读取；如果没有 `.ener` 但有 `.restart` 或 `.traj`，会按对应格式自动发现。默认输出：

```text
D:\code\nebresult\example1\neb_result.png
D:\code\nebresult\example1\result.txt
```

`result.txt` 包含：

```text
source
forward_barrier_eV
reverse_barrier_eV
reaction_energy_eV
peak_image_index
image path_A energy_eV
```

注意：当前 `analyze` 做的是通用 NEB 结果汇总，不自动判断“哪一段是质子转移、哪一段是构象变化”。这些更高阶判断还需要结合具体体系。

### 输入来源

#### 目录自动发现

```powershell
neb-helper analyze D:\code\nebresult\example1
```

自动发现优先级是：

```text
.ener + 可选结构文件
.restart
.traj
```

#### 显式 CP2K .ener

```powershell
neb-helper analyze --energy-file D:\calc\neb-r-0-1.ener
```

CP2K `.ener` 通常是 Hartree，默认会转换成 eV 并平移到 image 0：

```text
energy_eV(image i) = (E_i - E_0) * 27.211386245988
```

如果 `.ener` 里既有能量又有相邻 image 的距离，`analyze` 会自动用这些距离生成 path 坐标。

#### .ener + .restart

```powershell
neb-helper analyze --energy-file D:\calc\neb-r-0-1.ener --restart-file D:\calc\neb.restart
```

这种方式会同时读取能量和最后一组 replica 结构。之后如果加 `--write-xyz`，可以把分析到的 image 结构写成多帧 xyz。

#### ASE .traj

```powershell
neb-helper analyze --traj-file D:\calc\neb_relax.traj --images-per-band 7
```

如果一个 `.traj` 里保存了多轮 band，需要指定或让程序推断每个 band 有多少张 image。`--band-index -1` 表示读取最后一个 band。

### 常用选项

```text
--energy-file PATH         显式指定 CP2K .ener
--restart-file PATH        显式指定 CP2K .restart
--traj-file PATH           显式指定 ASE .traj
--xyz-glob PATTERN         用 replica xyz 文件补充结构
--image-count N            .ener 无法自动推断 image 数时手动指定
--line-index N             读取 .ener 第几行，默认 -1 表示最后一行
--xyz-index INDEX          读取 xyz 的哪个 frame，默认 -1
--images-per-band N        .traj 每个 band 的 image 数
--band-index N             .traj 读取第几个 band，默认 -1
--energy-unit hartree|ev   输入能量单位，默认 hartree
--absolute-energy          保留绝对能量，不平移到 image 0
--no-mic                   从结构计算 path 距离时不用 MIC
--no-smooth                不平滑曲线
--output-image PATH        图像输出路径
--dpi N                    图像 DPI，默认 600
--font NAME                Matplotlib 字体，默认 Times New Roman
--no-summary               不写 result.txt
--summary PATH             summary 输出路径
--write-xyz                有结构时写出 neb_traj.xyz
--xyz-output PATH          配合 --write-xyz 指定结构输出路径
```

### 避免覆盖原结果

默认输出会写在输入旁边。如果你只是试跑，可以显式指定临时输出：

```powershell
neb-helper analyze D:\code\nebresult\example1 --output-image D:\tmp\neb_result.png --summary D:\tmp\result.txt
```

### 和 slice / dimer 的关系

`analyze` 先回答“这条路径的能量和峰值 image 是什么”。然后你再基于人工判断选择：

```text
slice：裁剪真正关心的路径段
dimer：从接近 TS 的 image pair 生成 DIMER 初猜
```
## 6. dimer 命令：从已有路径派生 DIMER 初猜

`neb-helper dimer` 不需要 make 配置文件，它直接读取已有 `image_*.xyz`。

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
```

输出：

```text
D:\code\nebresult\dimer_guess_001_002\ts_guess.xyz
D:\code\nebresult\dimer_guess_001_002\dimer_vector.inc
```

常用选项：

```text
--source PATH              已有 NEB image 目录
--prefix image             输入 image 前缀
--suffix .xyz              输入 image 后缀
--between LEFT RIGHT       用 LEFT -> RIGHT 定义方向
--fraction X               插值比例，可重复
--output-dir PATH          输出目录
--structure-name NAME      单 fraction 时的结构文件名
--vector-name NAME         单 fraction 时的 DIMER_VECTOR 文件名
--format xyz               ASE 写出格式
--atoms active|all|LIST    DIMER_VECTOR 保留哪些原子分量
--active-atoms LIST        active 原子列表
--frozen-atoms LIST        这些原子的向量分量置零
--atom-indices-1-based     原子列表按 1-based 解释
--no-zero-frozen-atoms     不自动置零 frozen atoms
--no-normalize             不归一化向量
--scale X                  归一化后缩放
```

### 6.1 多个 DIMER 初猜

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.25 --fraction 0.5 --fraction 0.75
```

输出文件名会带 fraction tag，避免覆盖。

### 6.2 只保留反应中心

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "10,12,13,48" --atoms active
```

### 6.3 保留所有原子

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --atoms all
```

## 7. slice 命令：裁剪和重采样已有路径

`slice` 直接读取已有 `image_*.xyz`，输出新的重编号 band。

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

输出：

```text
slice_000_003\image_000.xyz
slice_000_003\image_001.xyz
slice_000_003\image_002.xyz
slice_000_003\image_003.xyz
slice_000_003\band.txt
slice_000_003\neb_sliced_path.xyz
slice_000_003\source_map.csv
```

常用选项：

```text
--source PATH              已有 NEB image 目录
--prefix image             输入 image 前缀
--suffix .xyz              输入 image 后缀
--range START END          inclusive image 范围，可反向
--output-dir PATH          输出目录
--output-prefix image      输出 image 前缀
--format xyz               ASE 写出格式
--resample-n-images N      重采样后的中间 image 数量
--trajectory NAME          多帧轨迹文件名；空字符串禁用
--band-file NAME           CP2K band 文件名；空字符串禁用
--source-map NAME          source map 文件名；空字符串禁用
```

### 7.1 裁剪 0-3

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

### 7.2 把 0-3 重采样为 7 个中间 image

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

总输出 image 数是 `7 + 2 = 9`。

### 7.3 反向路径

```powershell
neb-helper slice --source D:\code\nebresult --range 3 0
```

## 8. 当前质子转移案例如何使用

如果你判断：

```text
0-3 是真正质子转移
3 之后主要是构象变化
```

可选路线：

### 8.1 DIMER 路线

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "你的反应中心原子" --atoms active
```

再用 `ts_guess.xyz` 和 `dimer_vector.inc` 准备 CP2K DIMER。

### 8.2 NEB 裁剪路线

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

如果需要更多 image：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

然后你可以考虑把 `image_003` 附近做几何优化和频率确认，再把确认后的结构作为新的 product 端点。

## 9. 常见错误和处理

### 9.1 找不到 image 文件

检查命名是否是：

```text
image_000.xyz
image_001.xyz
```

如果不是，用：

```powershell
--prefix your_prefix --suffix your_suffix
```

### 9.2 原子数或顺序不一致

`make` 里用 `endpoint_reorder` 解决端点顺序问题。`dimer` / `slice` 要求已有 image 已经是一条兼容路径，不能自动重排中间 image。

### 9.3 MACE / DeepMD 导入失败

说明当前 Python 环境没有装对应包，或 CUDA/依赖不匹配。先确认：

```powershell
python -c "import mace"
python -c "import deepmd"
```

### 9.4 GPU 显存不足

对 `neb_relax` 调小：

```yaml
force_batch_size: 2
```

或：

```yaml
force_batch_size: 1
```

也可以临时用：

```yaml
force_evaluator: ase
```

牺牲速度换稳定性。

### 9.5 DIMER_VECTOR 是零向量

可能是：

```text
active_atoms 没有设置
active_atoms 选错
选中的原子在 LEFT/RIGHT 之间几乎不动
frozen_atoms 把所有 selected atoms 都置零了
```

可先试：

```powershell
--atoms all
```

确认不是结构本身问题。

## 10. 现在暂缓的功能

暂时不把 `analyze` 和 `endpoint` 做成正式命令。原因是它们需要把化学判断编码进工具，例如：

```text
哪些键长代表反应进程
哪些 CV 适合当前反应
哪些构象变化应忽略
某张 image 是否可以作为新端点
```

这些还需要更多案例沉淀。当前更稳妥的是先用已有通用功能：

```text
slice：裁剪出你认为可信的路径段
dimer：从你认为接近 TS 的 image pair 派生 DIMER 初猜
```
