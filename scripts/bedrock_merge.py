"""Minecraft: Bedrock Edition Language File Merger.

This script merges multiple language JSON files from different resource packs
into consolidated files for release, beta, and preview versions.
"""

import sys
from pathlib import Path
from typing import TypedDict

from convert import load_json_file, save_json_file


class TargetConfig(TypedDict):
    """Target configuration structure.

    Attributes:
        name (str): The name of the target
        path (str): The relative path to the extracted files directory
    """

    name: str
    path: str


MERGE_ORDER: list[str] = [
    "vanilla",
    "experimental_*",
    "oreui",
    "persona",
    "editor",
    "chemistry",
    "education",
    "education_demo",
]

TARGETS: list[TargetConfig] = [
    {"name": "release", "path": "extracted/release"},
    {"name": "beta", "path": "extracted/development"},
    {"name": "preview", "path": "extracted/development"},
]


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
            data = load_json_file(file_path)
            merged.update({k: v for k, v in data.items() if k not in merged})
        except (FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to read {file_path}: {e}", file=sys.stderr)

    return dict(sorted(merged.items()))


def get_ordered_subdirs(
    base_dir: Path, exclude_dirs: list[str] | None = None
) -> list[str]:
    """Get subdirectories in the specified merge order.

    Args:
        base_dir (Path): Base directory to scan for subdirectories
        exclude_dirs (list[str] | None): List of directory names to exclude from processing

    Returns:
        list[str]: List of directory names ordered according to MERGE_ORDER configuration.
        Wildcard patterns (e.g., experimental_*) are supported.
    """
    if exclude_dirs is None:
        exclude_dirs = []

    if not base_dir.exists():
        return []

    all_dirs = [
        d.name for d in base_dir.iterdir() if d.is_dir() and d.name not in exclude_dirs
    ]

    ordered: list[str] = []

    for pattern in MERGE_ORDER:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            matched = [d for d in all_dirs if d.startswith(prefix)]
            ordered.extend(matched)
        else:
            if pattern in all_dirs:
                ordered.append(pattern)

    remaining = [d for d in all_dirs if d not in ordered]
    ordered.extend(remaining)
    print(f"{all_dirs = }\n{ordered = }")

    return ordered


def get_target_subdirs(src_dir: Path, target_name: str) -> list[str]:
    """Get ordered subdirectories for a specific target.

    Args:
        src_dir (Path): Source directory path
        target_name (str): Target name (release, beta, or preview)

    Returns:
        list[str]: List of ordered subdirectory paths
    """

    class _TargetConfig(TypedDict):
        exclude: list[str]
        special_dir: str

    target_config: dict[str, _TargetConfig] = {
        "beta": {"exclude": ["previewapp"], "special_dir": "beta"},
        "preview": {"exclude": ["beta"], "special_dir": "previewapp"},
    }

    if target_name not in target_config:
        return get_ordered_subdirs(src_dir)

    config = target_config[target_name]
    ordered_subdirs = get_ordered_subdirs(src_dir, exclude_dirs=config["exclude"])

    special_dir = src_dir / config["special_dir"]
    if special_dir.exists():
        special_subdirs = get_ordered_subdirs(special_dir)
        ordered_subdirs.extend(
            f"{config['special_dir']}/{subdir}" for subdir in special_subdirs
        )

    return ordered_subdirs


def process_target(target: TargetConfig, base_output_dir: Path) -> None:
    """Process a single target configuration (release, beta, or preview).

    Args:
        target (TargetConfig): Target configuration containing name and path
        base_output_dir (Path): Base output directory for extracted files
    """
    src_dir = base_output_dir.parent / target["path"]
    if not src_dir.exists():
        print(f"Source directory does not exist: {src_dir}")
        return

    output_dir = base_output_dir / target["name"]
    output_dir.mkdir(parents=True, exist_ok=True)

    ordered_subdirs = get_target_subdirs(src_dir, target["name"])

    first_subdir = src_dir / ordered_subdirs[0] if ordered_subdirs else None
    if not first_subdir or not first_subdir.exists():
        print(f"No valid subdirectories found in {src_dir}")
        return

    lang_files = [f.name for f in first_subdir.glob("*.json")]

    for lang_file in lang_files:
        file_list: list[Path] = []

        for subdir in ordered_subdirs:
            subdir_path = src_dir / subdir
            lang_path = subdir_path / lang_file
            if lang_path.exists():
                file_list.append(lang_path)

        if not file_list:
            print(f"No files found for {lang_file} in {target['name']}")
            continue

        merged_data = merge_lang_files(file_list)

        output_file = output_dir / lang_file
        try:
            save_json_file(output_file, merged_data)

            print(f"Merged {len(file_list)} files to {output_file}")
            print(f"  Total keys: {len(merged_data)}")
            print("  Files merged:")
            for file_path in file_list:
                print(f"    {file_path}")

        except (OSError, PermissionError) as e:
            print(f"Error writing output file {output_file}: {e}", file=sys.stderr)


def main() -> None:
    """Main entry point for Minecraft: Bedrock Edition language file merger."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    output_dir = base_dir / "bedrock" / "merged"
    print("Starting Bedrock Edition language file merge process...")
    print(f"Base directory: {base_dir}")

    for target in TARGETS:
        print(f"\nProcessing target: {target['name']}")
        process_target(target, output_dir)

    print(f"\nAll Bedrock Edition language files merged! Output: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
