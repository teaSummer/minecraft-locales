"""Minecraft: Bedrock Edition Language File Converter.

This module provides utilities for converting between .lang, .json, and .tsv formats
used in Minecraft: Bedrock Edition language files.
"""

import csv
from collections import OrderedDict
from pathlib import Path

import orjson


def clean_lang_content(raw_content: str) -> str:
    """Clean and normalize language file content.

    Args:
        raw_content (str): The raw content of the language file.

    Returns:
        str: The cleaned and normalized content.
    """
    cleaned_content = (
        raw_content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    )
    cleaned_content = "\n".join(
        line for line in cleaned_content.splitlines() if line.strip(" \t\r\n\f\v")
    )
    return remove_duplicate_keys(cleaned_content) if cleaned_content.strip() else ""


def remove_duplicate_keys(lang_content: str) -> str:
    """Remove duplicate keys from lang file content, keeping first occurrence.

    Args:
        lang_content (str): The content of the .lang file as a string.

    Returns:
        str: The cleaned .lang file content with duplicates removed.
    """
    seen_keys: set[str] = set()
    result_lines: list[str] = []

    for line in lang_content.splitlines():
        trimmed_line = line.strip()

        if not trimmed_line or trimmed_line.startswith("##"):
            result_lines.append(line)
            continue

        equal_index = trimmed_line.find("=")
        if equal_index > 0:
            key = trimmed_line[:equal_index].strip()
            if key not in seen_keys:
                seen_keys.add(key)
                result_lines.append(line)
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def convert_lang_to_json(lang_content: str) -> OrderedDict[str, str]:
    """Convert .lang file content to JSON-compatible ordered dictionary.

    Args:
        lang_content (str): The content of the .lang file as a string.

    Returns:
        OrderedDict: An ordered dictionary with keys and values from the .lang file.
    """
    json_data: OrderedDict[str, str] = OrderedDict()

    for line in lang_content.splitlines():
        line = line.strip(" \t\r\n\f\v")

        if not line or line.startswith("##"):
            continue

        equal_index = line.find("=")
        if equal_index > 0:
            key = line[:equal_index].strip()
            value = line[equal_index + 1 :].strip(" \t\r\n\f\v")

            tab_hash_index = value.find("\t#")
            if tab_hash_index != -1:
                value = value[:tab_hash_index].rstrip(" \t\r\n\f\v")

            if key not in json_data:
                json_data[key] = value

    return json_data


def convert_json_to_lang(json_data: dict) -> str:
    """Convert JSON data to .lang file content format.

    Args:
        json_data (dict): The JSON data to convert.

    Returns:
        str: The .lang file content as a string.
    """
    lines: list[str] = []
    for key, value in json_data.items():
        lines.append(f"{str(key)}={str(value)}")
    return "\n".join(lines)


def load_lang_file(file_path: Path) -> OrderedDict[str, str]:
    """Load a .lang file and convert it to an ordered dictionary.

    Args:
        file_path (Path): The path to the .lang file.

    Returns:
        OrderedDict: The loaded data as an ordered dictionary.
    """
    content = file_path.read_text(encoding="utf-8")
    cleaned_content = clean_lang_content(content)
    return convert_lang_to_json(cleaned_content)


def load_json_file(file_path: Path) -> dict:
    """Load a JSON file and return its contents.

    Args:
        file_path (Path): The path to the JSON file.

    Returns:
        dict: The loaded JSON data.
    """
    with file_path.open("r", encoding="utf-8") as f:
        return orjson.loads(f.read())


def load_tsv_file(file_path: Path) -> dict:
    """Load a TSV file and return its contents as structured data.

    Args:
        file_path (Path): The path to the TSV file.

    Returns:
        dict: A dictionary with 'headers' and 'rows' keys.
    """
    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        headers = next(reader, [])
        rows = list(reader)
    return {"headers": headers, "rows": rows}


def save_lang_file(file_path: Path, data: dict) -> None:
    """Save data as a .lang file.

    Args:
        file_path (Path): The path to save the .lang file.
        data (dict): The data to save.
    """
    lang_content = convert_json_to_lang(data)
    file_path.write_text(lang_content, encoding="utf-8", newline="\n")


