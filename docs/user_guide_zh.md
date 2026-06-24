# neb-helper 完整功能手册

这份文档按功能模块系统介绍 `neb-helper` 当前已经实现的能力。快速上手请先看 [quickstart_zh.md](quickstart_zh.md)。

## 1. 总体结构

`neb-helper` 是一个 NEB 工作流工具箱，当前主要有五类命令：

```powershell
neb-helper make     # 从 initial/final 构造 NEB 初猜，可选 MLFF 预优化和 MLFF-NEB
neb-helper analyze  # 从已有 NEB 结果读取能量、画图、写 summary
neb-helper tsguess  # 从 IS/FS 端点生成 TS 候选结构和 DIMER_VECTOR
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
neb-helper tsguess --help
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
from neb_helper import analyze_neb, generate_dimer_guess, generate_ts_guess, slice_band

_, summary = analyze_neb(
    input_path=r"D:\code\nebresult\example1",
    output_image=r"D:\tmp\neb_result.png",
    summary_path=r"D:\tmp\result.txt",
)
print(summary.forward_barrier)
```

也可以使用显式门面模块：

```python
from neb_helper.api import load_config, make_neb_path, load_ts_guess_config

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
generate_dimer_guess_from_config
load_dimer_guess_config
generate_ts_guess
load_ts_guess_config
slice_band
read_neb_energy
summarize_barrier
```

常见返回对象包括：

```text
DimerGuessResult    dimer 输出目录、选中原子、结构文件和 DIMER_VECTOR 文件列表
TsGuessResult       tsguess 推荐 fraction、推荐结构、metrics、notes、DIMER_VECTOR、方向检查轨迹
SliceBandResult     slice 输出目录、band 文件、轨迹文件、source map
BarrierSummary      analyze 的 forward/reverse barrier、reaction energy、peak image
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

`tsguess` 读取 IS/FS 端点时也要求同样兼容。`dimer` 和 `slice` 读取已有 image 时，也会检查 image 之间是否兼容。

## 4. make：从端点构造 NEB 路径

`make` 是目前功能最多的模块，配置入口是 YAML 或 JSON：

```powershell
neb-helper make config.yaml
```

生成模板：

```powershell
neb-helper make --write-template nebmake.yaml


完整字段参考配置：

```text
examples/make/nebmake_v2_example.yaml
```

这份 YAML 从旧 `nebmake` 迁移而来，保留了大量注释，适合查字段含义和真实配置形态。它引用的是示例结构名和模型路径，不是自包含可直接运行的算例。

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

### YAML 配置文件

命令行参数较多时，推荐把 `analyze` 写成 YAML。这样同一个结果目录可以重复分析，也方便记录你当时使用的能量单位、输出路径和绘图设置。

运行：

```powershell
neb-helper analyze analyze_result.yaml
```

也可以显式指定：

```powershell
neb-helper analyze --config analyze_result.yaml
```

最小配置：

```yaml
input:
  path: D:\code\nebresult\example1
```

更常用的配置是显式写输出位置，避免覆盖原计算目录：

```yaml
input:
  path: D:\code\nebresult\example1
  energy_unit: hartree
  relative: true

output:
  image: D:\tmp\example1_neb_result.png
  summary: D:\tmp\example1_result.txt
  write_xyz: false

plot:
  smooth: true
  dpi: 600
  font: Times New Roman
```

如果要显式读取 CP2K `.ener` 和 `.restart`：

```yaml
input:
  energy_file: D:\calc\neb-r-0-1.ener
  restart_file: D:\calc\neb.restart
  image_count: 7
  line_index: -1
  energy_unit: hartree
  relative: true

output:
  image: D:\tmp\neb_result.png
  summary: D:\tmp\result.txt
  write_xyz: true
  xyz: D:\tmp\neb_traj.xyz
```

如果输入是 ASE `.traj`：

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

常用字段：

