#!/usr/bin/env python3
"""Build bishop-and-barrister.zip, the skill as claude.ai's skills settings take it.

claude.ai wants one folder at the top of the zip, named after the skill, with SKILL.md inside, and a
description of at most 200 characters. The zip holds only what the skill needs at run time: SKILL.md,
CHALLENGE.md, the scripts, the shipped reference files and the challenge binary's pins. Tests, evals, the
docs, the Lean sources and anything downloaded stay out. `when_to_use`, which Claude Code reads beside the
description, is dropped from the zip's SKILL.md because claude.ai documents only `name` and `description`.

Usage:
    python tools/package_skill.py                          # dist/bishop-and-barrister.zip
    python tools/package_skill.py --pins pins.json         # with a release's fresh binary pins
    python tools/package_skill.py --out somewhere/skill.zip
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "bishop-and-barrister"
DESCRIPTION_LIMIT = 200
FILES = ("SKILL.md", "CHALLENGE.md", "README.md", "LICENSE", "NOTICE", "requirements.txt")
TREES = ("scripts", "reference")
# Downloaded by earlier versions into reference/, and never shipped.
DOWNLOADED = {"MagicCompRules.txt", "version.json", "sources.json", "docs", ".gitignore"}


def frontmatter(text: str) -> tuple[dict, str]:
    """Split SKILL.md into its frontmatter fields and its body.

    Args:
        text: The whole of SKILL.md.

    Returns:
        The fields (values unquoted) and the body after the closing `---`.

    Raises:
        SystemExit: When SKILL.md doesn't start with a `---` block.
    """
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        sys.exit("SKILL.md has no frontmatter block")
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        fields[key.strip()] = json.loads(value) if value.startswith('"') else value
    return fields, text[m.end():]


def skill_md_for_claude_ai() -> str:
    """SKILL.md with only the frontmatter claude.ai documents, after checking it meets claude.ai's limits.

    Returns:
        The rewritten SKILL.md.

    Raises:
        SystemExit: When the name doesn't match the folder or the description is too long.
    """
    fields, body = frontmatter((ROOT / "SKILL.md").read_text(encoding="utf-8"))
    if fields.get("name") != NAME:
        sys.exit(f"SKILL.md's name is {fields.get('name')!r}; claude.ai needs it to match the folder, {NAME!r}")
    description = fields.get("description", "")
    if not description or len(description) > DESCRIPTION_LIMIT:
        sys.exit(f"SKILL.md's description is {len(description)} characters; claude.ai allows {DESCRIPTION_LIMIT}")
    return f"---\nname: {NAME}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n{body}"


def runtime_files() -> list[Path]:
    """Every file the skill needs at run time, relative to the repository root."""
    files = [Path(f) for f in FILES if (ROOT / f).exists()]
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob("*")):
            rel = path.relative_to(ROOT)
            if path.is_file() and "__pycache__" not in rel.parts and not DOWNLOADED & set(rel.parts[1:2]):
                files.append(rel)
    return files


def build(out: Path, pins: Path | None = None) -> list[str]:
    """Write the zip.

    Args:
        out: Where to write it.
        pins: A release's pins.json to ship as challenge/binaries.json; the repository's copy if None.

    Returns:
        The names inside the zip.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{NAME}/SKILL.md", skill_md_for_claude_ai())
        for rel in runtime_files():
            if rel.as_posix() != "SKILL.md":
                z.write(ROOT / rel, f"{NAME}/{rel.as_posix()}")
        z.write(pins or ROOT / "challenge" / "binaries.json", f"{NAME}/challenge/binaries.json")
        return z.namelist()


def main() -> int:
    """Run the command line.

    Returns:
        The exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / f"{NAME}.zip")
    parser.add_argument("--pins", type=Path, help="a release's pins.json, shipped as challenge/binaries.json")
    args = parser.parse_args()
    names = build(args.out, args.pins)
    print(f"Wrote {args.out}: {len(names)} files, {args.out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
