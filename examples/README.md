# neb-helper examples

The YAML files in this directory are teaching-oriented reference configs. They
are not all self-contained runnable calculations; replace structure paths,
atom indices, and model paths before using them for a real system.

Each workflow has Chinese and English versions:

```text
examples/analyze/analyze_result.yaml       English teaching config
examples/analyze/analyze_result_en.yaml    English teaching config
examples/analyze/analyze_result_zh.yaml    Chinese teaching config

examples/make/nebmake_v2_example.yaml      Chinese teaching config kept for compatibility
examples/make/nebmake_v2_example_zh.yaml   Chinese teaching config
examples/make/nebmake_v2_example_en.yaml   English teaching config

examples/dimer/dimer_guess.yaml            English teaching config
examples/dimer/dimer_guess_en.yaml         English teaching config
examples/dimer/dimer_guess_zh.yaml         Chinese teaching config

examples/tsguess/sc_dmf_c2h4.yaml          English teaching config
examples/tsguess/sc_dmf_c2h4_en.yaml       English teaching config
examples/tsguess/sc_dmf_c2h4_zh.yaml       Chinese teaching config
```

Typical commands:

```powershell
neb-helper make examples\make\nebmake_v2_example.yaml
neb-helper analyze examples\analyze\analyze_result.yaml
neb-helper dimer examples\dimer\dimer_guess.yaml
neb-helper tsguess examples\tsguess\sc_dmf_c2h4.yaml
```

Indexing convention:

```text
make      defaults to 0-based unless atom_indices_1_based: true
analyze   image indices in result.txt are 0-based
dimer     between: [LEFT, RIGHT] uses image indices; atom indices follow atom_indices_1_based
tsguess   atom indices follow atom_indices_1_based
```

For real calculations, prefer copying one example to your working directory and
editing the copy. This keeps the repository examples as stable references.
