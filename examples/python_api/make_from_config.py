"""Build a NEB path from a YAML/JSON config using the Python API."""

from neb_helper import load_config, make_neb_path


def main() -> None:
    spec = load_config(r"D:\path\to\nebmake.yaml")
    result = make_neb_path(spec)

    print(f"output directory: {result['output_dir']}")
    print(f"images written: {len(result['output_images'])}")
    print(f"diagnostics rows: {len(result['diagnostics'])}")


if __name__ == "__main__":
    main()