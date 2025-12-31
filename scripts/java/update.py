"""Minecraft: Java Edition Language File Updater.

A script to update and filter Minecraft language files automatically.
"""

import datetime
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import IO
from zipfile import ZipFile

import mclang
import requests
import orjson

EXPORT_LANGUAGES = [
    l.strip() for l in os.getenv("EXPORT_LANGUAGES", "").split(",") if l
]
# Example value: ["en-US"], an empty list for all languages.
# EXPORT_LANGUAGES = []


def get_version_manifest() -> dict:
    """Get version manifest file.

    Returns:
        dict: Version manifest data
    """
    print('\nRetrieving content of version manifest "version_manifest_v2.json"...')
    response = get_response(
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
    )
    if response is None:
        print("Failed to retrieve version manifest.", file=sys.stderr)
        return {}
    return response.json()


def get_response(url: str) -> requests.Response | None:
    """Get HTTP response and handle exceptions and retry logic.

    Args:
        url (str): URL to request

    Returns:
        requests.Response | None: Response object, or None if request fails
    """
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response


def get_file_hash(file: IO[bytes]) -> str:
    """Get the hash of the language file.

    Args:
        file (IO[bytes]): Content of the file

    Returns:
        str: Hash of the file
    """
    return hashlib.file_digest(file, "sha1").hexdigest()


def get_file(url: str, file_name: str, file_path: Path, sha1: str) -> None:
    """Download file and verify SHA1 value.

    Args:
        url (str): File download URL
        file_name (str): File name
        file_path (Path): File save path
        sha1 (str): Expected SHA1 checksum
    """
    file_path.write_bytes(get_response(url).content)
    if get_file_hash(file_path.open("rb")) != sha1:
        print(f'Unable to download file "{file_name}".', file=sys.stderr)


def process_version(
    target_version: str, versions: list[dict], target_dir: Path, existing_data: dict
) -> tuple | None:
    """Process a specific version of Minecraft: Java Edition language files.

    Args:
        target_version (str): The target version to fetch, or None for latest
        versions (list[dict]): Versions data
        target_dir (Path): Directory to save files

    Returns:
        tuple | None: Metadata of language files and asset index
    """
    print("\n" + "=" * 60 + f"\nProcessing development version: {target_version}\n")

    version_info = next((_ for _ in versions if _["id"] == target_version))
    if not version_info:
        print(
            f"Not found version {target_version} in version manifest.", file=sys.stderr
        )
        return

    print(
        f'Fetching client manifest file "{version_info["url"].rsplit("/", 1)[-1]}"...'
    )
    client_response = get_response(version_info["url"])
    if client_response is None:
        print("Failed to retrieve client manifest.", file=sys.stderr)
        return
    client = client_response.json()
    asset_index = client.get("assetIndex", {})

    hash_dict = {}
    extract_files = [
        "assets/minecraft/lang/en_US.lang",
        "assets/minecraft/lang/en_us.json",
        "assets/minecraft/lang/en_us.lang",
    ]
    client_url = client["downloads"]["client"]["url"]
    client_sha1 = client["downloads"]["client"]["sha1"]
    jar_path = target_dir / f"Java_Edition_{target_version}.jar"
    if not jar_path.exists():
        print(f'Downloading "client.jar" ({client_sha1})...')
        get_file(client_url, jar_path.name, jar_path, client_sha1)
    with ZipFile(jar_path) as jar_file:
        files = jar_file.namelist()
        for i in files:
            if i.startswith("lang/") and i.endswith(".lang"):
                extract_files.append(i)
        for filepath in extract_files:
            if (
                filepath not in files
                or filepath != "lang/stats_US.lang"
                and EXPORT_LANGUAGES
                and re.sub(
                    "-[a-z]+",
                    lambda x: x.group(0).upper(),
                    filepath.rsplit("/")[-1]
                    .replace("_", "-")
                    .removesuffix(".json")
                    .removesuffix(".lang"),
                )
                not in EXPORT_LANGUAGES
            ):
                continue
            entry = filepath.rsplit("/", 1)[-1]
            if filepath != "lang/stats_US.lang":
                lang_source = entry
            if entry.endswith(".lang") and target_dir.name != "old":
                target_dir = target_dir / "old"
                target_dir.mkdir(exist_ok=True)
            output_path = target_dir / entry
            with jar_file.open(filepath) as f:
                print(f"Extracting {filepath} to {output_path} from client.jar...")
                output_path.write_bytes(f.read())
                hash_dict[entry] = get_file_hash(output_path.open("rb"))

    def process_langs() -> None:
        """Process .lang files."""
        if not lang_source.endswith(".lang"):
            return
        for lang in target_dir.iterdir():
            if lang.suffix != ".lang":
                continue
            lang.with_suffix(".json").write_bytes(
                orjson.dumps(
                    mclang.loads(lang.read_bytes()), option=orjson.OPT_INDENT_2
                )
            )

    if len(hash_dict) > 1 or asset_index == existing_data.get("java", {}).get("asset_index"):
        process_langs()
        return (asset_index, hash_dict)
    asset_response = None
    if "url" in asset_index:
        print(
            f'\nFetching asset index file "{asset_index["url"].rsplit("/", 1)[-1]}"...'
        )
        asset_response = get_response(asset_index["url"])
    if asset_response is None:
        print("Failed to retrieve asset index.", file=sys.stderr)
        return (asset_index, hash_dict)
    asset_objects = asset_response.json()["objects"]

    lang_files = tuple(
        key.split("/")[-1]
        for key in asset_objects.keys()
        if key.startswith("lang/") or key.startswith("minecraft/lang/")
    )
    if EXPORT_LANGUAGES:
        if lang_source == "en_US.lang":
            lang_files = tuple(
                l
                for l in lang_files
                if l.replace("_", "-").removesuffix(".lang") in EXPORT_LANGUAGES
            )
        if lang_source == "en_us.json":
            lang_files = tuple(
                l
                for l in lang_files
                if re.sub(
                    "-[a-z]+",
                    lambda x: x.group(0).upper(),
                    l.replace("_", "-").removesuffix(".json"),
                )
                in EXPORT_LANGUAGES
            )
        if lang_source == "en_us.lang":
            lang_files = tuple(
                l
                for l in lang_files
                if re.sub(
                    "-[a-z]+",
                    lambda x: x.group(0).upper(),
                    l.replace("_", "-").removesuffix(".lang"),
                )
                in EXPORT_LANGUAGES
            )
    for lang in lang_files:
        if lang == lang_source:
            continue
        lang_asset = asset_objects.get(
            f"lang/{lang}", asset_objects.get(f"minecraft/lang/{lang}")
        )
        if lang_asset:
            hash_dict[lang] = file_hash = lang_asset["hash"]
            print(f'Downloading language file "{lang}" ({file_hash})...')
            get_file(
                f"https://resources.download.minecraft.net/{file_hash[:2]}/{file_hash}",
                lang,
                target_dir / lang,
                file_hash,
            )
    process_langs()
    return (asset_index, hash_dict)


