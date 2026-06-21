"""Generate a DIMER guess from Python.

This example shows both supported Python entry points:

- direct keyword arguments, useful in notebooks and scripts;
- YAML/JSON config files, useful when you want the Python script and CLI to
  share the same configuration.
"""

from neb_helper import generate_dimer_guess, generate_dimer_guess_from_config


def main() -> None:
    direct_result = generate_dimer_guess(
        source=r"D:\code\nebresult",
        left_index=1,
        right_index=2,
        fractions=(0.5,),
        active_atoms=[10, 12, 13, 48],
        atoms="active",
    )

    print(f"direct output directory: {direct_result.output_dir}")
    for file in direct_result.files:
        print(f"fraction {file.fraction:.3f}")
        print(f"  structure: {file.structure_path}")
        print(f"  vector:    {file.vector_path}")

    config_result = generate_dimer_guess_from_config(
        r"D:\code\neb-helper\examples\dimer\dimer_guess.yaml"
    )
    print(f"config output directory: {config_result.output_dir}")


if __name__ == "__main__":
    main()
