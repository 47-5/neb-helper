# `neb-helper tsguess`：从 IS/FS 生成 TS 与 DIMER 初猜

`tsguess` 的用途是：从同一反应的 IS/FS 端点生成一组几何上可检查的 TS 候选结构，并可选生成 CP2K `&DIMER_VECTOR`。它解决的是“初猜准备”问题，不是 TS 优化器，也不会替代 DIMER/NEB 和频率验证。

典型命令：

```powershell
neb-helper tsguess tsguess.yaml
```

仓库里的 `examples\tsguess\sc_dmf_c2h4.yaml` 是模板配置。真实 Sc/u-Sc CIF 不随仓库提交；运行前需要替换 `initial` / `final`，或把对应 CIF 放在 YAML 同目录。

## 1. 什么时候该用 tsguess

适合使用：

```text
IS/FS 已经可靠，但直接 Cartesian 插值产生坏键
反应中心只占大体系中的一小部分
金属位点、酸位点或吸附位点会把 DIMER 拉回 IS
你已经知道关键 forming / weakening 原子编号
需要一次生成多个候选 fraction 并透明比较距离指标
需要 active-only 的局部切线 DIMER_VECTOR
```

不适合直接依赖：

```text
IS/FS 原子顺序不一致且还没重排
你完全不知道反应坐标或关键成键/断键
反应路径有多个构象/通道但只写了一个 YAML
希望工具自动判断最终 TS 是否正确
```

## 2. 基本工作流

`tsguess` 做的事情是：

1. 读取 `initial` 和 `final`。
2. 检查原子数、元素顺序、PBC 和晶胞是否一致。
3. 解析 `active_atoms`、`forming_bonds`、`weakening_bonds` 等编号。
4. 在 `path.fractions` 指定的反应进度处生成候选结构。
5. 默认只移动 active region，非 active 背景来自 `path.base`。
6. 默认用 `active_idpp` 对 active region 做轻量 IDPP-like 距离清理。
7. 根据 `reaction_coordinates` 和 `selection` 写出 `metrics.csv` 并推荐一个候选。
8. 如果启用 `dimer_vector`，用局部路径切线写出 CP2K `&DIMER_VECTOR`。
9. 如果启用 `check`，写出三帧方向检查轨迹 `minus-center-plus.xyz`。

## 3. Sc/u-Sc Diels-Alder 体系模板

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
  idpp:
    steps: 200
    max_step: 0.03
    tether_weight: 0.02

reaction_coordinates:
  forming_bonds:
    - [578, 594]
    - [581, 593]
  weakening_bonds:
    - [577, 582]
  monitor_bonds:
    - [593, 594]

selection:
  prefer_fraction: 0.75
  forming_range: [2.10, 2.45]
  weakening_min: 3.0
  min_pair_distance: 0.65

candidate_outputs:
  directory: tsguess_outputs
  format: cif
  write_all: true
  candidate_template: "ts_guess_{tag}.cif"
  recommended_name: "ts_guess_recommended_{tag}.cif"
  metrics: metrics.csv
  notes: notes.md

dimer_vector:
  enabled: true
  source: local_tangent
  tangent_fractions: [0.70, 0.78]
  atoms: active
  remove_translation: active
  normalize: true
  scale: 1.0
  file: dimer_vector.inc

check:
  enabled: true
  amplitude: 1.0
  file: dimer_direction_check_minus_center_plus.xyz
```

对于 u-Sc，如果形成键配对不同，只需要改 reaction coordinates：

```yaml
reaction_coordinates:
  forming_bonds:
    - [578, 593]
    - [581, 594]
  weakening_bonds:
    - [577, 582]
  monitor_bonds:
    - [593, 594]