```text
input.path              结果目录、.ener、.restart 或 .traj
input.energy_file       显式 CP2K .ener
input.restart_file      显式 CP2K .restart
input.traj_file         显式 ASE .traj
input.xyz_glob          replica xyz glob；相对于结果目录解析
input.image_count       .ener 无法自动推断 image 数时手动指定
input.line_index        读取 .ener 第几条 numeric line
input.energy_unit       hartree 或 ev
input.relative          是否平移到 image 0
input.images_per_band   .traj 每条 band 的 image 数
input.band_index        .traj 读取第几条 band
input.mic               从结构计算 path 时是否使用 MIC
plot.smooth             是否平滑曲线
plot.dpi                图片 DPI
plot.font               Matplotlib 字体
output.image            图片输出路径
output.summary          result.txt 输出路径
output.write_summary    是否写 result.txt
output.write_xyz        是否写结构轨迹
output.xyz              结构轨迹输出路径
```

YAML 中的普通路径相对于配置文件所在目录解析。`xyz_glob` 是例外：它相对于结果目录解析，例如 `energy_file: D:\calc\neb-r-0-1.ener` 搭配 `xyz_glob: "*Replica*.xyz"` 会匹配 `D:\calc\*Replica*.xyz`。

更完整的教程和常见问题见 [analyze YAML 教程](analyze_zh.md)。

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
## 6. tsguess 命令：从 IS/FS 端点生成 TS/DIMER 初猜

`neb-helper tsguess` 用于从同一反应的 IS/FS 端点直接生成一组 TS 候选结构，并可选生成 CP2K `&DIMER_VECTOR`。它不是 TS 优化器，也不替代频率验证；它的定位是把一个“化学上合理、方向上合理”的初猜准备好，供后续 CP2K DIMER、NEB 或频率计算使用。

典型命令：

```powershell
neb-helper tsguess examples\tsguess\sc_dmf_c2h4.yaml
```

`examples\tsguess\sc_dmf_c2h4.yaml` 是模板配置。真实 Sc/u-Sc CIF 不随仓库提交；运行前需要替换 `initial` / `final`，或把对应 CIF 放在 YAML 同目录。

适合使用 `tsguess` 的情况：

```text
IS/FS 都已经可靠，但线性插值产生坏键或穿插
强金属/酸位点锚定导致 DIMER 初猜容易滑回 IS
你已经知道关键 forming / weakening 原子编号
希望一次生成多个候选 fraction 并用 metrics 透明比较
希望从局部路径切线生成 active-only DIMER_VECTOR
```

### 6.1 最小配置

```yaml
workflow: tsguess

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

candidate_outputs:
  directory: tsguess_outputs
  format: cif

dimer_vector:
  enabled: true
  source: local_tangent
  tangent_fractions: [0.70, 0.78]
  atoms: active
  remove_translation: active

check:
  enabled: true
  amplitude: 1.0
```

这份配置假设：

```text
IS/FS 原子顺序一致
编号来自 1-based 可视化软件
577-598 是反应中心
两条 C-C 键正在形成
577-582 代表需要削弱的锚定键或配位键
TS 大概偏产物侧，所以扫描 0.70-0.80
```

### 6.2 输入端点和编号

```yaml
initial: IS.cif
final: FS.cif
atom_indices_1_based: true
active_atoms: "577-598"
frozen_atoms: "1-576"
```

`initial` 和 `final` 必须满足：

```text
原子数一致
元素顺序一致
PBC flags 一致
有 PBC 时 cell 一致或足够接近
```

`atom_indices_1_based: true` 会把 YAML 里的原子编号从 1-based 转换成 Python/ASE 内部的 0-based。来自 GaussView、VESTA、VMD 显示标签的编号通常应该用 1-based；来自 Python 脚本或 ASE list 的编号通常是 0-based。

`active_atoms` 控制候选路径中哪些原子会按 IS -> FS 位移移动和参与 active-region IDPP-like 清理。未指定 `active_atoms` 时，候选路径会把全体系都视为 active；但如果 `dimer_vector.atoms: active`，建议显式指定 active_atoms，否则大体系 DIMER_VECTOR 会包含过多无关运动。

### 6.3 path：候选结构如何生成

```yaml
path:
  method: active_idpp
  base: initial
  fractions: [0.70, 0.75, 0.78, 0.80]
  idpp:
    steps: 200
    max_step: 0.03
    tolerance: 1.0e-5
    tether_weight: 0.02
```

字段说明：

```text
method       active_idpp / idpp_like / active_linear / linear / mic_linear
base         initial / final / linear
fractions    从 IS 到 FS 的候选反应进度
idpp.steps   active-region IDPP-like 梯度下降步数
max_step     每步最大位移，用于避免清理过程太激进
tolerance    active gradient 收敛阈值
tether_weight 对线性插值位置的弱约束，避免结构过度漂移
```

