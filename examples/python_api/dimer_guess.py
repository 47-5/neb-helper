"""Generate a DIMER guess from Python."""

from neb_helper import generate_dimer_guess


def main() -> None:
    result = generate_dimer_guess(
        source=r"D:\code\nebresult",
        left_index=1,
        right_index=2,
        fractions=(0.5,),
        active_atoms=[10, 12, 13, 48],
        atoms="active",
    )

    print(f"output directory: {result.output_dir}")
    for file in result.files:
        print(f"fraction {file.fraction:.3f}")
        print(f"  structure: {file.structure_path}")
        print(f"  vector:    {file.vector_path}")


if __name__ == "__main__":
    main()