def save_lang_file_with_sources(
    file_path: Path, sources_data: dict[str, dict[str, str]]
) -> None:
    """Save translation data as a .lang file, organized by source files.

    Args:
        file_path (Path): The path to save the .lang file
        sources_data (dict): Dictionary mapping source files to their translations
    """
    total_entries = sum(len(translations) for translations in sources_data.values())
    if total_entries == 0:
        file_path.write_text("", encoding="utf-8", newline="\n")
        return

    lines: list[str] = []

    first_section = True
    for source_file, translations in sources_data.items():
        if not translations:
            continue

        if not first_section:
            lines.append("")
        first_section = False

        lines.append(f"## {source_file}")

        translation_lines = [f"{key}={value}" for key, value in translations.items()]
        lines.extend(translation_lines)

    content = "\n".join(lines)
    file_path.write_text(content, encoding="utf-8", newline="\n")


def save_json_file(file_path: Path, data: dict, sort_keys: bool = True) -> None:
    """Save data as a JSON file with proper formatting.

    Args:
        file_path (Path): The path to save the JSON file.
        data (dict): The data to save.
        sort_keys (bool, optional): Whether to sort the keys. Defaults to True.
    """
    options = orjson.OPT_INDENT_2
    if sort_keys:
        options |= orjson.OPT_SORT_KEYS
    with file_path.open("wb") as f:
        f.write(orjson.dumps(data, option=options))


def save_tsv_file(file_path: Path, headers: list[str], rows: list[list[str]]) -> None:
    """Save data as a TSV file.

    Args:
        file_path (Path): The path to save the TSV file.
        headers (list[str]): The headers for the TSV file.
        rows (list[list[str]]): The rows of data.
    """
    with file_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(headers)
        writer.writerows(rows)


def build_key_to_source_mapping(
    extracted_dir: Path, branch: str, lang_code: str
) -> dict[str, str]:
    """Build a mapping from translation keys to their source files.

    Args:
        extracted_dir (Path): Path to the extracted directory
        branch (str): Branch name (release, beta, preview)
        lang_code (str): Language code (zh_CN, zh_TW, etc.)

    Returns:
        dict[str, str]: Mapping from keys to source file paths
    """
    if branch == "release":
        search_base = extracted_dir / "release"
    else:
        search_base = extracted_dir / "development"

    search_order = [
        "vanilla",
        "oreui",
        "persona",
        "editor",
        "chemistry",
        "education",
        "education_demo",
    ]

    if branch == "beta":
        search_order.append("beta")
    elif branch == "preview":
        search_order.append("previewapp")

    key_to_source: dict[str, str] = {}

    for subdir in reversed(search_order):
        lang_file = search_base / subdir / f"{lang_code}.lang"
        if lang_file.exists():
            content = lang_file.read_text(encoding="utf-8")
            source_path = f"resource_packs/{subdir}/texts/{lang_code}.lang"

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("##"):
                    continue

                equal_index = line.find("=")
                if equal_index > 0:
                    key = line[:equal_index].strip()
                    if key not in key_to_source:
                        key_to_source[key] = source_path

    return key_to_source


def extract_translation_from_tsv(tsv_file: Path) -> OrderedDict[str, str]:
    """Extract translation data from TSV file.

    Args:
        tsv_file (Path): The path to the TSV file.

    Returns:
        OrderedDict: The extracted translation data.
    """
    tsv_data = load_tsv_file(tsv_file)
    headers = tsv_data["headers"]
    rows = tsv_data["rows"]

    if "Key" not in headers:
        raise ValueError("TSV file must contain a 'Key' column")
    if "Translation" not in headers:
        raise ValueError("TSV file must contain a 'Translation' column")

    key_index = headers.index("Key")
    translation_index = headers.index("Translation")
    result: OrderedDict[str, str] = OrderedDict()

    for row in rows:
        if len(row) > max(key_index, translation_index):
            key = row[key_index]
            translation = row[translation_index] if translation_index < len(row) else ""
            if key and translation:
                result[key] = translation

    return result


