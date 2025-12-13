"""Minecraft: Java Edition Language File Updater.

A script to update and filter Minecraft language files automatically.
"""

import datetime
import hashlib
import os
import re
import sys
from pathlib import Path
from zipfile import ZipFile

import requests
import orjson
from convert import clean_lang_content, convert_lang_to_json

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
    resp = get_response(
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
    )
    if resp is None:
        print("Failed to retrieve version manifest.", file=sys.stderr)
        return {}
    return resp.json()


def get_response(url: str) -> requests.Response | None:
    """Get HTTP response and handle exceptions and retry logic.

    Args:
        url (str): URL to request

    Returns:
        requests.Response | None: Response object, or None if request fails
    """
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp


def get_file_hash(file_path: Path) -> bool:
    """Verify file's SHA1 value.

    Args:
        file_path (Path): Path to the file

    Returns:
        bool: Whether verification passed
    """
    return hashlib.file_digest(file_path.open("rb"), "sha1").hexdigest()


def get_file(url: str, file_name: str, file_path: Path, sha1: str) -> None:
    """Download file and verify SHA1 value.

    Args:
        url (str): File download URL
        file_name (str): File name
        file_path (Path): File save path
        sha1 (str): Expected SHA1 checksum
        max_retries (int): Maximum number of retries
    """
    success = False
    resp = get_response(url)
    with open(file_path, "wb") as f:
        f.write(resp.content)
    if get_file_hash(file_path) == sha1:
        success = True
    if not success:
        print(f'Unable to download file "{file_name}".', file=sys.stderr)


def process_version(
    versions: list[dict], version: str, target_dir: Path
) -> tuple | None:
    """Process a specific version of Minecraft: Java Edition language files.

    Args:
        versions (list[dict]): List of version metadata
        version (str): Version string
        target_dir (Path): Directory to save files

    Returns:
        tuple | None: Metadata of language files and asset index
    """
    print("\n" + "=" * 60 + f"\nProcessing development version: {version}\n")

    version_info = next((_ for _ in versions if _["id"] == version), {})
    if not version_info:
        print(
            f"Could not find version {version} in the version manifest.",
            file=sys.stderr,
        )
        return

    client_manifest_url = version_info["url"]
    print(
        f'Fetching client manifest file "{client_manifest_url.rsplit("/", 1)[-1]}"...'
    )
    client_manifest_resp = get_response(client_manifest_url)
    if client_manifest_resp is None:
        print("Failed to retrieve client manifest.", file=sys.stderr)
        return
    client_manifest = client_manifest_resp.json()

    asset_index_url = client_manifest["assetIndex"]["url"]
    print(f'Fetching asset index file "{asset_index_url.rsplit("/", 1)[-1]}"...')
    asset_index_resp = get_response(asset_index_url)
    if asset_index_resp is None:
        print("Failed to retrieve asset index.", file=sys.stderr)
        return
    asset_index = asset_index_resp.json()["objects"]
    print()

    hash_dict = {}
    extract_files = [
        "assets/minecraft/lang/en_US.lang",
        "assets/minecraft/lang/en_us.json",
        "assets/minecraft/lang/en_us.lang",
    ]
    if not EXPORT_LANGUAGES or "en-US" in EXPORT_LANGUAGES:
        client_url = client_manifest["downloads"]["client"]["url"]
        client_sha1 = client_manifest["downloads"]["client"]["sha1"]
        client_path = target_dir / f"Java_Edition_{version}.jar"
        print(f'Downloading "client.jar" ({client_sha1})...')
        get_file(client_url, client_path.name, client_path, client_sha1)
        with ZipFile(client_path) as client:
            for filepath in extract_files:
                if filepath not in client.namelist() or not filepath.startswith(
                    "assets/minecraft/lang/"
                ):
                    continue
                lang_source = filepath.rsplit("/", 1)[-1]
                if lang_source.endswith(".lang"):
                    target_dir = target_dir / "old"
                    target_dir.mkdir(exist_ok=True)
                output_path = target_dir / lang_source
                with client.open(filepath) as content:
                    print(
                        f"Extracting /{filepath} to ./{output_path} from client.jar..."
                    )
                    output_path.write_bytes(content.read())
                    hash_dict[lang_source] = get_file_hash(output_path)
                break

    language_files_list = [
        key.split("/")[-1]
        for key in asset_index.keys()
        if key.startswith("minecraft/lang/")
    ]
    if EXPORT_LANGUAGES:
        if lang_source == "en_US.lang":
            language_files_list = [
                l
                for l in language_files_list
                if l.replace("_", "-").removesuffix(".lang") in EXPORT_LANGUAGES
            ]
        if lang_source == "en_us.json":
            language_files_list = [
                l
                for l in language_files_list
                if re.sub(
                    "-[a-z]+",
                    lambda x: x.group(0).upper(),
                    l.replace("_", "-").removesuffix(".json"),
                )
                in EXPORT_LANGUAGES
            ]
        if lang_source == "en_us.lang":
            language_files_list = [
                l
                for l in language_files_list
                if re.sub(
                    "-[a-z]+",
                    lambda x: x.group(0).upper(),
                    l.replace("_", "-").removesuffix(".lang"),
                )
                in EXPORT_LANGUAGES
            ]
    for lang in language_files_list:
        if lang.removesuffix(".json").removesuffix(".lang").upper() == "EN_US":
            continue
        lang_asset = asset_index.get(f"minecraft/lang/{lang}")
        if lang_asset:
            file_hash = lang_asset["hash"]
            hash_dict[lang] = file_hash
            print(f'Downloading language file "{lang}" ({file_hash})...')
            get_file(
                f"https://resources.download.minecraft.net/{file_hash[:2]}/{file_hash}",
                lang,
                target_dir / lang,
                file_hash,
            )
    if lang_source.endswith(".lang"):
        for lang in target_dir.iterdir():
            lang.with_suffix(".json").write_bytes(
                orjson.dumps(
                    convert_lang_to_json(
                        clean_lang_content(lang.read_text(encoding="utf-8"))
                    ),
                    option=orjson.OPT_INDENT_2,
                )
            )
    return (client_manifest["assetIndex"], hash_dict)