推荐默认是：

```yaml
method: active_idpp
base: initial
```

含义是：非 active 背景保留 IS，active 原子按 MIC 位移插值，并在 active region 内做内部距离清理。对分子筛、表面、金属配位大体系，这通常比全体系 Cartesian 插值更稳。

`base: final` 适合你希望背景更接近产物端的情况。`base: linear` 会让非 active 原子也按 IS/FS 线性插值，适合小分子或全体系都参与反应的情况。

### 6.4 reaction_coordinates：监控哪些几何量

当前第一版支持三类 bond distance：

```yaml
reaction_coordinates:
  forming_bonds:
    - [578, 594]
    - [581, 593]
  weakening_bonds:
    - [577, 582]
  monitor_bonds:
    - [593, 594]
```

用途：

```text
forming_bonds    候选 TS 中希望落在合理成键距离范围内的键
weakening_bonds  候选 TS 中希望已经拉长/削弱的键
monitor_bonds    只写入 metrics.csv，不直接参与评分
```

这些编号是化学知识，工具不会自动判断。对新体系，通常先从 IS/FS 差异最大的键长变化中找 forming / weakening pair，再放入 YAML。

### 6.5 selection：如何推荐一个候选

```yaml
selection:
  prefer_fraction: 0.75
  prefer_fraction_weight: 0.05
  forming_range: [2.10, 2.45]
  target_forming_distance:
  asymmetry_weight: 0.25
  weakening_min: 3.0
  min_pair_distance: 0.65
```

评分逻辑是透明的，所有关键数值都会写入 `metrics.csv`。主要规则：

```text
forming_range          forming bond 落在该区间内不罚分，太短或太长罚分
target_forming_distance 若指定，则按目标距离而不是区间打分
asymmetry_weight       多条 forming bond 不同步时的额外罚分
weakening_min          weakening bond 短于该值时罚分
min_pair_distance      active region 内任意原子对太近时强烈罚分
prefer_fraction        弱偏好，避免几何得分相近时选择离预期太远的 fraction
```

注意：推荐结构只是“几何和反应坐标上更像 TS 初猜”的候选，不是已经优化过的 TS。后续仍然需要 DIMER/NEB 和频率验证。

### 6.6 candidate_outputs：输出文件

```yaml
candidate_outputs:
  directory: tsguess_outputs
  format: cif
  write_all: true
  candidate_template: "ts_guess_{tag}.cif"
  recommended_name: "ts_guess_recommended_{tag}.cif"
  metrics: metrics.csv
  notes: notes.md
```

典型输出：

```text
tsguess_outputs/
  ts_guess_t0p700.cif
  ts_guess_t0p750.cif
  ts_guess_t0p780.cif
  ts_guess_t0p800.cif
  ts_guess_recommended_t0p750.cif
  metrics.csv
  notes.md
```

`metrics.csv` 是最重要的判断依据之一。它会包含：

```text
fraction
recommended
forming_*
weakening_*
monitor_*
forming_mean
forming_std
min_active_pair_distance
score
```

如果 `format: xyz` 且不手动指定文件名模板，默认推荐结构后缀会随格式变成 `.xyz`。

### 6.7 dimer_vector：从局部路径切线生成 DIMER_VECTOR

```yaml
dimer_vector:
  enabled: true
  source: local_tangent
  tangent_fractions: [0.70, 0.78]
  atoms: active
  remove_translation: active
  zero_frozen_atoms: true
  normalize: true
  scale: 1.0
  file: dimer_vector.inc
```

当前支持的方向来源是：

```text
source: local_tangent
```

含义是：

```text
vector = structure(tangent_fractions[1]) - structure(tangent_fractions[0])
```

例如 `[0.70, 0.78]` 就是用 `t=0.78 - t=0.70` 作为局部反应方向。相比直接使用 `FS - IS`，局部切线通常更接近 TS 附近的方向，也更少包含无关重排。

字段说明：

```text
atoms               active / all / 原子列表，控制哪些原子分量写入向量
remove_translation  active/selected 表示去掉所选原子的整体平移；all 表示全体系去平移
zero_frozen_atoms   是否把 frozen_atoms 从 selected atoms 中剔除
normalize           是否归一化向量
scale               归一化后的缩放系数
file                输出 CP2K &DIMER_VECTOR 片段
```

