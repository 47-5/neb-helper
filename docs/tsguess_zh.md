# `neb-helper tsguess`：从 IS/FS 生成 TS 与 DIMER 初猜

`tsguess` 用于处理这样的场景：你已经有同一反应的 IS/FS，但直接 NEB 或 DIMER 初猜容易被强吸附、分子重排或坏键插值破坏。它会从端点结构生成一组候选 TS 构型，并可选地生成 CP2K `&DIMER_VECTOR`。

典型命令只有一个配置文件：

```powershell
neb-helper tsguess tsguess.yaml
```

## 基本思路

1. 读取 `initial` 和 `final`。
2. 检查原子数、元素顺序、PBC 和晶胞是否一致。
3. 只移动 `active_atoms` 指定的反应中心；非活性原子默认来自 IS 骨架。
4. 在 `path.fractions` 指定的反应进度处生成候选结构。
5. 默认使用 `active_idpp`，对活性区做 IDPP-like 距离清理，减少线性插值造成的坏键。
6. 根据 `reaction_coordinates` 和 `selection` 打分，推荐一个候选。
7. 如果 `dimer_vector.enabled: true`，用局部路径切线生成 CP2K `&DIMER_VECTOR`。
8. 写出 `minus-center-plus.xyz`，方便在 VMD/GaussView/OVITO 中检查方向。

## Sc/u-Sc 一类 Diels–Alder 体系模板

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
  amplitude: 0.10
  file: dimer_direction_check_minus_center_plus.xyz
```

对于 u-Sc，只需要把两条形成键改成实际配对，例如：

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

## 输出文件

默认输出包括：

- `ts_guess_t0p700.cif`、`ts_guess_t0p750.cif` 等候选结构；
- `ts_guess_recommended_t0p750.cif`，推荐的 TS 初猜；
- `metrics.csv`，各候选的反应键距离和打分；
- `notes.md`，人类可读摘要；
- `dimer_vector.inc`，CP2K 可粘贴的 `&DIMER_VECTOR` 块；
- `dimer_direction_check_minus_center_plus.xyz`，方向检查三帧结构。

## 适合的使用方式

这个 workflow 的定位是 **TS/DIMER 初猜生成器**，不是已经优化过的 NEB。它适合在以下情况下使用：

- IS/FS 已经可靠，但线性插值会产生坏键；
- 金属-L 酸或 B 酸强吸附导致 DIMER 容易滑回 IS；
- 你已经知道关键成键/断键编号，只想快速生成一组合理候选；
- 希望在 IDE 或脚本里通过 YAML 改少量参数重复使用。

推荐流程是先运行 `tsguess`，检查推荐结构和方向检查 xyz，然后把推荐 CIF 与 `dimer_vector.inc` 放入 CP2K DIMER 输入文件。
