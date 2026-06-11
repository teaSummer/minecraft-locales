"""Minecraft: Bedrock Edition Language File Provider.

This script is used to provide the translations for Minecraft Wiki.
"""

import os
from pathlib import Path
import subprocess

import dotenv
from mwclient import Site
import orjson
import regex as re


def main() -> None:
    dotenv.load_dotenv()
    base_dir = Path(__file__).parent
    merged_dir = base_dir.parent.parent / "bedrock" / "merged"
    changed_version = os.getenv("BEDROCK_EDITION") or (
        subprocess.run(
            [
                "pwsh",
                "-c",
                "[Environment]::GetEnvironmentVariable('BEDROCK_EDITION', 'User')",
            ]
        )
        .stdout.decode()
        .strip()
    )
    if not changed_version:
        return
    edit_as_bot = (os.getenv("EDIT_AS_BOT") or "true").lower()
    if edit_as_bot == "true":
        edit_as_bot = True
    else:
        edit_as_bot = False

    data = {"en_US": {}, "zh_CN": {}, "zh_TW": {}}
    output = {}
    output["_meta.version"] = changed_version
    pagename = "Module:NameProvider/releaseBE"
    if changed_version.count(".") > 1:
        pagename = "Module:NameProvider/development"

    for filestem in data.keys():
        file = merged_dir.joinpath(filestem + ".json")
        data[filestem] = orjson.loads(file.read_bytes())
    keys = sorted(data["en_US"].keys())
    for k in keys:
        output[k] = []
        for filestem in data.keys():
            output[k].append(data[filestem].get(k, data["en_US"][k]))
    table = ""
    for k, v in output.items():
        temp = f"{table}\n\t[ '{k}' ] = "
        if isinstance(v, list):
            v = '", "'.join(re.sub(r"\\(?!n)", r"\\\\", i).replace('"', '\\"') for i in v)
            table = '%s{ "%s" },' % (temp, v)
        else:
            table = '%s"%s",' % (temp, v)
    table = "return {%s\n}" % table

    site = Site(
        "zh.minecraft.wiki", path="/", clients_useragent=os.getenv("WIKI_USERAGENT")
    )
    site.clientlogin(
        username=os.getenv("WIKI_BOT_USERNAME"), password=os.getenv("WIKI_BOT_PASSWORD")
    )
    site.site_init()
    page = site.pages[pagename]
    page.edit(table, bot=edit_as_bot, summary="机器人：更新%s数据" % changed_version)


if __name__ == "__main__":
    main()
