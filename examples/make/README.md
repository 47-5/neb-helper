# make examples

Teaching configs:

```text
nebmake_v2_example.yaml     Chinese teaching config kept for existing docs and commands.
nebmake_v2_example_zh.yaml  Chinese teaching config.
nebmake_v2_example_en.yaml  English teaching config.
```

It is meant as a field-by-field example, not as a self-contained runnable case. Before running it, replace at least:

- `initial` and `final`
- `active_atoms` and `frozen_atoms`
- any waypoint/torsion atom indices
- MLFF calculator fields such as `type`, `model`, `head`, `device`, and `dtype`
- `output.directory` if you do not want to write into `v2_output`

Run after editing:

```powershell
neb-helper make examples\make\nebmake_v2_example.yaml
```

For a shorter starter config, use:

```powershell
neb-helper make --write-template nebmake.yaml
```