def extract_translation_with_sources(
    tsv_file: Path, extracted_dir: Path, branch: str
) -> dict[str, dict[str, str]]:
    """Extract translation data from TSV file, organized by source file.

    Args:
        tsv_file (Path): The path to the TSV file
        extracted_dir (Path): Path to the extracted directory
        branch (str): Branch name (release, beta, preview)

    Returns:
        dict: Dictionary mapping source files to their translations
    """
    tsv_data = load_tsv_file(tsv_file)
    headers = tsv_data["headers"]
    rows = tsv_data["rows"]

    if "Key" not in headers:
        raise ValueError("TSV file must contain a 'Key' column")
    if "Translation" not in headers:
        raise ValueError("TSV file must contain a 'Translation' column")

    key_index = headers.index("Key")
    translation_index = headers.index("Translation")

    mapping = build_key_to_source_mapping(extracted_dir, branch, "en_US")
    sources_map: dict[str, dict[str, str]] = {}

    for row in rows:
        if len(row) > max(key_index, translation_index):
            key = row[key_index]
            translation = row[translation_index] if translation_index < len(row) else ""

            if key and translation and key in mapping:
                source_file = mapping[key]

                if source_file not in sources_map:
                    sources_map[source_file] = OrderedDict()
                sources_map[source_file][key] = translation

    return sources_map


def apply_translation_to_tsv(
    tsv_file: Path, translation_data: dict, output_file: Path | None = None
) -> Path:
    """Apply translation data to TSV file, adding or updating the Translation column.

    Args:
        tsv_file (Path): The path to the TSV file.
        translation_data (dict): The translation data to apply.
        output_file (Path | None, optional): The output file path. Defaults to None.

    Returns:
        Path: The path to the output file.
    """
    if output_file is None:
        output_file = tsv_file

    tsv_data = load_tsv_file(tsv_file)
    headers = tsv_data["headers"]
    rows = tsv_data["rows"]

    if "Key" not in headers:
        raise ValueError("TSV file must contain a 'Key' column")

    key_index = headers.index("Key")

    if "Translation" not in headers:
        headers.append("Translation")
        translation_index = len(headers) - 1
        for row in rows:
            while len(row) <= translation_index:
                row.append("")
    else:
        translation_index = headers.index("Translation")

    for row in rows:
        if len(row) > key_index:
            key = row[key_index]
            if key in translation_data:
                while len(row) <= translation_index:
                    row.append("")
                row[translation_index] = str(translation_data[key])

    save_tsv_file(output_file, headers, rows)
    return output_file


def convert_lang_to_json_file(lang_file: Path, json_file: Path | None = None) -> Path:
    """Convert a .lang file to a .json file and return output path.

    Args:
        lang_file (Path): The path to the .lang file.
        json_file (Path | None, optional): The output JSON file path. Defaults to None.

    Returns:
        Path: The path to the output JSON file.
    """
    if json_file is None:
        json_file = lang_file.with_suffix(".json")
    data = load_lang_file(lang_file)
    save_json_file(json_file, data)
    return json_file


def convert_json_to_lang_file(json_file: Path, lang_file: Path | None = None) -> Path:
    """Convert a .json file to a .lang file and return output path.

    Args:
        json_file (Path): The path to the JSON file.
        lang_file (Path | None, optional): The output .lang file path. Defaults to None.

    Returns:
        Path: The path to the output .lang file.
    """
    if lang_file is None:
        lang_file = json_file.with_suffix(".lang")
    data = load_json_file(json_file)
    save_lang_file(lang_file, data)
    return lang_file


def convert_tsv_to_json_file(tsv_file: Path, json_file: Path | None = None) -> Path:
    """Convert a TSV file to a JSON file by extracting translations.

    Args:
        tsv_file (Path): The path to the TSV file.
        json_file (Path | None, optional): The output JSON file path. Defaults to None.

    Returns:
        Path: The path to the output JSON file.
    """
    if json_file is None:
        json_file = tsv_file.with_suffix(".json")
    translation_data = extract_translation_from_tsv(tsv_file)
    save_json_file(json_file, translation_data)
    return json_file


def convert_tsv_to_lang_file(tsv_file: Path, lang_file: Path | None = None) -> Path:
    """Convert a TSV file to a LANG file by extracting translations.

    Args:
        tsv_file (Path): The path to the TSV file.
        lang_file (Path | None, optional): The output .lang file path. Defaults to None.

    Returns:
        Path: The path to the output .lang file.
    """
    if lang_file is None:
        lang_file = tsv_file.with_suffix(".lang")
    translation_data = extract_translation_from_tsv(tsv_file)
    save_lang_file(lang_file, translation_data)
    return lang_file


