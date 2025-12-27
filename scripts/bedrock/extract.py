"""Minecraft: Bedrock Edition Language File Extractor.

This script downloads Minecraft: Bedrock Edition packages and extracts
language files from them, converting .lang files to both .lang and .json formats.
Supports both UWP (.appx) and GDK (.msixvc) package formats.
"""

import datetime
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from base64 import b64decode
from pathlib import Path
from typing import IO
from xml.dom import minidom

import mclang
import orjson
import requests
import urllib3

EXPORT_LANGUAGES = [
    l.strip() for l in os.getenv("EXPORT_LANGUAGES", "").split(",") if l
]
# Example value: ["en-US"], an empty list for all languages.
# EXPORT_LANGUAGES = []


def get_mcappx_versions() -> dict:
    """Get Minecraft: Bedrock Edition versions from mcappx.com.

    Returns:
        dict: Versions data
    """
    print("Fetching Minecraft: Bedrock Edition versions from mcappx.com...")

    try:
        headers = {
            "User-Agent": "mcappx_developer",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://mcappx.com/",
        }
        response = requests.get(
            "https://data.mcappx.com/v2/bedrock.json", headers=headers, timeout=30
        )
        response.raise_for_status()
        return response.json().get("From_mcappx.com", {})
    except requests.RequestException as e:
        print(f"Error fetching version information from API: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error parsing API response: {e}", file=sys.stderr)

    return {}


def get_version_from_api(
    target_version: str | None, metadata: dict | None
) -> tuple | None:
    """Get the latest version information from mcappx.com API.

    Args:
        target_version (str | None): The target version to fetch, or None for latest
        metadata (dict | None): The metadata of all versions, or None to fetch

    Returns:
        tuple | None: (version, package_type, build_type, family_name, version_id)
            For UWP: returns package family name
            For GDK: returns direct download URL
            Returns None if not found
    """
    versions_data = metadata or get_mcappx_versions()

    target_data = None
    target_date = ""

    if target_version and target_version in versions_data:
        target_data = versions_data[target_version]
        target_date = target_data.get("Date", "")
    else:
        for version, version_data in versions_data.items():
            version_date = version_data.get("Date", "")
            if version_date >= target_date:
                target_date = version_date
                target_version = version
                target_data = version_data

    if not target_data:
        print(f"\nNot found version in API")
        return

    build_type = target_data["BuildType"]
    print(f"\nProcessing version: {target_version} ({build_type})")

    variations = target_data["Variations"]
    for variation in variations:
        if variation["Arch"] == "x64":
            meta = variation["MetaData"]
            meta = meta[0] if len(meta) else None
            version_id = target_data["ID"]
            package_type = target_data["Type"]
            if variation["ArchivalStatus"] < 2:
                return
            return (target_version, package_type, build_type, meta, version_id)

    print(f"Not found x64 download URL for {target_version}")
    return


def get_appx_file(
    update_id: str | None, version: str, version_id: str, base_dir: Path
) -> Path | None:
    """Download appx file for the specified package.

    Args:
        update_id (str | None): The package update ID to download
        version (str): Version string for filename
        version_id (str): Version ID for filename
        base_dir (Path): Base directory to save the downloaded file

    Returns:
        Path: Path to the downloaded appx file, or None if download failed

    This function uses the store.rg-adguard.net service to obtain download links
    for Microsoft Store packages, then downloads the x64 appx file.
    """
    output_path = base_dir / "bedrock" / f"Bedrock_Edition_{version}.appx"

    download_url = f"https://dl.mcappx.com/be-{version_id.replace('.', '-')}-x64-cn"
    if download_file(download_url, output_path):
        return output_path

    if update_id is None:
        return

    download_url = None
    xml_template = (base_dir / "scripts" / "bedrock" / "UWP_request.xml").read_text()
    filled_xml = xml_template.format(update_id)

    response = requests.post(
        "https://fe3cr.delivery.mp.microsoft.com/ClientWebService/client.asmx/secured",
        data=filled_xml,
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        verify=False,
    )
    document = minidom.parseString(response.text)

    for node in document.getElementsByTagName("FileLocation"):
        temp_url = node.getElementsByTagName("Url")[0].firstChild.nodeValue
        if (
            len(temp_url) != 99
            and temp_url.find("tlu.dl.delivery.mp.microsoft.com") != -1
        ):
            download_url = temp_url

    if download_url and download_file(download_url, output_path):
        return output_path