def main(target_version: str | None = None, metadata: dict | None = None) -> bool:
    """Main entry point for Minecraft: Java Edition language file updater.

    Args:
        target_version (str | None)?: The target version to fetch, or None for latest
        metadata (dict | None)?: The metadata of all versions, or None to fetch

    Returns:
        bool: True if language files changed, False otherwise
    """
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent.parent

    output_dir = base_dir / "java"
    output_dir.mkdir(exist_ok=True)

    changed = False
    max_retries = 3
    retry_count = 0

    print("Starting Java Edition language file update process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    version = target_version
    existing_data = {}
    version_data = {}
    versions_file = base_dir / "versions.json"
    if versions_file.exists():
        existing_data = orjson.loads(versions_file.read_bytes())
    while retry_count < max_retries:
        retry_count += 1
        try:
            version_manifest = metadata or get_version_manifest()
            version = version or version_manifest["latest"]["snapshot"]
            version_data = process_version(
                version, version_manifest["versions"], output_dir, existing_data
            )
            break
        except Exception as e:
            print(f"Failed to process, there may be retrying: {e}")
    else:
        return changed

    version_data_to_save = {
        "java": {
            "update_time": datetime.datetime.now(datetime.UTC).isoformat(),
            "version": version,
            "asset_index": version_data[0],
            "sha1": version_data[1],
        }
    }
    existing_hash = existing_data.get("java", {}).get("sha1")
    if existing_hash != version_data[1]:
        changed = True
        version_data_to_save.update(
            {k: v for k, v in existing_data.items() if k != "java"}
        )
        versions_file.write_bytes(
            orjson.dumps(version_data_to_save, option=orjson.OPT_INDENT_2)
        )

    if os.getenv("GITHUB_ACTIONS"):
        with open(os.getenv("JAVA_EDITION"), "a") as env:
            env.write(f"{version if changed else '/'}\n")

    print("\n" + "=" * 60)
    print("Version information saved:")
    print(f"  development: {version}")
    print("=" * 60)
    print("Minecraft: Java Edition language file updater completed!")
    print(f"Output directory: {output_dir}")
    print(f"Version information saved to: {versions_file}")
    print("=" * 60)
    return changed


if __name__ == "__main__":
    main()
