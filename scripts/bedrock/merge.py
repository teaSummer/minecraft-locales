"""Minecraft: Bedrock Edition Language File Merger.

This script merges multiple language JSON files from different resource packs
into consolidated files.
"""

import sys
from pathlib import Path

import orjson

MERGE_ORDER: tuple[str] = (
    "beta",
    "chemistry",
    "editor",
    "education",
    "education_*",
    "experimental_*",
    "oreui",
    "persona",
    "previewapp",
    "vanilla",
    "vanilla_*",
)


def merge_lang_files(file_list: list[Path]) -> dict:
    """Merge multiple language JSON files into a single dictionary.

    Args:
        file_list (list[Path]): List of file paths to merge

    Returns:
        dict: Dictionary with merged language data, sorted by keys.
        First occurrence of each key wins in case of duplicates.
    """
    merged = {}

    for file_path in file_list:
        if not file_path.exists():
            continue
        try:
            data = orjson.loads(file_path.read_bytes())
            merged.update({k: v for k, v in data.items() if k not in merged})
        except (FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to read {file_path}: {e}", file=sys.stderr)

    return dict(sorted(merged.items()))


def get_ordered_subdirs(base_dir: Path) -> list[str]:
    """Get subdirectories in the specified merge order.

    Args:
        base_dir (Path): Base directory to scan for subdirectories

    Returns:
        list[str]: List of directory names ordered according to MERGE_ORDER configuration.
        Wildcard patterns (e.g., experimental_*) are supported.
    """
    if not base_dir.exists():
        return []

    all_dirs = tuple(d.name for d in base_dir.iterdir() if d.is_dir())

    ordered: list[str] = []

    for pattern in MERGE_ORDER:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            matched = tuple(d for d in all_dirs if d.startswith(prefix))
            ordered.extend(matched)
        else:
            if pattern in all_dirs:
                ordered.append(pattern)

    remaining = tuple(d for d in all_dirs if d not in ordered)
    ordered.extend(remaining)
    print(f"{all_dirs = }\n{ordered = }")

    return ordered


def main() -> None:
    """Main entry point for Minecraft: Bedrock Edition language file merger."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent.parent

    output_dir = base_dir / "bedrock" / "merged"
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Starting Bedrock Edition language file merge process...")
    print(f"Base directory: {base_dir}")

    src_dir = output_dir.parent / "extracted"
    if not src_dir.exists():
        print(f"Source directory does not exist: {src_dir}")
        return

    ordered_subdirs = get_ordered_subdirs(src_dir)

    first_subdir = src_dir / ordered_subdirs[0] if ordered_subdirs else None
    if not first_subdir or not first_subdir.exists():
        print(f"No valid subdirectories found in {src_dir}")
        return

    lang_files = (f.name for f in first_subdir.glob("*.json"))

    for lang_file in lang_files:
        file_list: list[Path] = []

        for subdir in ordered_subdirs:
            subdir_path = src_dir / subdir
            lang_path = subdir_path / lang_file
            if lang_path.exists():
                file_list.append(lang_path)

        if not file_list:
            print(f"No files found for {lang_file}")
            continue

        merged_data = merge_lang_files(file_list)
        output_file = output_dir / lang_file
        try:
            output_file.write_bytes(
                orjson.dumps(
                    merged_data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
                )
            )
            print(f"Merged {len(file_list)} files to {output_file}:")
            for file_path in file_list:
                print(f"  {file_path}")
            print(f"Total keys: {len(merged_data)}")
        except (OSError, PermissionError) as e:
            print(f"Error writing output file {output_file}: {e}", file=sys.stderr)

    print(f"\nAll Bedrock Edition language files merged! Output: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
