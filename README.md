# neb-helper

`neb-helper` is a Python toolbox for NEB workflows.

The package has two intended layers:

- `neb_helper.make`: build CP2K-oriented NEB paths from initial/final structures. This is the current `nebmake_v2` implementation.
- `neb_helper.result`: analyze existing NEB results and derive follow-up workflows once a first-pass band has revealed useful prior knowledge.

## Documentation

- [中文快速教程](docs/quickstart_zh.md)
- [中文完整功能手册](docs/user_guide_zh.md)

## Install

From this repository:

```powershell
pip install .
```

For editable development:

```powershell
pip install -e .
```

## Python API

The same workflows can be used from scripts, notebooks, or IDE run configurations:

```python
from neb_helper import analyze_neb, generate_dimer_guess, slice_band

_, summary = analyze_neb(
    input_path=r"D:\code\nebresult\example1",
    output_image=r"D:\tmp\neb_result.png",
    summary_path=r"D:\tmp\result.txt",
)
print(summary.forward_barrier)
```

The importable API is also collected under `neb_helper.api`:

```python
from neb_helper.api import load_config, make_neb_path
```

See `examples/python_api/` for runnable script templates.

## Build a NEB Path

Build a NEB path from a YAML or JSON config:

```powershell
neb-helper make path\to\config.yaml
```

The package also installs a compatibility command for the current builder:

```powershell
nebmake-v2 path\to\config.yaml
```

For convenience, this also dispatches to the `make` workflow:

```powershell
neb-helper path\to\config.yaml
```

Write a starter config:

```powershell
neb-helper make --write-template nebmake.yaml
```

A more complete field-by-field reference config is available at `examples/make/nebmake_v2_example.yaml`.

## Analyze a NEB Result

Analyze a CP2K `.ener` result directory and write a plot plus `result.txt`:

```powershell
neb-helper analyze D:\code\nebresult\example1
```

Typical outputs:

```text
D:\code\nebresult\example1\neb_result.png
D:\code\nebresult\example1\result.txt
```

The analyzer can also read explicit CP2K `.ener` / `.restart` files or ASE `.traj` files:

```powershell
neb-helper analyze --energy-file D:\calc\neb-r-0-1.ener --restart-file D:\calc\neb.restart
neb-helper analyze --traj-file D:\calc\neb_relax.traj --images-per-band 7
```

## Generate a DIMER Guess

Generate a TS guess halfway between two existing NEB images and write a CP2K `&DIMER_VECTOR` block:

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5
```

By default this reads files named `image_000.xyz`, `image_001.xyz`, ... and writes to:

```text
D:\code\nebresult\dimer_guess_001_002\ts_guess.xyz
D:\code\nebresult\dimer_guess_001_002\dimer_vector.inc
```

Restrict the DIMER direction to a reaction-center atom subset:

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.5 --active-atoms "10,12,13,48" --atoms active
```

Generate several guesses between the same image pair:

```powershell
neb-helper dimer --source D:\code\nebresult --between 1 2 --fraction 0.25 --fraction 0.5 --fraction 0.75
```

Useful options:

```text
--prefix image              Image filename prefix before the numeric index.
--suffix .xyz               Image filename suffix.
--output-dir PATH           Override the default output directory.
--atoms active|all|LIST     Atom components retained in DIMER_VECTOR.
--active-atoms LIST         Active atom list used when --atoms active.
--frozen-atoms LIST         Atom components zeroed by default.
--atom-indices-1-based      Interpret atom selections as 1-based.
--no-normalize              Keep the raw selected pair displacement.
```

## Slice an Existing Band

Crop a meaningful part of an existing band and reindex it as a new CP2K-ready band:

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3
```

By default this writes:

```text
D:\code\nebresult\slice_000_003\image_000.xyz
D:\code\nebresult\slice_000_003\image_001.xyz
D:\code\nebresult\slice_000_003\image_002.xyz
D:\code\nebresult\slice_000_003\image_003.xyz
D:\code\nebresult\slice_000_003\band.txt
D:\code\nebresult\slice_000_003\neb_sliced_path.xyz
D:\code\nebresult\slice_000_003\source_map.csv
```

Resample the cropped segment to a new number of intermediate images while preserving the old path shape by piecewise MIC interpolation along cumulative path length:

```powershell
neb-helper slice --source D:\code\nebresult --range 0 3 --resample-n-images 7
```

Reverse a segment if you want the opposite direction:

```powershell
neb-helper slice --source D:\code\nebresult --range 3 0
```

Useful options:

```text
--prefix image              Input image filename prefix.
--suffix .xyz               Input image filename suffix.
--output-dir PATH           Override the default output directory.
--output-prefix image       Output image filename prefix.
--format xyz                ASE output format.
--trajectory NAME           Multi-frame trajectory name; empty string disables it.
--band-file NAME            CP2K BAND snippet name; empty string disables it.
--source-map NAME           CSV mapping back to source images; empty string disables it.
```

## Package Layout

```text
src/neb_helper/
  cli.py              # top-level neb-helper command
  make/               # current nebmake_v2 implementation
  result/             # analysis and derived-result workflows
```

## Planned Result Workflows

- Higher-level `analyze` diagnostics for selected bond distances, proton-transfer CVs, and conformational-change flags once the generic cases are clearer.
- `endpoint`: stage endpoint candidates from selected images for geometry optimization and frequency checks after the workflow is better justified across cases.
