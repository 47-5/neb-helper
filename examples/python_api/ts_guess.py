"""Generate TS/DIMER guesses from an IS/FS endpoint pair using Python.

Run from an environment where neb-helper is installed, for example:

    pip install -e D:\code\neb-helper
    python examples\python_api\ts_guess.py

The referenced YAML is a template. Replace its initial/final paths, or place
the matching local CIF files next to the YAML before running this script.
"""

from neb_helper import generate_ts_guess, load_ts_guess_config


def main() -> None:
    config_path = r"D:\code\neb-helper\examples\tsguess\sc_dmf_c2h4.yaml"

    spec = load_ts_guess_config(config_path)
    result = generate_ts_guess(spec)

    print(f"output directory: {result.output_dir}")
    print(f"recommended fraction: {result.recommended_fraction:.3f}")
    print(f"recommended structure: {result.recommended_structure}")
    print(f"metrics: {result.metrics_path}")
    print(f"notes: {result.notes_path}")
    print(f"DIMER_VECTOR: {result.dimer_vector_path}")
    print(f"direction check: {result.check_path}")

    for candidate in result.candidates:
        print(
            f"candidate t={candidate.fraction:.3f}: "
            f"score={candidate.score:.6g}, structure={candidate.structure_path}"
        )


if __name__ == "__main__":
    main()