对大体系推荐：

```yaml
atoms: active
remove_translation: active
normalize: true
```

`DIMER_VECTOR` 的正负号通常不影响 DIMER 搜索，因为 `v` 和 `-v` 描述的是同一条方向轴。只有当你希望方向检查轨迹中的 `minus -> center -> plus` 明确对应 IS -> FS 时，才需要交换 `tangent_fractions` 顺序。

### 6.8 check：方向检查轨迹

```yaml
check:
  enabled: true
  amplitude: 1.0
  file: dimer_direction_check_minus_center_plus.xyz
```

开启后会写三帧：

```text
center - amplitude * vector
center
center + amplitude * vector
```

这个文件只用于可视化检查方向。`amplitude` 只影响检查轨迹里的位移大小，不改变推荐结构，也不改变 CP2K 使用的 `dimer_vector.inc`。对 20 个以上 active atoms 的大体系，`0.1` 往往太小，看不出趋势，可以先试 `0.5` 或 `1.0`。

### 6.9 Python API

最短用法：

```python
from neb_helper import generate_ts_guess

result = generate_ts_guess(r"D:\code\neb-helper\examples\tsguess\sc_dmf_c2h4.yaml")

print(result.recommended_fraction)
print(result.recommended_structure)
print(result.metrics_path)
print(result.dimer_vector_path)
print(result.check_path)
```

显式读取配置：

```python
from neb_helper import generate_ts_guess, load_ts_guess_config

spec = load_ts_guess_config(r"D:\path\to\tsguess.yaml")
result = generate_ts_guess(spec)
```

从 Python dict 构造也可以：

```python
from neb_helper import generate_ts_guess

result = generate_ts_guess(
    {
        "initial": r"D:\calc\IS.cif",
        "final": r"D:\calc\FS.cif",
        "atom_indices_1_based": True,
        "active_atoms": "577-598",
        "path": {"method": "active_idpp", "fractions": [0.70, 0.75, 0.78]},
        "reaction_coordinates": {
            "forming_bonds": [[578, 594], [581, 593]],
            "weakening_bonds": [[577, 582]],
        },
        "candidate_outputs": {"directory": r"D:\calc\tsguess_outputs"},
        "dimer_vector": {
            "enabled": True,
            "tangent_fractions": [0.70, 0.78],
            "atoms": "active",
            "remove_translation": "active",
        },
    }
)
```

返回对象 `TsGuessResult` 常用字段：

```text
output_dir              输出目录
recommended_fraction    推荐 fraction
recommended_structure   推荐结构路径
candidates              每个候选的 fraction、score、metrics、structure_path
metrics_path            metrics.csv
notes_path              notes.md
dimer_vector_path       dimer_vector.inc
check_path              minus-center-plus 方向检查轨迹
selected_indices        DIMER_VECTOR 使用的 0-based 原子编号
raw_dimer_norm          归一化前的 selected vector norm
```

### 6.10 建议工作流

实际使用时建议按这个顺序：

1. 准备 IS/FS，确认原子顺序一致。
2. 写 `active_atoms` 和关键 forming / weakening bonds。
3. 先用较宽的 `fractions` 扫描，例如 `[0.60, 0.70, 0.75, 0.80]`。
4. 查看 `metrics.csv` 和全部候选结构。
5. 只在候选都不合理时再调 `active_atoms`、`path.base`、`forming_range` 或 `fractions`。
6. 打开 `dimer_direction_check_minus_center_plus.xyz`，确认方向轴不是整体平移或无关扭动。
7. 用推荐结构和 `dimer_vector.inc` 跑短 DIMER。
8. DIMER 收敛后做频率验证，确认 imaginary mode 对应目标反应。

## 7. dimer 命令：从已有路径派生 DIMER 初猜

`neb-helper dimer` 直接读取已有 `image_*.xyz`，既可以用命令行参数，也可以用 YAML/JSON 配置文件。命令行适合一次性操作；YAML 更适合反复调 active atoms、fraction 和输出目录。

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
```

等价的 YAML 驱动方式：

```powershell
neb-helper dimer examples\dimer\dimer_guess.yaml
```

最小配置：

```yaml
source: ./neb_path
between: [1, 2]
fraction: 0.5

