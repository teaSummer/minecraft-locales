"""Minecraft: Java Edition Language File Provider.

This script is used to provide the translations for Minecraft Wiki.
"""

import datetime
import os
from pathlib import Path
import subprocess

import dotenv
from mwclient import Site
import orjson
import regex as re


def main() -> None:
    dotenv.load_dotenv()
    now = datetime.datetime.now(datetime.UTC)
    force_provide = (os.getenv("FORCE_PROVIDE") or "false").lower()
    if force_provide == "true":
        force_provide = True
    else:
        force_provide = False
    if now.month == 4 and now.day == 1 and not force_provide:
        return
    base_dir = Path(__file__).parent
    language_dir = base_dir.parent.parent / "java"
    changed_version = os.getenv("JAVA_EDITION") or (
        subprocess.run(
            [
                "pwsh",
                "-c",
                "[Environment]::GetEnvironmentVariable('JAVA_EDITION', 'User')",
            ],
            capture_output=True,
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

    data = {"en_us": {}, "zh_cn": {}, "zh_tw": {}, "zh_hk": {}}
    output = {}
    output["_meta.version"] = changed_version
    pagename = "Module:NameProvider/releaseJE"
    if "-" in changed_version or "w" in changed_version:
        pagename = "Module:NameProvider/snapshot"

    for filestem in data.keys():
        file = language_dir.joinpath(filestem + ".json")
        data[filestem] = orjson.loads(file.read_bytes())
    keys = data["en_us"].keys()
    for k in keys:
        output[k] = []
        for filestem in data.keys():
            output[k].append(data[filestem].get(k, data["en_us"][k]))
    table = ""
    for k, v in output.items():
        temp = "%s\n\t[ '%s' ] = " % (table, k)
        if isinstance(v, list):
            v = '", "'.join(
                re.sub(r"\\(?!n)", r"\\\\", i).replace('"', '\\"').replace("\n", "\\n")
                for i in v
            )
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
