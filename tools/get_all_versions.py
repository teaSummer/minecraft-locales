"""All Versions Getter."""

import subprocess
import sys
from pathlib import Path


def commit(edition: str, version: str, base_dir: Path) -> None:
    """Run 'git commit'.

    Args:
        edition (str): Edition.
        version (str): Version.
        base_dir (Path): Base directory.
    """
    subprocess.run(["git", "add", "."], cwd=str(base_dir))
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"Update {edition} {version} locales",
        ],
        cwd=str(base_dir),
    )


def main() -> None:
    """Main entry point for getting all versions."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    sys.path.append(str(base_dir / "scripts"))
    from bedrock import extract, merge  # pyright: ignore[reportMissingImports]
    from java import update  # pyright: ignore[reportMissingImports]

    java_data = update.get_version_manifest()
    java_versions = [version["id"] for version in java_data["versions"]]
    java_versions = java_versions[: java_versions.index("b1.0") + 1]
    java_versions.reverse()
    print("=" * 60)
    for jev in java_versions:
        if update.main(jev, java_data):
            commit("Minecraft: Java Edition", jev, base_dir)

    bedrock_data = extract.get_mcappx_versions()
    bedrock_versions = [
        version
        for version, data in bedrock_data.items()
        if any(
            variation["Arch"] == "x64" and variation["ArchivalStatus"] > 1
            for variation in data["Variations"]
        )
    ]
    print("=" * 60)
    for bev in bedrock_versions:
        if extract.main(bev, bedrock_data):
            merge.main()
            commit("Minecraft: Bedrock Edition", bev, base_dir)


if __name__ == "__main__":
    main()
