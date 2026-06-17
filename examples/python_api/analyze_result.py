"""Analyze an existing NEB result from Python.

Run from an environment where neb-helper is installed, for example:

    pip install -e D:\code\neb-helper
    python examples\python_api\analyze_result.py
"""

from neb_helper import analyze_neb


def main() -> None:
    data, summary = analyze_neb(
        input_path=r"D:\code\nebresult\example1",
        output_image=r"D:\tmp\neb_result.png",
        summary_path=r"D:\tmp\result.txt",
        smooth=False,
    )

    print(f"images: {len(data.energies)}")
    print(f"forward barrier: {summary.forward_barrier:.6f} eV")
    print(f"reverse barrier: {summary.reverse_barrier:.6f} eV")
    print(f"reaction energy: {summary.reaction_energy:.6f} eV")
    print(f"peak image: {summary.peak_index}")


if __name__ == "__main__":
    main()