def process_lang(
    zip_file: zipfile.ZipFile, entry: zipfile.ZipInfo, relative_path: str
) -> bool:
    """Process a single language file from zip archive.

    Args:
        zip_file: Open ZipFile object
        entry: ZipInfo entry for the language file
        relative_path: Relative path of the language file

    Returns:
        bool: True if file was successfully processed, False otherwise
    """
    print(f"Processing: {entry}")
    raw_content = zip_file.read(entry).decode("utf-8", errors="ignore")
    return save_lang_and_json(raw_content, relative_path)


def get_file_hash(file: IO[bytes]) -> str:
    """Get the hash of the language file.

    Args:
        file (IO[bytes]): Content of the file

    Returns:
        str: Hash of the file
    """
    return hashlib.file_digest(file, "sha1").hexdigest()


def save_lang_and_json(content: str, output_file: Path) -> bool:
    """Save language content to .lang and .json files.

    Args:
        content (str): Cleaned language file content
        output_file (Path): Path to output .lang file

    Returns:
        bool: True if files were successfully saved, False otherwise
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content, encoding="utf-8", newline="\n")
    output_file.with_suffix(".json").write_bytes(
        orjson.dumps(mclang.loads(content), option=orjson.OPT_INDENT_2)
    )
    return True


def export_files_to_structure(zip_path: Path, output_dir: Path) -> dict:
    """Extract language files from package to directory structure.

    Args:
        zip_path (Path): Path to the appx/zip file to extract from
        output_dir (Path): Base output directory for extracted files

    Returns:
        dict: Metadata of language files
    """
    print(f"Extracting files from {zip_path}...")

    hash_dict = {}
    try:
        with zipfile.ZipFile(zip_path) as zip_file:
            lang_loc_entries = []
            texts_entries = []
            zip_entries = []
            files = zip_file.namelist()
            for e in files:
                if (
                    EXPORT_LANGUAGES
                    and e.replace("_", "-")
                    .removesuffix(".lang")
                    .removesuffix("-pocket")
                    not in EXPORT_LANGUAGES
                ):
                    continue
                if (
                    e.startswith(("data/resource_packs/", "data/resourcepacks/"))
                    and "/texts/" in e
                    and e.endswith(".lang")
                ):
                    texts_entries.append(e)
                if (
                    e.startswith(("data/lang/", "data/loc/"))
                    and "/pc-base/" not in e
                    and e.endswith(".lang")
                ):
                    lang_loc_entries.append(e)
                if e.endswith(".zip") and e.startswith("data/resource_packs/"):
                    zip_entries.append(e)

            texts_entries.sort()
            for entry in texts_entries:
                relative_path = (
                    entry.removeprefix("data/resource_packs/")
                    .removeprefix("data/resourcepacks/")
                    .replace("/client/", "/")
                    .replace("/texts/", "/")
                )
                hash_dict[relative_path] = get_file_hash(zip_file.open(entry))
                process_lang(zip_file, entry, output_dir / relative_path)

            for entry in lang_loc_entries:
                path_type = "lang" if entry.startswith("data/lang/") else "loc"
                relative_path = f"old/{entry.removeprefix(f'data/{path_type}/')}"
                hash_dict[relative_path] = get_file_hash(zip_file.open(entry))
                process_lang(zip_file, entry, output_dir / relative_path)

            for entry in zip_entries:
                print(f"Extracting inner files from {entry}...")
                with zipfile.ZipFile(zip_file.open(entry)) as inner_zip:
                    inner_dir = entry.removeprefix("data/resource_packs/").removesuffix(
                        ".zip"
                    )
                    for inner_entry in inner_zip.namelist():
                        relative_path = (
                            f"{inner_dir}/{inner_entry.removeprefix('texts/')}"
                        )
                        if inner_entry.endswith(".lang") and (
                            not EXPORT_LANGUAGES
                            or relative_path.replace("_", "-")
                            .removeprefix(inner_dir + "/")
                            .removesuffix(".lang")
                            in EXPORT_LANGUAGES
                        ):
                            hash_dict[relative_path] = get_file_hash(
                                inner_zip.open(inner_entry)
                            )
                            process_lang(
                                inner_zip, inner_entry, output_dir / relative_path
                            )
    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting from {zip_path}: {e}", file=sys.stderr)

    return hash_dict


def show_download_progress(
    downloaded_size: int, total_size: int, last_logged: int, is_github_actions: bool
) -> int:
    """Show download progress based on environment.

    Args:
        downloaded_size (int): Number of bytes downloaded
        total_size (int): Total file size in bytes (0 if unknown)
        last_logged (int): Last progress value that was logged
        is_github_actions (bool): Whether running in GitHub Actions

    Returns:
        int: Updated last logged value
    """
    downloaded_mb = downloaded_size / 1024 / 1024

    if total_size > 0:
        progress = (downloaded_size / total_size) * 100
        total_mb = total_size / 1024 / 1024

        if is_github_actions:
            current_step = int(progress // 10)
            if current_step > last_logged:
                print(
                    f"  Progress: {progress:.0f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
                )
                return current_step
        else:
            progress_text = (
                f"\r  Progress: {progress:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
            )
            print(progress_text, end="", flush=True)
    else:
        if is_github_actions:
            mb_int = int(downloaded_mb)
            if mb_int % 50 == 0 and mb_int > last_logged:
                print(f"  Downloaded: {downloaded_mb:.0f} MB")
                return mb_int
        else:
            print(f"\r  Downloaded: {downloaded_mb:.1f} MB", end="", flush=True)
    return last_logged


def download_file(url: str, output_path: Path) -> bool:
    """Download a file from URL with progress reporting.

    Args:
        url (str): URL to download from
        output_path (Path): Path to save the downloaded file

    Returns:
        bool: True if download successful, False otherwise
    """
    print(f"Downloading from {url}...")

    if output_path.exists():
        print(f"File already exists: {output_path.name}")
        return True

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with requests.get(url, stream=True, headers=headers, timeout=60) as r:
            r.raise_for_status()

            total_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0
            is_github_actions = bool(os.getenv("GITHUB_ACTIONS"))
            last_progress_logged = -1

            with output_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        last_progress_logged = show_download_progress(
                            downloaded_size,
                            total_size,
                            last_progress_logged,
                            is_github_actions,
                        )
            if not is_github_actions:
                print()
        return True
    except requests.RequestException as e:
        print(f"Error downloading file: {e}", file=sys.stderr)
        if output_path.exists():
            output_path.unlink()
    return False


def download_gdk_package(
    download_url: str, version: str, base_dir: Path
) -> Path | None:
    """Download GDK package (msixvc) from direct URL.

    Args:
        download_url (str): Direct download URL for the GDK package
        version (str): Version string for filename
        base_dir (Path): Base directory to save the downloaded file

    Returns:
        Path: Path to the downloaded file, or None if download failed
    """
    output_path = base_dir / "bedrock" / f"Bedrock_Edition_{version}.msixvc"

    if download_file(download_url, output_path):
        return output_path

    return


def process_extracted_langs(resource_packs_dir: Path, output_dir: Path) -> dict:
    """Process language files from extracted resource packs directory.

    Args:
        resource_packs_dir (Path): Path to resource_packs directory
        output_dir (Path): Output directory for processed files

    Returns:
        dict: Hashes of language files
    """
    print(f"Processing language files from {resource_packs_dir}...")

    hash_dict = {}
    for pack_dir in resource_packs_dir.iterdir():
        texts_dir = pack_dir / "texts"
        if not texts_dir.exists():
            continue

        for lang in texts_dir.iterdir():
            if (
                not lang.name.endswith(".lang")
                or EXPORT_LANGUAGES
                and lang.name.replace("_", "-").removesuffix(".lang")
                not in EXPORT_LANGUAGES
            ):
                continue

            raw_content = lang.read_text(encoding="utf-8", errors="ignore")
            relative_path = f"{pack_dir.name}/{lang.name}"
            print(f"Processing: {relative_path}")
            hash_dict[relative_path] = get_file_hash(lang.open("rb"))
            save_lang_and_json(raw_content, output_dir / relative_path)

    return hash_dict


def process_gdk_package(msixvc_file: Path, package_type: str, output_dir: Path) -> dict:
    """Process GDK package using XvdTool.Streaming with pre-configured CIK keys.

    Args:
        msixvc_file (Path): Path to the msixvc file
        package_type (str): Package type ("Release", "Beta", or "Preview")
        output_dir (Path): Output directory for extracted files

    Returns:
        dict: Hashes of language files

    Note:
        CIK keys must be pre-configured in tools/Cik/ directory.
        Use extract_cik.py script to extract CIK keys before running this function.
    """
    print(f"Processing GDK package: {msixvc_file.name}")

    tools_dir = output_dir.parent.parent / "tools"

    xvdtool_exe = tools_dir / "XvdTool.Streaming" / "x64" / "XvdTool.Streaming.exe"
    cik_dir = tools_dir / "Cik"
    cik_dir.mkdir(exist_ok=True)

    if sys.platform != "win32":
        print("\nError: GDK package processing requires Windows", file=sys.stderr)
        return {}

    print("\nChecking for required tools and CIK keys...")

    if not xvdtool_exe.exists():
        print("\nError: XvdTool.Streaming.exe not found", file=sys.stderr)
        return {}

    if os.getenv("CIK_DATA"):
        cik_version = 0 if package_type == "Release" else 1
        cik_data = b64decode(os.getenv("CIK_DATA")).decode().split("&")[cik_version]
        print("\nUsing CIK from environment variables")
        try:
            cik_hex, cik_guid = cik_data.split("@")
            cik_bytes = bytes.fromhex(cik_hex)
            cik_file_path = cik_dir / f"{cik_guid}.cik"
            cik_file_path.write_bytes(cik_bytes)
            print(f"Created CIK file from environment: {cik_file_path.name}")
        except Exception as e:
            print(f"\nError: Invalid CIK data or hex format: {e}", file=sys.stderr)
            return {}

    if not cik_dir.exists():
        print(f"\nError: CIK directory not found: {cik_dir}", file=sys.stderr)
        print("Please run extract_cik.py to extract CIK keys first", file=sys.stderr)
        return {}
    cik_files = tuple(cik_dir.glob("*.cik"))
    if not cik_files:
        print(f"\nError: No CIK files found in {cik_dir}", file=sys.stderr)
        print("Please run extract_cik.py to extract CIK keys first", file=sys.stderr)
        print(
            "\nFor CI environments, you can also set CIK_DATA environment variable",
            file=sys.stderr,
        )
        return {}

    print(f"Found {len(cik_files)} CIK key(s):")
    for cik_file in cik_files:
        print(f"  - {cik_file.name}")

    print("\nDecrypting and extracting package using XvdTool.Streaming...")

    extract_output_dir = output_dir / "temp_extract"
    extract_output_dir.mkdir(exist_ok=True)

    xvdtool_working_dir = extract_output_dir / "xvdtool_workspace"
    xvdtool_working_dir.mkdir(exist_ok=True)

    xvd_cik_dir = xvdtool_working_dir / "Cik"
    xvd_cik_dir.mkdir(exist_ok=True)

    cik_files_copied = 0
    for cik_file in cik_dir.glob("*.cik"):
        dest_cik = xvd_cik_dir / cik_file.name
        shutil.copy(cik_file, dest_cik)
        print(f"Copied CIK: {cik_file.name}")
        cik_files_copied += 1

    if cik_files_copied == 0:
        print("Warning: No CIK files found to copy")
        return {}

    try:
        result = subprocess.run(
            [
                str(xvdtool_exe),
                "extract",
                str(msixvc_file.absolute()),
                "-o",
                str(extract_output_dir.absolute()),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(xvdtool_working_dir),
        )

        if result.returncode != 0:
            print(f"XvdTool.Streaming failed with error code {result.returncode}")
            if result.stderr:
                print(f"Error output:\n{result.stderr}", file=sys.stderr)
            if result.stdout:
                print(f"Standard output:\n{result.stdout}")
            return {}

        if result.stdout:
            print("XvdTool.Streaming output:")
            for line in result.stdout.splitlines():
                print(f"  {line}")

        if result.stderr:
            print("XvdTool.Streaming errors/warnings:")
            for line in result.stderr.splitlines():
                print(f"  {line}")

    except Exception as e:
        print(f"Failed to run XvdTool.Streaming: {e}", file=sys.stderr)
        return {}

    print("\nOrganizing extracted files...")

    data_folder = None
    for candidate in ("data", "Data", "DATA"):
        candidate_path = extract_output_dir / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            data_folder = candidate_path
            break

    if not data_folder:
        print("Warning: Not found data folder in extracted files")
        return {}

    resource_packs_dir = data_folder / "resource_packs"
    if not resource_packs_dir.exists():
        print(f"Warning: Not found resource folder in {data_folder}")
        return {}

    hash_dict = process_extracted_langs(resource_packs_dir, output_dir)

    if not hash_dict:
        print("Warning: No language files found in resource folder")
        print(f"Please manually check: {resource_packs_dir}")
        return {}

    shutil.rmtree(extract_output_dir, ignore_errors=True)

    print("\nGDK package processing completed successfully!")
    return hash_dict


def main(target_version: str | None = None, metadata: dict | None = None) -> bool:
    """Main entry point for Minecraft: Bedrock Edition language file extractor.

    Args:
        target_version (str | None)?: The target version to fetch, or None for latest
        metadata (dict | None)?: The metadata of all versions, or None to fetch

    Returns:
        bool: True if language files changed, False otherwise
    """
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent.parent
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    output_dir = base_dir / "bedrock" / "extracted"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Starting Bedrock Edition language file extraction process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    changed = False
    max_retries = 3
    retry_count = 0

    while retry_count <= max_retries:
        retry_count += 1
        if retry_count > 1:
            retry_msg = f"Attempt {retry_count}/{max_retries}"
            print(f"\nVersion information incomplete, retrying... ({retry_msg})")

        version_data = get_version_from_api(target_version, metadata)
        if not version_data:
            print(f"Failed to get version information")
            continue

        version, package_type, build_type, download_info, version_id = version_data

        package_file = None
        if build_type == "UWP":
            package_file = get_appx_file(download_info, version, version_id, base_dir)
        elif build_type == "GDK":
            package_file = download_gdk_package(download_info, version, base_dir)
        else:
            print(f"Unknown build type: {build_type}")
            continue

        if not package_file:
            print(f"Failed to download package", file=sys.stderr)
            continue

        print(f"Downloaded: {package_file.name}")
        break

    print("\n" + "=" * 60)
    hash_dict = {}
    if build_type == "GDK":
        hash_dict = process_gdk_package(package_file, package_type, output_dir)
    else:
        hash_dict = export_files_to_structure(package_file, output_dir)

    if not hash_dict:
        print(f"Failed to process package: {package_file}", file=sys.stderr)

    print("\n" + "=" * 60)
    versions_file = base_dir / "versions.json"

    existing_version_data = {}
    if versions_file.exists():
        try:
            existing_version_data = orjson.loads(versions_file.read_bytes())
        except Exception as e:
            print(f"Warning: Could not read existing versions.json: {e}")

    existing_hash = existing_version_data.get("bedrock", {}).get("sha1")
    if existing_hash != hash_dict:
        changed = True
        version_data_to_save = existing_version_data.copy()
        version_data_to_save.update(
            {
                "bedrock": {
                    "update_time": datetime.datetime.now(datetime.UTC).isoformat(),
                    "version": version,
                    "sha1": hash_dict,
                }
            }
        )
        tmp_file = versions_file.with_suffix(versions_file.suffix + ".tmp")
        tmp_file.write_bytes(
            orjson.dumps(version_data_to_save, option=orjson.OPT_INDENT_2)
        )
        tmp_file.replace(versions_file)

    if os.getenv("GITHUB_ACTIONS"):
        with open(os.getenv("BEDROCK_EDITION"), "a") as env:
            env.write(f"{version if changed else '/'}\n")

    print("Version information saved:")
    print(f"  development: {version}")
    print("\n" + "=" * 60)
    print("Minecraft: Bedrock Edition language file extraction completed!")
    print(f"Output directory: {output_dir}")
    print(f"Version information saved to: {versions_file}")
    print("=" * 60)
    return changed


if __name__ == "__main__":
    main()
