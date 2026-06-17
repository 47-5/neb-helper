# neb-helper 快速教程

这份教程帮助你快速理解 `neb-helper` 现在能做什么，以及在一个已有 NEB 结果基础上怎么继续推进。完整字段和高级功能说明见 [user_guide_zh.md](user_guide_zh.md)。

## 1. 工具定位

`neb-helper` 现在分成两层：

- `make`：从 `initial` / `final` 两个端点出发，构造 NEB 初猜。它基本继承原来的 `nebmake_v2`。
- `result`：读取已经跑出来的 NEB 结果，再根据已有路径做后处理。目前已经实现 `dimer` 和 `slice`。

也就是说：

```text
从端点造路径：neb-helper make
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
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
neb-helper slice --source D:\code\nebresult --range 0 3
```

兼容旧入口：

```powershell
nebmake-v2 config.yaml
neb-helper config.yaml
```

其中 `neb-helper config.yaml` 会自动等价于 `neb-helper make config.yaml`。

## 4. make：从端点构造 NEB 初猜

先生成一个模板配置：

```powershell
neb-helper make --write-template nebmake.yaml
```

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

## 5. dimer：从已有 image pair 生成 DIMER 初猜

当你已经有一条 NEB 路径，并判断鞍点大概在两张 image 之间，可以用 `dimer` 生成：

- DIMER 初始结构 `ts_guess.xyz`
- CP2K `&DIMER_VECTOR` 片段 `dimer_vector.inc`

例如鞍点大概在 `image_001` 和 `image_002` 中间：

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
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

例如：

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --atom-indices-1-based --active-atoms "11,13,14,49" --atoms active
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

## 6. slice：裁剪已有 NEB 路径

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

### slice 常用选项

```text
--source PATH              已有 NEB image 所在目录
--range START END          inclusive 的 0-based image 范围
--resample-n-images N      重采样后的中间 image 数量
--output-dir PATH          指定输出目录
--output-prefix image      输出 image 文件名前缀
--trajectory NAME          多帧 xyz 文件名；空字符串表示不写
--band-file NAME           CP2K band 片段文件名；空字符串表示不写
--source-map NAME          来源映射 CSV 文件名；空字符串表示不写
```

## 7. 当前质子转移案例的推荐用法

你的当前判断是：

```text
image_000 - image_003：感兴趣的质子转移过程
image_003 之后：大概率是质子转移后的构象变化
```

可以分两条路线推进。

### 路线 A：改用 DIMER

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

### 路线 B：继续做 NEB，但裁剪路径

先裁出真正关心的段：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

如果需要更密的初猜：

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

这里要注意：`image_003` 是否能直接当新 product 端点，需要你后续用几何优化和频率确认。`neb-helper slice` 只负责生成候选路径，不替你判断它是不是稳定极小点。

## 8. 文件命名约定

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

## 9. 常见问题

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

## 10. 现在还不建议自动化的部分

暂时不把 `analyze` 和 `endpoint` 做成正式命令。原因是这些判断目前仍然比较 case by case：例如哪些键长/CV 能代表反应、哪些构象变化应视为无关松弛、`image_003` 是否可以作为新端点，都需要结合具体体系判断。

更稳妥的做法是先使用当前的两个后处理工具：

```text
dimer：从可疑 TS 区间生成 DIMER 初猜
slice：裁剪出真正关心的路径段
```

等积累几个不同体系的使用模式后，再把通用诊断项沉淀成 `analyze`。