def convert_json_to_tsv_file(json_file: Path, tsv_file: Path) -> Path:
    """Apply JSON translations to an existing TSV file.

    Args:
        json_file (Path): The path to the JSON file.
        tsv_file (Path): The path to the TSV file.

    Returns:
        Path: The path to the updated TSV file.
    """
    translation_data = load_json_file(json_file)
    return apply_translation_to_tsv(tsv_file, translation_data)


def convert_lang_to_tsv_file(lang_file: Path, tsv_file: Path) -> Path:
    """Apply LANG translations to an existing TSV file.

    Args:
        lang_file (Path): The path to the .lang file.
        tsv_file (Path): The path to the TSV file.

    Returns:
        Path: The path to the updated TSV file.
    """
    translation_data = load_lang_file(lang_file)
    return apply_translation_to_tsv(tsv_file, translation_data)


def handle_apply_to_tsv(input_file: Path, input_suffix: str, tsv_file: Path) -> Path:
    """Handle applying translations to TSV file.

    Args:
        input_file (Path): The path to the input file.
        input_suffix (str): The suffix of the input file.
        tsv_file (Path): The path to the TSV file.

    Returns:
        Path: The path to the updated TSV file.
    """
    converters = {
        ".json": convert_json_to_tsv_file,
        ".lang": convert_lang_to_tsv_file,
    }

    if input_suffix not in converters:
        raise ValueError(f"Cannot apply {input_suffix} files to TSV")

    return converters[input_suffix](input_file, tsv_file)


def handle_normal_conversion(
    input_file: Path, input_suffix: str, output_file: Path | None
) -> Path:
    """Handle normal file conversions.

    Args:
        input_file (Path): The path to the input file.
        input_suffix (str): The suffix of the input file.
        output_file (Path | None): The output file path.

    Returns:
        Path: The path to the output file.
    """
    converters = {
        ".lang": convert_lang_to_json_file,
        ".json": convert_json_to_lang_file,
        ".tsv": handle_tsv_conversion,
    }

    if input_suffix not in converters:
        raise ValueError(
            f"Unsupported file extension '{input_suffix}'. Supported extensions: .lang, .json, .tsv"
        )

    return converters[input_suffix](input_file, output_file)


def handle_tsv_conversion(input_file: Path, output_file: Path | None) -> Path:
    """Handle TSV file conversion logic.

    Args:
        input_file (Path): The path to the input TSV file.
        output_file (Path | None): The output file path.

    Returns:
        Path: The path to the output file.
    """
    if output_file is None:
        return convert_tsv_to_json_file(input_file, None)

    output_suffix = output_file.suffix.lower()
    converters = {
        ".json": convert_tsv_to_json_file,
        ".lang": convert_tsv_to_lang_file,
    }

    if output_suffix not in converters:
        raise ValueError(f"Unsupported output format '{output_suffix}' for TSV input")

    return converters[output_suffix](input_file, output_file)


def main() -> None:
    """Command-line entry point for language file conversions."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python convert.py <input_file> [output_file] [options]")
        print("Converts between .lang, .json, and .tsv formats.")
        print("\nOptions for TSV operations:")
        print(
            "  --apply-to <tsv>   Apply translations from input file to specified TSV file"
        )
        print("\nExamples:")
        print("  python convert.py file.lang                    # Convert to JSON")
        print("  python convert.py file.json output.lang        # Convert JSON to LANG")
        print(
            "  python convert.py file.tsv                     # Extract translations to JSON"
        )
        print("  python convert.py file.json --apply-to data.tsv # Apply JSON to TSV")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = None
    apply_to_tsv = None

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--apply-to" and i + 1 < len(sys.argv):
            apply_to_tsv = Path(sys.argv[i + 1])
            i += 2
        else:
            if output_file is None:
                output_file = Path(arg)
            i += 1

    if not input_file.exists():
        print(f"Error: Input file '{input_file}' does not exist")
        sys.exit(1)

    try:
        input_suffix = input_file.suffix.lower()

        if apply_to_tsv is not None:
            if not apply_to_tsv.exists():
                print(f"Error: Target TSV file '{apply_to_tsv}' does not exist")
                sys.exit(1)
            result_file = handle_apply_to_tsv(input_file, input_suffix, apply_to_tsv)
            print(f"Applied translations from {input_file} to {result_file}")
        else:
            result_file = handle_normal_conversion(
                input_file, input_suffix, output_file
            )
            action = (
                "Extracted translations from" if input_suffix == ".tsv" else "Converted"
            )
            print(f"{action} {input_file} -> {result_file}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