atom_indices_1_based: true
active_atoms: "577-598"
atoms: active
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

YAML 字段和命令行选项基本一一对应：

```text
source              已有 NEB image 目录
between             [LEFT, RIGHT]，0-based image index
fraction/fractions  单个或多个插值比例
prefix/suffix       输入 image 文件命名
output_dir          输出目录
structure_name      单 fraction 时的结构文件名
vector_name         单 fraction 时的 DIMER_VECTOR 文件名
format              ASE 写出格式
atoms               active / all / 原子列表
active_atoms        atoms: active 时使用的原子列表
frozen_atoms        需要从向量中剔除的原子
zero_frozen_atoms   是否剔除 frozen_atoms
normalize           是否归一化向量
scale               归一化后缩放
```

### 7.1 多个 DIMER 初猜

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.25 --fraction 0.5 --fraction 0.75
```

输出文件名会带 fraction tag，避免覆盖。

### 7.2 只保留反应中心

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "10,12,13,48" --atoms active
```

### 7.3 保留所有原子

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --atoms all
```

### 7.4 Python API

直接传参数：

```python
from neb_helper import generate_dimer_guess

result = generate_dimer_guess(
    source=r"D:\code\nebresult",
    left_index=1,
    right_index=2,
    fractions=(0.5,),
    active_atoms=[10, 12, 13, 48],
    atoms="active",
)
```

读取 YAML：

```python
from neb_helper import generate_dimer_guess_from_config

result = generate_dimer_guess_from_config(r"D:\path\to\dimer_guess.yaml")
```

## 8. slice 命令：裁剪和重采样已有路径

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

### 8.1 裁剪 0-3

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

### 8.2 把 0-3 重采样为 7 个中间 image

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

总输出 image 数是 `7 + 2 = 9`。

### 8.3 反向路径

```powershell
neb-helper slice --source D:\code\nebresult --range 3 0
```

## 9. 当前质子转移案例如何使用

如果你判断：

```text
0-3 是真正质子转移
3 之后主要是构象变化
```

可选路线：

### 9.1 IS/FS 端点路线：tsguess

如果你已经有可靠的 reactant/product 端点，且知道质子转移相关的 donor/acceptor/H 原子编号，可以先用 `tsguess` 生成候选 TS 结构和 DIMER_VECTOR：

```powershell
neb-helper tsguess proton_transfer_tsguess.yaml
```

假设 donor 是 42，H 是 43，acceptor 是 88，YAML 中的 `reaction_coordinates` 可以先写成：

```yaml
reaction_coordinates:
  forming_bonds:
    - [43, 88]
  weakening_bonds:
    - [42, 43]
  monitor_bonds:
    - [42, 88]
```

实际 YAML 里要换成你的体系编号。当前版本还不支持符号名或 CV 表达式，仍然是 bond distance 列表。

### 9.2 已有 NEB 路线：DIMER

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "你的反应中心原子" --atoms active
```

再用 `ts_guess.xyz` 和 `dimer_vector.inc` 准备 CP2K DIMER。

### 9.3 NEB 裁剪路线

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

如果需要更多 image：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

然后你可以考虑把 `image_003` 附近做几何优化和频率确认，再把确认后的结构作为新的 product 端点。

## 10. 常见错误和处理

### 10.1 找不到 image 文件

检查命名是否是：

```text
image_000.xyz
image_001.xyz
```

如果不是，用：

```powershell
--prefix your_prefix --suffix your_suffix
```

### 10.2 原子数或顺序不一致

`make` 里用 `endpoint_reorder` 解决端点顺序问题。`dimer` / `slice` 要求已有 image 已经是一条兼容路径，不能自动重排中间 image。

### 10.3 MACE / DeepMD 导入失败

说明当前 Python 环境没有装对应包，或 CUDA/依赖不匹配。先确认：

```powershell
python -c "import mace"
python -c "import deepmd"
```

### 10.4 GPU 显存不足

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

### 10.5 DIMER_VECTOR 是零向量

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

## 11. 现在暂缓的功能

暂时不把更高阶的自动化 endpoint / CV 诊断做成正式命令。原因是这些功能需要把化学判断编码进工具，例如：

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
