"""Minecraft: Java Edition Language File Updater.

A script to update and filter Minecraft language files automatically.
"""

import datetime
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from zipfile import ZipFile

import requests
import orjson
from requests.exceptions import ReadTimeout, RequestException, SSLError

EXPORT_LANGUAGES = [
    l.strip() for l in os.getenv("EXPORT_LANGUAGES", "").split(",") if l
]
# Example value: ["en-US"], an empty list for all languages.
# EXPORT_LANGUAGES = []


def get_response(url: str, max_retries: int) -> requests.Response | None:
    """Get HTTP response and handle exceptions and retry logic.

    Args:
        url (str): URL to request
        max_retries (int): Maximum number of retries

    Returns:
        requests.Response | None: Response object, or None if request fails
    """
    retries = 0
    while retries < max_retries:
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp
        except SSLError as e:
            if retries < max_retries - 1:
                print(f"SSL Error encountered: {e}")
                print("Server access restricted, retrying in 10 seconds...")
                time.sleep(10)
            else:
                print(f"SSL Error encountered: {e}")
                print("Maximum retry attempts reached. Operation terminated.")
        except ReadTimeout as e:
            if retries < max_retries - 1:
                print(f"Request timeout: {e}")
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"Request timeout: {e}")
                print("Maximum retry attempts reached. Operation terminated.")
        except RequestException as ex:
            print(f"Request error occurred: {ex}")
            break
        retries += 1
    return None


def check_sha1(file_path: Path, sha1: str) -> bool:
    """Verify file's SHA1 value.

    Args:
        file_path (Path): Path to the file
        sha1 (str): Expected SHA1 checksum

    Returns:
        bool: Whether verification passed
    """
    with file_path.open("rb") as f:
        return hashlib.file_digest(f, "sha1").hexdigest() == sha1


def get_file(
    url: str, file_name: str, file_path: Path, sha1: str, max_retries: int
) -> None:
    """Download file and verify SHA1 value.

    Args:
        url (str): File download URL
        file_name (str): File name
        file_path (Path): File save path
        sha1 (str): Expected SHA1 checksum
    """
    success = False
    for _ in range(max_retries):
        resp = get_response(url, max_retries)
        if resp is None:
            print(f"Failed to download {file_name}: No response received.")
            continue
        try:
            with open(file_path, "wb") as f:
                f.write(resp.content)
            if check_sha1(file_path, sha1):
                success = True
                break
            print("File SHA1 checksum mismatch, retrying download.")
        except RequestException as e:
            print(f"Request error: {e}")
            sys.exit(1)
    if not success:
        print(f'Unable to download file "{file_name}".')


def process_version(
    versions: list[dict],
    version: str,
    version_type: str,
    target_dir: Path,
    max_retries: int,
) -> dict:
    """Process a specific version of Minecraft: Java Edition language files.

    Args:
        version (str): Version string
        version_type (str): Type of version
        target_dir (Path): Directory to save files
        max_retries (int): Maximum number of retries

    Returns:
        dict: Metadata of language files
    """
    print("\n" + "=" * 60 + f"\nProcessing {version_type} version: {version}\n")

    version_info = next((_ for _ in versions if _["id"] == version), {})
    if not version_info:
        print(f"Could not find version {version} in the version manifest.")
        sys.exit(1)

    client_manifest_url = version_info["url"]
    print(
        f'Fetching client manifest file "{client_manifest_url.rsplit("/", 1)[-1]}"...'
    )
    client_manifest_resp = get_response(client_manifest_url, max_retries)
    if client_manifest_resp is None:
        print("Failed to retrieve client manifest.")
        sys.exit(1)
    client_manifest = client_manifest_resp.json()

    asset_index_url = client_manifest["assetIndex"]["url"]
    print(f'Fetching asset index file "{asset_index_url.rsplit("/", 1)[-1]}"...')
    asset_index_resp = get_response(asset_index_url, max_retries)
    if asset_index_resp is None:
        print("Failed to retrieve asset index.")
        sys.exit(1)
    asset_index = asset_index_resp.json()["objects"]
    print()

    hash_dict = {}
    if not EXPORT_LANGUAGES or "en-US" in EXPORT_LANGUAGES:
        client_url = client_manifest["downloads"]["client"]["url"]
        client_sha1 = client_manifest["downloads"]["client"]["sha1"]
        client_path = target_dir / f"Java_Edition_{version}.jar"
        print(f'Downloading "client.jar" ({client_sha1})...')
        get_file(client_url, client_path.name, client_path, client_sha1, max_retries)
        with ZipFile(client_path) as client:
            with client.open("assets/minecraft/lang/en_us.json") as content:
                hash_dict["en_us.json"] = hashlib.file_digest(
                    content, "sha1"
                ).hexdigest()
                with open(target_dir / "en_us.json", "wb") as en:
                    print('Extracting language file "en_us.json" from client.jar...')
                    en.write(content.read())

    language_files_list = [
        key.split("/")[-1]
        for key in asset_index.keys()
        if key.startswith("minecraft/lang/") and key.endswith(".json")
    ]
    if EXPORT_LANGUAGES:
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
    for lang in language_files_list:
        if lang == "en_us.json":
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
                max_retries,
            )
    return hash_dict


def main() -> None:
    """Main entry point for Minecraft: Java Edition language file updater."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent.parent

    output_dir = base_dir / "java"
    release_dir = output_dir / "release"
    development_dir = output_dir / "development"
    release_dir.mkdir(parents=True, exist_ok=True)
    development_dir.mkdir(exist_ok=True)

    max_retries = 5

    print("Starting Java Edition language file extraction process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    print('\nRetrieving content of version manifest "version_manifest_v2.json"...')
    version_manifest_resp = get_response(
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", max_retries
    )
    if version_manifest_resp is None:
        print("Failed to retrieve version manifest.")
        sys.exit(1)
    version_manifest_json = version_manifest_resp.json()
    versions = version_manifest_json["versions"]

    release_version = version_manifest_json["latest"]["release"]
    development_version = version_manifest_json["latest"]["snapshot"]
    hash_dict = {
        release_version: process_version(
            versions, release_version, "release", release_dir, max_retries
        ),
        development_version: process_version(
            versions, development_version, "snapshot", development_dir, max_retries
        ),
    }

    versions_file = base_dir / "versions.json"
    existing_version_data = {}
    if versions_file.exists():
        with open(versions_file, encoding="utf-8") as f:
            try:
                existing_version_data = orjson.loads(f.read())
            except Exception:
                existing_version_data = None
    version_data_to_save = {
        "java": {
            "update_time": datetime.datetime.now(datetime.UTC).isoformat(),
            "latest": {"release": release_version, "development": development_version},
            "sha1": hash_dict,
        }
    }

    existing_hash = existing_version_data.get("java", {}).get("sha1", {})
    if existing_hash != hash_dict or not versions_file.exists():
        version_data_to_save.update(
            {k: v for k, v in existing_version_data.items() if k != "java"}
        )
        with open(versions_file, "w", encoding="utf-8", newline="\n") as f:
            json_str = orjson.dumps(
                version_data_to_save, option=orjson.OPT_INDENT_2
            ).decode("utf-8")
            f.write(json_str)

    print("\n" + "=" * 60)
    print("Version information saved:")
    print(f"  Release: {release_version}")
    print(f"  Development: {development_version}")
    print("=" * 60)
    print("Java Edition language file extraction completed!")
    print(f"Output directory: {output_dir}")
    print(f"Version information saved to: {versions_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
