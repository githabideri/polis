#!/usr/bin/env python3
"""Run the installed VS interpolation code against the production patch.
Requires .NET 10 and VINTAGE_STORY (or --game). No game process or network.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--game", default=os.environ.get("VINTAGE_STORY"))
args = parser.parse_args()
if not args.game:
    parser.error("set VINTAGE_STORY or pass --game")
game = Path(args.game).resolve()
root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="polis-interpolation-test-") as tmp:
    work = Path(tmp)
    project = ET.Element("Project", Sdk="Microsoft.NET.Sdk")
    group = ET.SubElement(project, "PropertyGroup")
    ET.SubElement(group, "OutputType").text = "Exe"
    ET.SubElement(group, "TargetFramework").text = "net10.0"
    ET.SubElement(group, "EnableDefaultCompileItems").text = "false"
    items = ET.SubElement(project, "ItemGroup")
    ET.SubElement(items, "Compile", Include=str(root / "src/Compat/1.22.7/PolisInterpolationStability.cs"))
    ET.SubElement(items, "Compile", Include=str(work / "Program.cs"))
    for relative in ["VintagestoryAPI.dll", "VintagestoryLib.dll", "Mods/VSEssentials.dll", "Lib/0Harmony.dll",
                     "Lib/Newtonsoft.Json.dll", "Lib/protobuf-net.dll"]:
        dll = game / relative
        if not dll.is_file():
            raise SystemExit("Missing engine dependency: " + str(dll))
        ref = ET.SubElement(items, "Reference", Include=dll.stem)
        ET.SubElement(ref, "HintPath").text = str(dll)
    ET.ElementTree(project).write(work / "Regression.csproj")
    (work / "Program.cs").write_text(Path(__file__).with_name("Program.cs.txt").read_text())
    subprocess.run(["dotnet", "run", "--project", str(work / "Regression.csproj"), "-c", "Release"], check=True)