```

## 4. 字段说明

### 4.1 initial / final / atom_indices_1_based

```yaml
initial: IS.cif
final: FS.cif
atom_indices_1_based: true
```

IS/FS 必须是同一套原子顺序。`tsguess` 不会自动重排端点。若端点元素顺序不同，应先在 `make` workflow 或其他工具里重排。

`atom_indices_1_based: true` 表示 YAML 中所有原子编号按 1-based 解释。来自可视化软件的编号通常是 1-based；来自 ASE/Python 的编号通常是 0-based。

### 4.2 active_atoms / frozen_atoms

```yaml
active_atoms: "577-598"
frozen_atoms: "1-576"
```

`active_atoms` 控制：

```text
哪些原子沿 IS -> FS 位移生成候选结构
哪些原子参与 active_idpp 距离清理
atoms: active 时 DIMER_VECTOR 保留哪些原子分量
```

如果没有指定 `active_atoms`，候选结构生成会把全体系当作 active。但对大体系强烈建议显式指定 active region，否则方向向量和碰撞检查会混入大量无关运动。

### 4.3 path

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

`method` 支持：

```text
active_idpp   active 原子先线性插值，再做 IDPP-like 清理
idpp_like     active_idpp 的同义写法
active_linear active 原子只做 MIC 线性插值
linear        active_linear 的同义写法
mic_linear    active_linear 的同义写法
```

`base` 支持：

```text
initial   非 active 原子来自 IS
final     非 active 原子来自 FS
linear    非 active 原子也按 IS/FS 线性插值
```

`fractions` 是候选结构位置。对偏产物侧的 Diels-Alder 类反应，可以从 `[0.70, 0.75, 0.78, 0.80]` 开始；对更早的 TS，可以试 `[0.35, 0.45, 0.55, 0.65]`。

### 4.4 reaction_coordinates

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

当前版本的 reaction coordinate 是 bond distance。三类 bond 的区别：

```text
forming_bonds    参与评分，要求距离落在 forming_range 附近
weakening_bonds  参与评分，要求距离大于 weakening_min
monitor_bonds    只记录到 metrics.csv，不参与评分
```

`forming_bonds` 和 `weakening_bonds` 不应该盲目依赖默认值。它们是体系知识，换反应后必须重新检查。

### 4.5 selection

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

评分项：

```text
forming_range           forming bond 在区间内不罚分，区间外按偏离程度罚分
target_forming_distance 如果设置，则按目标 forming distance 打分
asymmetry_weight        多条 forming bond 不同步时的额外罚分
weakening_min           weakening bond 短于该值时罚分
min_pair_distance       active region 内任意原子对过近时强烈罚分
prefer_fraction         弱偏好，只在几何得分接近时影响选择
```

输出的 `score` 是用于排序的工具指标，不是能量，也不是 TS 正确性的证明。

### 4.6 candidate_outputs

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

默认输出：

```text
ts_guess_t0p700.cif
ts_guess_t0p750.cif
ts_guess_t0p780.cif
ts_guess_t0p800.cif
ts_guess_recommended_t0p750.cif
metrics.csv
notes.md
```

`metrics.csv` 是判断推荐是否合理的主要依据。`notes.md` 是人类可读摘要，记录输入端点、active atoms、推荐 fraction 和候选表。

### 4.7 dimer_vector

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

当前只支持：

```yaml
source: local_tangent
```

方向定义：

```text
vector = candidate(tangent_fractions[1]) - candidate(tangent_fractions[0])
```

例如 `[0.70, 0.78]` 代表从较反应物侧指向较产物侧。对 CP2K DIMER 来说，`v` 和 `-v` 通常等价，因为它们描述同一条方向轴；交换顺序主要影响可视化中的 plus/minus 标签。

大体系推荐：

```yaml
atoms: active
remove_translation: active
normalize: true
```

这样可以避免 DIMER 初始方向被分子整体平移或骨架无关位移主导。

### 4.8 check

```yaml
check:
  enabled: true
  amplitude: 1.0
  file: dimer_direction_check_minus_center_plus.xyz
```

方向检查文件包含三帧：

```text
minus  = center - amplitude * vector
center = recommended structure
plus   = center + amplitude * vector
```

`amplitude` 只影响这个检查轨迹，不影响推荐结构，也不改变 `dimer_vector.inc`。如果 active atoms 很多，`0.1` 可能肉眼看不出趋势，可以用 `0.5` 或 `1.0`。

## 5. 如何检查一次 tsguess 输出

推荐顺序：

1. 打开 `metrics.csv`，检查推荐 fraction 是否真的有合理 forming / weakening 距离。
2. 打开全部候选结构，确认推荐结构没有明显坏键或穿插。
3. 打开 `dimer_direction_check_minus_center_plus.xyz`，确认方向轴对应目标反应。
4. 把 `ts_guess_recommended_*.cif` 和 `dimer_vector.inc` 放入 CP2K DIMER 输入。
5. 先跑短 DIMER，看前几十步是否沿目标反应方向变化。
6. DIMER 收敛后做频率验证，检查 imaginary mode。

## 6. Python API

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

常用返回字段：

```text
recommended_fraction    推荐 fraction
recommended_structure   推荐结构路径
candidates              每个候选的 fraction / score / metrics / structure_path
metrics_path            metrics.csv
notes_path              notes.md
dimer_vector_path       dimer_vector.inc
check_path              方向检查轨迹
selected_indices        DIMER_VECTOR 使用的 0-based 原子编号
raw_dimer_norm          归一化前 selected vector 的 norm
```

## 7. 常见调参

### 推荐 fraction 太靠前或太靠后

调整：

```yaml
path:
  fractions: [0.60, 0.65, 0.70, 0.75]

selection:
  prefer_fraction: 0.70
```

`prefer_fraction` 是弱偏好，不应该用它强行覆盖几何距离判断。真正决定候选质量的仍然是 `forming_range`、`weakening_min` 和结构检查。

### forming bond 太短或太长

调整：

```yaml
selection:
  forming_range: [2.20, 2.55]
```

或者给目标距离：

```yaml
selection:
  target_forming_distance: 2.30
```

### 方向检查看不清

只调：

```yaml
check:
  amplitude: 1.0
```

这不会影响 CP2K DIMER_VECTOR。

### 方向标签反了

如果只是 `minus -> plus` 标签和你的 IS -> FS 习惯相反，可以交换：

```yaml
dimer_vector:
  tangent_fractions: [0.78, 0.70]
```

这会把向量乘以 `-1`。通常不影响 DIMER 搜索本身。

### DIMER_VECTOR 包含整体平移

确认：

```yaml
dimer_vector:
  atoms: active
  remove_translation: active
```

如果 active_atoms 选得过大，方向仍可能包含无关构象变化。此时应收窄 active region，或后续把反应中心和 buffer region 分层处理。

## 8. 当前限制

当前 `tsguess` 仍是第一版工作流，限制包括：

```text
reaction coordinate 主要是 bond distance
scoring 仍是 forming/weakening/monitor 的固定逻辑
active_idpp 是轻量 IDPP-like 清理，不是完整 IDPP optimizer
不自动识别反应键
不自动判断多个反应通道
不替代 DIMER/NEB 和频率验证
```

后续更通用的方向是 CV + scoring terms、endpoint-diff 辅助工具、existing-band-driven tsguess，以及更化学化的 bad-bond diagnostics。
