# Minecraft Locales

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE) [![Update locales](https://github.com/teaSummer/minecraft-locales/actions/workflows/update.yml/badge.svg)](https://github.com/teaSummer/minecraft-locales/actions/workflows/update.yml)

A collection of Minecraft language files, including translations for all supported languages:

- *Minecraft: Java Edition*
- *Minecraft: Bedrock Edition* (with *Minecraft Education* and *Minecraft: Pocket Edition* language files)

To get language files of older versions, see [history branch](https://github.com/teaSummer/minecraft-locales/blob/history/README.md).

## File Structure

Here's a breakdown of the repository's file structure:

- `.github/workflows/`: Contains the GitHub Actions workflow for automating the translation process.
- `bedrock/extracted/`: Contains *Minecraft: Bedrock Edition* raw language files as extracted directly from the game.
- `bedrock/merged/`: Holds consolidated *Minecraft: Bedrock Edition* language files, organized by game version.
- `java/`: Contains *Minecraft: Java Edition* raw language files as extracted directly from the game.
- `scripts/`: Houses utility scripts for managing and updating the translations.
- `tools/`: Contains the tool for processing packages.

## Local Running

To run the script locally, you need to have the following installed:

- [Python 3.11+](https://www.python.org/downloads)
- [.NET 9.0](https://dotnet.microsoft.com/en-us/download/dotnet/9.0)
- [uv](https://github.com/astral-sh/uv)

### Usage

1. **Clone the repository:**

    ``` bash
    git clone https://github.com/teaSummer/minecraft-locales.git
    cd minecraft-locales
    ```

2. **Create a virtual environment and install dependencies:**

    ``` bash
    uv venv && uv sync
    git submodule update --init
    cd tools/XvdTool.Streaming
    dotnet publish XvdTool.Streaming/XvdTool.Streaming.csproj -c Release -o ./x64 -r win-x64 --no-self-contained -nowarn:ca1416,ca2022,cs0168
    cd ../..
    ```

3. **Activate the virtual environment:**

    - **Windows (PowerShell):**

        ``` powershell
        .venv\Scripts\Activate.ps1
        ```

    - **macOS/Linux:**

        ``` bash
        source .venv/bin/activate
        ```

## GitHub Secret

The `CIK_DATA` secret must be configured to update *Minecraft: Bedrock Edition* locales.

To obtain `CIK_DATA`, you need run `python tools/extract_cik.py` on a Windows machine with *Minecraft: Bedrock Edition* (release and Preview) installed.

## Ends
* Inspiration: [SkyEye_FAST](https://github.com/SkyEye-FAST)
* *Bedrock Edition* data: [mcappx.com](https://mcappx.com)
