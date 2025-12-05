"""Minecraft: Bedrock Edition Language File Extractor.

This script downloads Minecraft: Bedrock Edition packages and extracts
language files from them, converting .lang files to both .lang and .json formats.
Supports both UWP (.appx) and GDK (.msixvc) package formats.
"""

import datetime
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from base64 import b64decode
from pathlib import Path
from typing import TypedDict

import orjson
import requests
from bs4 import BeautifulSoup, Tag
from convert import clean_lang_content, convert_lang_to_json

EXPORT_LANGUAGES = [
    l.strip() for l in os.getenv("EXPORT_LANGUAGES", "").split(",") if l
]
# Example value: ["en-US"], an empty list for all languages.
# EXPORT_LANGUAGES = []


class PackageInfo(TypedDict):
    """Package information dictionary structure.

    Attributes:
        package_type (str): The package type ("Release" or "Preview")
        folder_name (str): The output folder name for extracted files
    """

    package_type: str
    folder_name: str


PACKAGE_INFO: list[PackageInfo] = [
    {"package_type": "Release", "folder_name": "release"},
    {"package_type": "Preview", "folder_name": "development"},
]


class VersionData(TypedDict):
    """Version data from bedrock.json API.

    Attributes:
        Type (str): Package type ("Release" or "Preview")
        BuildType (str): Build type ("UWP" or "GDK")
        ID (str): Version ID
        Date (str): Release date
        Variations (list): List of architecture variations
    """

    Type: str
    BuildType: str
    ID: str
    Date: str
    Variations: list[dict]


def get_latest_version_from_api(package_type: str) -> tuple | None:
    """Get the latest version info from mcappx.com API.

    Args:
        package_type (str): "Release" or "Preview"

    Returns:
        tuple | None: (version, build_type, family_name, version_data)
            For UWP: returns package family name
            For GDK: returns direct download URL
            Returns None if not found
    """
    print(f"Fetching latest {package_type} version from mcappx.com API...")

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
        data = response.json()

        versions_data = data.get("From_mcappx.com", {})

        latest_version: str | None = None
        latest_data: VersionData | None = None
        latest_date = ""

        for version, version_data in versions_data.items():
            if version_data.get("Type") == package_type:
                version_date = version_data.get("Date", "")
                if version_date >= latest_date:
                    latest_date = version_date
                    latest_version = version
                    latest_data = version_data

        if not latest_version or not latest_data:
            print(f"No {package_type} version found in API")
            return None

        build_type = latest_data.get("BuildType", "UWP")
        print(f"Found {package_type} version: {latest_version} ({build_type})")

        if build_type == "GDK":
            variations = latest_data.get("Variations", [])
            for variation in variations:
                if variation.get("Arch") == "x64":
                    metadata = variation.get("MetaData", [])
                    if (
                        metadata
                        and isinstance(metadata[0], str)
                        and metadata[0].startswith("http")
                    ):
                        return (latest_version, build_type, metadata[0], versions_data)

            print(f"No x64 GDK download URL found for {latest_version}")
            return None

        if package_type == "Release":
            family_name = "Microsoft.MinecraftUWP_8wekyb3d8bbwe"
        else:
            family_name = "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"

        return (latest_version, build_type, family_name, versions_data)

    except requests.RequestException as e:
        print(f"Error fetching version info from API: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error parsing API response: {e}", file=sys.stderr)
        return None


