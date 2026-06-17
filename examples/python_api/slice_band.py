"""Crop and optionally resample an existing NEB band from Python."""

from neb_helper import slice_band


def main() -> None:
    result = slice_band(
        source=r"D:\code\nebresult",
        start_index=0,
        end_index=3,
        resample_n_images=7,
    )

    print(f"output directory: {result.output_dir}")
    print(f"band file: {result.band_path}")
    print(f"trajectory: {result.trajectory_path}")
    print(f"source map: {result.source_map_path}")


if __name__ == "__main__":
    main()