def main(target_version: str | None = None, metadata: dict | None = None) -> bool:
    """Main entry point for Minecraft: Java Edition language file updater.

    Args:
        target_version (str | None)?: The target version to fetch, or None for latest
        metadata (dict | None)?: The metadata of all versions, or None to fetch

    Returns:
        bool: True if language files changed, False otherwise
    """
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    output_dir = base_dir / "java"
    output_dir.mkdir(exist_ok=True)

    changed = False
    max_retries = 3
    retry_count = 0

    print("Starting Java Edition language file extraction process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    version = target_version
    version_data = {}
    while retry_count < max_retries:
        retry_count += 1
        try:
            version_manifest = metadata or get_version_manifest()
            versions = version_manifest["versions"]

            version = version or version_manifest["latest"]["snapshot"]
            version_data = process_version(versions, version, output_dir)
            break
        except Exception as e:
            print(f"Failed to process, there may be retrying: {e}")
    else:
        return changed

    versions_file = base_dir / "versions.json"
    existing_data = {}
    if versions_file.exists():
        existing_data = orjson.loads(versions_file.read_bytes())
    version_data_to_save = {
        "java": {
            "update_time": datetime.datetime.now(datetime.UTC).isoformat(),
            "latest": {"development": version},
            "asset_index": version_data[0],
            "sha1": {version: version_data[1]},
        }
    }
    existing_hash = tuple(existing_data.get("java", {}).get("sha1", {}).values())
    if len(existing_hash) == 0:
        existing_hash = (None,)
    if existing_hash[0] != version_data[1] or not versions_file.exists():
        changed = True
        version_data_to_save.update(
            {k: v for k, v in existing_data.items() if k != "java"}
        )
        versions_file.write_bytes(
            orjson.dumps(version_data_to_save, option=orjson.OPT_INDENT_2)
        )

    print("\n" + "=" * 60)
    print("Version information saved:")
    print(f"  Development: {version}")
    print("=" * 60)
    print("Java Edition language file extraction completed!")
    print(f"Output directory: {output_dir}")
    print(f"Version information saved to: {versions_file}")
    print("=" * 60)
    return changed


if __name__ == "__main__":
    main("13w26a")