def get_appx_file(package_name: str, base_dir: Path) -> Path | None:
    """Download appx file for the specified package.

    Args:
        package_name (str): The package family name to download
        base_dir (Path): Base directory to save the downloaded file

    Returns:
        Path: Path to the downloaded appx file, or None if download failed

    This function uses the store.rg-adguard.net service to obtain download links
    for Microsoft Store packages, then downloads the x64 appx file.
    """
    print(f"Getting download link for {package_name}...")

    url = "https://store.rg-adguard.net/api/GetFiles"
    data = {
        "type": "PackageFamilyName",
        "url": package_name,
        "ring": "RP",
        "lang": "en-US",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error requesting download links: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    for link in soup.find_all("a", href=True):
        if not isinstance(link, Tag):
            continue

        link_text = link.get_text(strip=True)
        if re.search(r"x64.*\.appx\b", link_text):
            href_value = link.get("href")
            if not isinstance(href_value, str):
                continue

            appx_path = base_dir / link_text
            if download_file(href_value, appx_path):
                return appx_path
            return None

    print(f"No x64 appx file found for {package_name}")
    return None


def _process_lang_file(
    zip_file: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    base_output_dir: Path,
) -> bool:
    """Process a single language file from zip archive.

    Args:
        zip_file: Open ZipFile object
        entry: ZipInfo entry for the language file
        base_output_dir: Base output directory for extracted files

    Returns:
        bool: True if file was successfully processed, False otherwise
    """
    relative_path = entry.filename.replace("data/resource_packs/", "").replace(
        "/texts/", "/"
    )

    print(f"  Processing: {entry.filename}")

    raw_content = zip_file.read(entry).decode("utf-8", errors="ignore")
    cleaned_content = clean_lang_content(raw_content)

    if not cleaned_content:
        return False

    return _save_lang_and_json(
        cleaned_content, base_output_dir / relative_path, relative_path
    )


def _get_lang_hash(lang_file: Path) -> str:
    """Get the hash of the language file.

    Args:
        lang_file (Path): Path to the file

    Returns:
        str: Hash of the file
    """
    with lang_file.open("rb") as f:
        return hashlib.file_digest(f, "sha1").hexdigest()


def _save_lang_and_json(content: str, output_file: Path, relative_path: str) -> bool:
    """Save language content to .lang and .json files.

    Args:
        content (str): Cleaned language file content
        output_file (Path): Path to output .lang file
        relative_path (str): Relative path for display purposes

    Returns:
        bool: True if files were successfully saved, False otherwise
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_file.write_text(content, encoding="utf-8", newline="\n")
    print(f"Created {relative_path}")

    json_data = convert_lang_to_json(content)
    json_file = output_file.with_suffix(".json")

    with json_file.open("wb") as f:
        f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))

    json_relative_path = relative_path.replace(".lang", ".json")
    print(f"Created {json_relative_path} with {len(json_data)} entries")

    return True


def export_files_to_structure(
    zip_path: Path, base_output_dir: Path, exclude_beta: bool = False
) -> dict:
    """Extract language files from package to directory structure.

    Args:
        zip_path (Path): Path to the appx/zip file to extract from
        base_output_dir (Path): Base output directory for extracted files
        exclude_beta (bool): Whether to exclude beta paths (for release packages)

    Returns:
        dict: Metadata of language files
    """
    package_type = "release files" if exclude_beta else "files to directory structure"
    print(f"Extracting {package_type} from {zip_path}...")

    hash_dict = {}
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_file:
            texts_entries = [
                entry
                for entry in zip_file.infolist()
                if entry.filename.startswith("data/resource_packs/")
                and "/texts/" in entry.filename
                and entry.filename.endswith(".lang")
            ]
            if EXPORT_LANGUAGES:
                texts_entries = [
                    l
                    for l in texts_entries
                    if l.replace("_", "-").removesuffix(".lang") in EXPORT_LANGUAGES
                ]
            texts_entries.sort(key=lambda x: x.filename)

            for entry in texts_entries:
                lang_file = Path(entry.filename)
                hash_dict[lang_file.name] = _get_lang_hash(lang_file)

                relative_path = entry.filename.replace(
                    "data/resource_packs/", ""
                ).replace("/texts/", "/")

                if exclude_beta and "beta/" in relative_path:
                    print(f"  Skipping beta path: {relative_path}")
                    continue

                _process_lang_file(zip_file, entry, base_output_dir)
    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file", file=sys.stderr)
    except Exception as e:
        print(f"Error extracting from {zip_path}: {e}", file=sys.stderr)

    return hash_dict


def _show_download_progress(
    downloaded_size: int, total_size: int, last_logged: int, is_github_actions: bool
) -> int:
    """Show download progress based on environment.

    Args:
        downloaded_size (int): Number of bytes downloaded
        total_size (int): Total file size in bytes (0 if unknown)
        last_logged (int): Last progress value that was logged
        is_github_actions (bool): Whether running in GitHub Actions

    Returns:
        Updated last_logged value
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
                        last_progress_logged = _show_download_progress(
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
    download_url: str, base_dir: Path, version: str
) -> Path | None:
    """Download GDK package (msixvc) from direct URL.

    Args:
        download_url (str): Direct download URL for the GDK package
        base_dir (Path): Base directory to save the downloaded file
        version (str): Version string for filename

    Returns:
        Path: Path to the downloaded file, or None if download failed
    """
    if "MINECRAFTUWP" in download_url:
        filename = f"Microsoft.MinecraftUWP_{version}_x64__8wekyb3d8bbwe.msixvc"
    else:
        filename = f"Microsoft.MinecraftWindowsBeta_{version}_x64__8wekyb3d8bbwe.msixvc"

    output_path = base_dir / f"Bedrock_Edition_{version}.msixvc"

    if download_file(download_url, output_path):
        return output_path

    return None


def _process_extracted_lang_files(
    resource_packs_dir: Path, base_output_dir: Path
) -> dict:
    """Process language files from extracted resource packs directory.

    Args:
        resource_packs_dir (Path): Path to resource_packs directory
        base_output_dir (Path): Base output directory for processed files

    Returns:
        dict: Hashes of language files
    """
    print(f"Processing language files from {resource_packs_dir}...")

    hash_dict = {}
    for pack_dir in resource_packs_dir.iterdir():
        if not pack_dir.is_dir():
            continue

        texts_dir = pack_dir / "texts"
        if not texts_dir.exists():
            continue

        for lang_file in texts_dir.iterdir():
            if (
                not lang_file.name.endswith(".lang")
                or EXPORT_LANGUAGES
                and lang_file.name.replace("_", "-").removesuffix(".lang")
                not in EXPORT_LANGUAGES
            ):
                continue

            raw_content = lang_file.read_text(encoding="utf-8", errors="ignore")
            cleaned_content = clean_lang_content(raw_content)
            hash_dict[lang_file.name] = _get_lang_hash(lang_file)

            if not cleaned_content:
                continue

            relative_path = f"{pack_dir.name}/{lang_file.name}"
            output_file = base_output_dir / relative_path

            _save_lang_and_json(cleaned_content, output_file, relative_path)

    return hash_dict


def process_gdk_package(msixvc_file: Path, base_output_dir: Path) -> dict:
    """Process GDK package using XvdTool.Streaming with pre-configured CIK keys.

    Args:
        msixvc_file (Path): Path to the msixvc file
        base_output_dir (Path): Base output directory for extracted files

    Returns:
        dict: Hashes of language files

    Note:
        CIK keys must be pre-configured in tools/Cik/ directory.
        Use extract_cik.py script to extract CIK keys before running this function.
    """
    print(f"Processing GDK package: {msixvc_file.name}")

    tools_dir = base_output_dir.parent.parent.parent / "tools"
    tools_dir.mkdir(exist_ok=True)

    xvdtool_exe = tools_dir / "XvdTool.Streaming" / "x64" / "XvdTool.Streaming.exe"
    cik_dir = tools_dir / "Cik"

    if sys.platform != "win32":
        print("\nError: GDK package processing requires Windows")
        return {}

    print("\nChecking for required tools and CIK keys...")

    if not xvdtool_exe.exists():
        print("\nError: XvdTool.Streaming.exe not found")
        return {}

    cik_version = 0 if base_output_dir.name == "release" else 1
    if os.getenv("CIK_DATA"):
        cik_data = b64decode(os.getenv("CIK_DATA")).decode().split("&")[cik_version]
        print("\nUsing CIK from environment variables")
        cik_dir.mkdir(parents=True, exist_ok=True)
        try:
            cik_hex, cik_guid = cik_data.split("@")
            cik_bytes = bytes.fromhex(cik_hex)
            cik_file_path = cik_dir / f"{cik_guid}.cik"
            cik_file_path.write_bytes(cik_bytes)
            print(f"Created CIK file from environment: {cik_file_path.name}")
        except Exception as e:
            print(f"\nError: Invalid CIK data or hex format: {e}")
            return {}

    if not cik_dir.exists():
        print(f"\nError: CIK directory not found: {cik_dir}")
        print("Please run extract_cik.py to extract CIK keys first")
        return {}

    cik_files = list(cik_dir.glob("*.cik"))
    if not cik_files:
        print(f"\nError: No CIK files found in {cik_dir}")
        print("Please run extract_cik.py to extract CIK keys first")
        print("\nFor CI environments, you can also set CIK_DATA environment variable")
        return {}

    print(f"Found {len(cik_files)} CIK key(s):")
    for cik_file in cik_files:
        print(f"  - {cik_file.name}")

    print("\nDecrypting and extracting package using XvdTool.Streaming...")

    extract_output_dir = base_output_dir / "temp_extract"
    extract_output_dir.mkdir(exist_ok=True)

    xvdtool_working_dir = extract_output_dir / "xvdtool_workspace"
    xvdtool_working_dir.mkdir(exist_ok=True)

    xvd_cik_dir = xvdtool_working_dir / "Cik"
    xvd_cik_dir.mkdir(exist_ok=True)

    cik_files_copied = 0
    for cik_file in cik_dir.glob("*.cik"):
        dest_cik = xvd_cik_dir / cik_file.name
        shutil.copy2(cik_file, dest_cik)
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
                print(f"Error output:\n{result.stderr}")
            if result.stdout:
                print(f"Standard output:\n{result.stdout}")
            return {}

        print("Package extraction successful")

        if result.stdout:
            print("XvdTool.Streaming output:")
            for line in result.stdout.splitlines():
                print(f"  {line}")

        if result.stderr:
            print("XvdTool.Streaming errors/warnings:")
            for line in result.stderr.splitlines():
                print(f"  {line}")

    except Exception as e:
        print(f"Failed to run XvdTool.Streaming: {e}")
        return {}

    print("\nOrganizing extracted files...")

    data_folder = None
    for candidate in ["data", "Data", "DATA"]:
        candidate_path = extract_output_dir / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            data_folder = candidate_path
            break

    if not data_folder:
        print("Warning: Could not find data folder in extracted files")
        print(f"Contents of {extract_output_dir}:")
        for item in extract_output_dir.iterdir():
            print(f"  - {item.name}")
        return {}

    resource_packs_dir = data_folder / "resource_packs"
    if not resource_packs_dir.exists():
        print(f"Warning: Could not find resource_packs folder in {data_folder}")
        return {}

    hash_dict = _process_extracted_lang_files(resource_packs_dir, base_output_dir)

    if not hash_dict:
        print("Warning: No language files found in resource packs")
        print(f"Please manually check: {resource_packs_dir}")
        return {}

    shutil.rmtree(extract_output_dir, ignore_errors=True)

    print("\nGDK package processing completed successfully!")
    return hash_dict


def main() -> None:
    """Main entry point for Minecraft: Bedrock Edition language file extractor."""
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent.parent

    output_dir = base_dir / "bedrock" / "extracted"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Starting Bedrock Edition language file extraction process...")
    print(f"Base directory: {base_dir}")
    print(f"Output directory: {output_dir}")

    package_files: list[tuple[str, Path, str]] = []
    version_info: dict[str, str | None] = {"release": None, "development": None}

    max_retries = 5
    retry_count = 0

    while retry_count < max_retries:
        version_info = {"release": None, "development": None}

        for i, package in enumerate(PACKAGE_INFO):
            prefix = "\n" if i == 0 else "\n\n"
            package_type = package["package_type"]
            folder_name = package["folder_name"]

            if retry_count > 0:
                attempt_msg = f"(Attempt {retry_count + 1}/{max_retries})"
                print(f"{prefix}Retrying package type: {package_type} {attempt_msg}")
            else:
                print(f"{prefix}Processing package type: {package_type}")

            version_data = get_latest_version_from_api(package_type)
            if not version_data:
                print(f"Failed to get version info for {package_type}")
                continue

            version, build_type, download_info, versions = version_data

            if folder_name == "release":
                version_info["release"] = version
            else:
                version_info["development"] = version

            package_file: Path | None = None

            if build_type == "UWP":
                package_file = get_appx_file(download_info, base_dir)
            elif build_type == "GDK":
                package_file = download_gdk_package(download_info, base_dir, version)
            else:
                print(f"Unknown build type: {build_type}")
                continue

            if not package_file:
                print(f"Failed to download package for {package_type}")
                continue

            print(f"Downloaded: {package_file.name}")
            package_files.append((folder_name, package_file, build_type))

        if (
            version_info["release"] is not None
            and version_info["development"] is not None
        ):
            break

        retry_count += 1
        if retry_count < max_retries:
            retry_msg = f"Attempt {retry_count + 1}/{max_retries}"
            print(f"\nVersion info incomplete, retrying... ({retry_msg})")

    if version_info["release"] is None or version_info["development"] is None:
        print("\nError: Failed to get complete version info after 5 attempts")
        print(f"  Release: {version_info.get('release', 'null')}")
        print(f"  Development: {version_info.get('development', 'null')}")
        print("Aborting program without updating versions.json")
        sys.exit(1)

    hash_dict = {}
    for folder_name, package_file, build_type in package_files:
        print("\n" + "=" * 60)
        package_output_dir = output_dir / folder_name
        package_output_dir.mkdir(exist_ok=True)

        if build_type == "GDK":
            hash_dict[version_info[folder_name]] = process_gdk_package(
                package_file, package_output_dir
            )
        else:
            exclude_beta = folder_name == "release"
            hash_dict[version_info[folder_name]] = export_files_to_structure(
                package_file, package_output_dir, exclude_beta
            )

        if not hash_dict[version_info[folder_name]]:
            print(f"Failed to process package: {package_file}")

    print("\n" + "=" * 60)
    versions_file = base_dir / "versions.json"

    existing_version_data = {}
    if versions_file.exists():
        try:
            existing_version_data = orjson.loads(versions_file.read_bytes())
        except Exception as e:
            print(f"Warning: Could not read existing versions.json: {e}")

    existing_hash = existing_version_data.get("bedrock", {}).get("sha1", {})
    if existing_hash != hash_dict or not versions_file.exists():
        version_data_to_save = existing_version_data.copy()
        version_data_to_save.update(
            {
                "bedrock": {
                    "update_time": datetime.datetime.now(datetime.UTC).isoformat(),
                    "latest": version_info,
                    "sha1": hash_dict,
                }
            }
        )
        tmp_file = versions_file.with_suffix(versions_file.suffix + ".tmp")
        tmp_file.write_bytes(
            orjson.dumps(version_data_to_save, option=orjson.OPT_INDENT_2)
        )
        tmp_file.replace(versions_file)

    print("Version information saved:")
    print(f"  Release: {version_info.get('release', 'N/A')}")
    print(f"  Development: {version_info.get('development', 'N/A')}")
    print("\n" + "=" * 60)
    print("Bedrock Edition language file extraction completed!")
    print(f"Output directory: {output_dir}")
    print(f"Version information saved to: {versions_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
