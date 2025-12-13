"""All Minecraft Versions Getter."""

import subprocess
from pathlib import Path

import bedrock_extract
import bedrock_merge
import java_update


def git_commit(version_type: str, version: str, base_dir: Path) -> None:
    """Run 'git commit'.

    Args:
        version_type (str): Version type.
        version (str): Version.
        base_dir (Path): Base directory.
    """
    subprocess.run(["git", "add", "."], cwd=str(base_dir))
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"Update Minecraft: {version_type} Edition {version} locales",
        ]
    )


def main() -> None:
    """Main entry point for getting all versions."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    java_data = java_update.get_version_manifest()
    java_versions = [version["id"] for version in java_data["versions"]]
    java_versions = java_versions[: java_versions.index("13w26a") + 1]
    java_versions.reverse()
    print("=" * 60)
    for jev in java_versions:
        if java_update.main(jev, java_data):
            git_commit("Java", jev, base_dir)

    bedrock_data = bedrock_extract.get_mcappx_versions()
    bedrock_versions = [
        version
        for version, data in bedrock_data.items()
        if not version.startswith("0.")
        and [
            variation
            for variation in data["Variations"]
            if variation["Arch"] == "x64" and variation["MetaData"]
        ]
    ]
    print("=" * 60)
    for bev in bedrock_versions:
        if bedrock_extract.main(bev, bedrock_data):
            bedrock_merge.main()
            git_commit("Bedrock", bev, base_dir)


if __name__ == "__main__":
    main()
