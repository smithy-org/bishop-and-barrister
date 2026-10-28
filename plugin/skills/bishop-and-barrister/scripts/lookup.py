#!/usr/bin/env python3
"""Look things up in the Comprehensive Rules and the tournament documents without loading whole files.

The CR is about a megabyte of text, so never read it directly — use these
subcommands to pull out just the passages you need. `--doc` picks another
document, downloaded by `scripts/sources.py`: the Magic Tournament Rules (mtr),
the Infraction Procedure Guide (ipg) or Judging at Regular REL (jar).

Usage:
    python scripts/lookup.py rule 509.1a       # one rule plus its subrules
    python scripts/lookup.py rule 704          # a whole numbered section
    python scripts/lookup.py search deathtouch # rules mentioning a term
    python scripts/lookup.py glossary "First Strike"
    python scripts/lookup.py toc               # section numbers and titles
    python scripts/lookup.py rule 702.19b 702.2b      # several at once
    python scripts/lookup.py --doc ipg rule 2.2 2.3   # without Examples and Philosophy; --all for those
    python scripts/lookup.py --doc jar search "extra cards"
    python scripts/lookup.py --doc mtr toc
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import paths  # where the user's data lives

# What ships with the skill (the format files, templates) stays in its own folder. What sources.py downloads
# lives outside it, in the user's home for the skill, so a plugin update (which replaces the skill's folder)
# never throws the documents away.
REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
# Earlier versions downloaded into the skill's own reference/ folder.
LEGACY = ("MagicCompRules.txt", "version.json", "sources.json", "docs")
# The tournament documents (level 2). Each is converted by sources.py into
# paths.docs_dir()/<key>.json: {"title", "effective", "sections": [{"key", "heading", "text"}]}.
DOCS = {
    "mtr": "Magic Tournament Rules",
    "ipg": "Infraction Procedure Guide",
    "jar": "Judging at Regular REL",
}

RULE_LINE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s+(.*)$")
SECTION_LINE = re.compile(r"^(\d{3})\.\s+(\S.*)$")


def adopt_legacy_documents() -> list[str]:
    """Copy documents an earlier version downloaded into the skill folder to paths.documents().

    Only what paths.documents() lacks is copied, and the originals are left in place: a plugin's folder may be
    read-only, and a later update replaces it anyway. Nothing has to be downloaded again.

    Returns:
        The names copied, if any.
    """
    copied = []
    for name in LEGACY:
        old, new = REFERENCE_DIR / name, paths.documents() / name
        if old.exists() and not new.exists():
            paths.documents().mkdir(parents=True, exist_ok=True)
            if old.is_dir():
                shutil.copytree(old, new)
            else:
                shutil.copy2(old, new)
            copied.append(name)
    return copied


def load() -> list[str]:
    """Read the Comprehensive Rules as lines.

    Raises:
        SystemExit: When the rules haven't been downloaded.
    """
    adopt_legacy_documents()
    if not paths.rules_file().exists():
        sys.exit(
            "Rules file not found. Download it first:\n"
            "    python scripts/sources.py update"
        )
    return paths.rules_file().read_text(encoding="utf-8-sig").splitlines()


def body_start(lines: list[str]) -> int:
    """Skip the table of contents, which repeats the section headings.

    Rule 100.1 is the first real rule, but section header '100. General' sits
    just above it and belongs to the body too, so back up to catch it.

    Args:
        lines: The rules file's lines.

    Returns:
        The index of the body's first line, or 0 when rule 100.1 isn't found.
    """
    for i, line in enumerate(lines):
        if re.match(r"^100\.1\.?\s", line):
            for j in range(i, max(i - 10, -1), -1):
                if re.match(r"^100\.\s+\S", lines[j]):
                    return j
            return i
    return 0


def glossary_bounds(lines: list[str]) -> tuple[int, int]:
    """Find the real glossary, not the 'Glossary' line in the table of contents.

    Both words appear twice in the file, so scan from the end.

    Args:
        lines: The rules file's lines.

    Returns:
        (start, end): the glossary's first entry line and the line where it stops, or (-1, -1)
        when there is no glossary.
    """
    end = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "Credits":
            end = i
            break

    start = -1
    for i in range(end - 1, -1, -1):
        if lines[i].strip() == "Glossary":
            start = i + 1
            break

    return (start, end) if start != -1 else (-1, -1)


def cmd_rule(args) -> int:
    """Run `rule` on the CR: print each rule asked for.

    Args:
        args: The parsed command line: numbers and limit.

    Returns:
        0 when every rule was found, 1 otherwise.
    """
    status = 0
    for i, number in enumerate(args.numbers):
        if i:
            print()
        status |= cr_rule(number, args.limit)
    return status


def cr_rule(number: str, limit: int) -> int:
    """Print one CR rule with its subrules and examples, or a whole section for a bare number like "704".

    Args:
        number: The rule or section number.
        limit: The most lines to print before truncating.

    Returns:
        0 when the rule was found, 1 when it wasn't.

    Raises:
        SystemExit: When the rules haven't been downloaded.
    """
    lines = load()
    start = body_start(lines)
    target = number.rstrip(".")

    # A bare section number like "704" means the whole section.
    section_mode = bool(re.fullmatch(r"\d{3}", target))
    prefix = target + "." if section_mode else target

    out, seen_any = [], False
    for line in lines[start:]:
        m = RULE_LINE.match(line)
        if m:
            num = m.group(1)
            hit = num.startswith(prefix) if section_mode else (
                num == target or (num.startswith(target) and len(num) > len(target))
            )
            if hit:
                seen_any = True
                out.append(line.rstrip())
                continue
            if seen_any:
                break  # left the block we care about
        elif seen_any and line.strip().startswith("Example:"):
            out.append(line.rstrip())

    if not out:
        print(f"No rule found matching {number}.", file=sys.stderr)
        return 1

    if len(out) > limit:
        print("\n".join(out[:limit]))
        print(f"\n[truncated: {len(out) - limit} more lines; raise --limit to see them]")
    else:
        print("\n".join(out))
    return 0


def snippet(line: str, pattern: re.Pattern, width: int = 260) -> str:
    """Trim a long rule down to a window around the match, keeping its number.

    Args:
        line: A rule line from the CR.
        pattern: The search term; the window is placed around its first match.
        width: The most characters of rule text to keep.

    Returns:
        "<number>  <text>", with "..." where the text was cut; a line that isn't a rule comes back stripped.
    """
    m = RULE_LINE.match(line)
    if not m:
        return line.strip()
    number, text = m.group(1), m.group(2).strip()
    if len(text) <= width:
        return f"{number}  {text}"

    hit = pattern.search(text)
    centre = hit.start() if hit else 0
    start = max(0, centre - width // 3)
    end = min(len(text), start + width)
    excerpt = text[start:end]
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt += "..."
    return f"{number}  {excerpt}"


def cmd_search(args) -> int:
    """Run `search` on the CR: print the rules that mention a term, as snippets unless --full.

    The glossary is left out, so a hit is always a numbered rule.

    Args:
        args: The parsed command line: term, limit and full.

    Returns:
        0 when some rule mentions the term, 1 otherwise.
    """
    lines = load()
    start = body_start(lines)
    gstart, gend = glossary_bounds(lines)
    pattern = re.compile(re.escape(args.term), re.IGNORECASE)

    hits = []
    stop = gstart if gstart > start else len(lines)
    for line in lines[start:stop]:
        m = RULE_LINE.match(line)
        if m and pattern.search(line):
            hits.append(line.rstrip())

    if not hits:
        print(f"No rules mention {args.term!r}.", file=sys.stderr)
        return 1

    shown = hits[: args.limit]
    print(f"{len(hits)} rule(s) mention {args.term!r}" + (f", showing {len(shown)}:" if len(shown) < len(hits) else ":"))
    print()
    print("\n\n".join(
        line.strip() if args.full else snippet(line, pattern) for line in shown
    ))
    if len(shown) < len(hits):
        print(f"\n[{len(hits) - len(shown)} more; raise --limit or narrow the term]")
    if not args.full:
        print("\n[snippets only; use `rule <number>` for full text, or --full]")
    return 0


def cmd_glossary(args) -> int:
    """Run `glossary`: print the entries whose name matches a term, exact matches first.

    Args:
        args: The parsed command line: term and limit.

    Returns:
        0 when an entry matched, 1 otherwise.
    """
    lines = load()
    start, end = glossary_bounds(lines)
    if start == -1:
        print("Could not locate the glossary section.", file=sys.stderr)
        return 1

    term = args.term.strip().lower()
    entries, current = [], None
    for line in lines[start:end]:
        if not line.strip():
            current = None
            continue
        if current is None:
            current = [line.strip()]
            entries.append(current)
        else:
            current.append(line.strip())

    exact = [e for e in entries if e[0].lower() == term]
    partial = [e for e in entries if term in e[0].lower() and e not in exact]
    found = exact + partial

    if not found:
        print(f"No glossary entry for {args.term!r}.", file=sys.stderr)
        return 1

    for entry in found[: args.limit]:
        print(entry[0])
        for line in entry[1:]:
            print(f"    {line}")
        print()
    if len(found) > args.limit:
        print(f"[{len(found) - args.limit} more matching entries]")
    return 0


def load_doc(doc: str) -> dict:
    """Read a tournament document's converted JSON.

    Args:
        doc: The document key: "mtr", "ipg" or "jar".

    Returns:
        The document: {"title", "effective", "sections"}.

    Raises:
        SystemExit: When the document hasn't been downloaded.
    """
    adopt_legacy_documents()
    path = paths.docs_dir() / f"{doc}.json"
    if not path.exists():
        sys.exit(f"The {DOCS[doc]} isn't downloaded. Download it first:\n    python scripts/sources.py update {doc}")
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    """Collapse whitespace and lower-case, for matching heading words."""
    return re.sub(r"\s+", " ", text).strip().lower()


def find_sections(doc: str, ref: str) -> list[dict]:
    """Find the sections a reference names: a number ("2.2", "A" for Appendix A) or words from a heading.

    A number also takes its subsections ("3" gives 3, 3.1, 3.2 ...). Heading words match when they are
    part of exactly the headings returned.

    Args:
        doc: The document key.
        ref: The section number, "Appendix X", or heading words.

    Returns:
        The matching sections, in document order; empty when none match.

    Raises:
        SystemExit: When the document hasn't been downloaded.
    """
    sections = load_doc(doc)["sections"]
    key = ref.strip().rstrip(".")
    if key.lower().startswith("appendix "):
        key = key[len("appendix "):]
    exact = [s for s in sections if s["key"].lower() == key.lower()]
    if exact:
        return [s for s in sections if s["key"].lower() == key.lower() or s["key"].startswith(exact[0]["key"] + ".")]
    words = _norm(ref)
    return [s for s in sections if words and words in _norm(s["heading"])]


def doc_section(doc: str, ref: str) -> dict | None:
    """Find the one section a citation's ref names.

    An exact key wins over its subsections, so "3" names section 3, not 3.1.

    Args:
        doc: The document key.
        ref: The citation's section reference.

    Returns:
        The section, or None if the ref names none or several.

    Raises:
        SystemExit: When the document hasn't been downloaded.
    """
    found = find_sections(doc, ref)
    key = ref.strip().rstrip(".").lower()
    exact = [s for s in found if s["key"].lower() == key]
    if exact:
        return exact[0]
    return found[0] if len(found) == 1 else None


# The IPG splits each infraction into these parts. Examples and Philosophy explain the rule but don't
# change the answer, so they're left out unless asked for (--all): that roughly halves a section.
PARTS = ("Definition", "Examples", "Philosophy", "Additional Remedy")
SKIPPED_PARTS = ("Examples", "Philosophy")


def trim_parts(text: str, everything: bool) -> tuple[list[str], list[str]]:
    """Drop a section's Examples and Philosophy parts.

    Args:
        text: The section's text.
        everything: Keep every part (--all).

    Returns:
        (the lines kept, the names of the parts left out).
    """
    if everything:
        return text.splitlines(), []
    out, skipped, skipping = [], [], False
    for line in text.splitlines():
        if line.strip() in PARTS:
            skipping = line.strip() in SKIPPED_PARTS
            if skipping:
                skipped.append(line.strip())
                continue
        elif line.startswith("Upgrade:"):
            skipping = False
        if not skipping:
            out.append(line)
    return out, skipped


def version_line(doc: str) -> str:
    """Return "[<title>, effective <date>]" for a document, to head its output."""
    data = load_doc(doc)
    return f"[{data['title']}, effective {data.get('effective') or 'unknown'}]"


def doc_rule(args) -> int:
    """Run `rule` on a tournament document: print each section asked for.

    Args:
        args: The parsed command line: doc, numbers, limit and all.

    Returns:
        0 when at least one section was found, 1 otherwise. Refs that match nothing are named on stderr.
    """
    found, missing = [], []
    for ref in args.numbers:
        hits = find_sections(args.doc, ref)
        found += [s for s in hits if s not in found]
        if not hits:
            missing.append(ref)
    for ref in missing:
        print(f"No section of the {DOCS[args.doc]} matches {ref!r}. Try `--doc {args.doc} toc`.", file=sys.stderr)
    if not found:
        return 1
    out = [version_line(args.doc), ""]
    for s in found:
        out.append(f"{s['key']}  {s['heading']}")
        lines, skipped = trim_parts(s["text"], args.all)
        out.extend(lines)
        if skipped:
            out.append(f"[left out: {', '.join(skipped)}; add --all to see them]")
        out.append("")
    if len(out) > args.limit:
        print("\n".join(out[: args.limit]))
        print(f"\n[truncated: {len(out) - args.limit} more lines; raise --limit or ask for one subsection]")
    else:
        print("\n".join(out).rstrip())
    return 0


def doc_search(args) -> int:
    """Run `search` on a tournament document: print the sections that mention a term.

    Args:
        args: The parsed command line: doc, term, limit and full.

    Returns:
        0 when some section mentions the term, 1 otherwise.
    """
    pattern = re.compile(re.escape(args.term), re.IGNORECASE)
    hits = []
    for s in load_doc(args.doc)["sections"]:
        text = re.sub(r"\s+", " ", s["text"])
        for m in pattern.finditer(s["heading"] + " " + text):
            hits.append((s, m))
            break
    if not hits:
        print(f"No section of the {DOCS[args.doc]} mentions {args.term!r}.", file=sys.stderr)
        return 1
    shown = hits[: args.limit]
    print(f"{version_line(args.doc)}\n{len(hits)} section(s) of the {DOCS[args.doc]} mention {args.term!r}:\n")
    for s, _ in shown:
        text = re.sub(r"\s+", " ", s["text"])
        if args.full:
            body = text
        else:
            hit = pattern.search(text)
            start = max(0, (hit.start() if hit else 0) - 80)
            body = ("..." if start else "") + text[start:start + 260] + ("..." if start + 260 < len(text) else "")
        print(f"{s['key']}  {s['heading']}\n    {body}\n")
    if len(shown) < len(hits):
        print(f"[{len(hits) - len(shown)} more; raise --limit or narrow the term]")
    print(f"[use `--doc {args.doc} rule <section>` for full text]")
    return 0


def doc_toc(args) -> int:
    """Run `toc` on a tournament document: print its section keys and headings.

    Args:
        args: The parsed command line: doc.

    Returns:
        The exit status, always 0.
    """
    data = load_doc(args.doc)
    print(f"{data['title']} (effective {data.get('effective') or 'unknown'})")
    for s in data["sections"]:
        print(f"{s['key']}  {s['heading']}")
    return 0


def cmd_toc(args) -> int:
    """Run `toc` on the CR: print each section number and title once.

    Args:
        args: The parsed command line (unused).

    Returns:
        The exit status, always 0.
    """
    lines = load()
    start = body_start(lines)
    seen = set()
    for line in lines[start:]:
        m = SECTION_LINE.match(line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            print(f"{m.group(1)}. {m.group(2).strip()}")
    return 0


def main() -> int:
    """Run the command line, sending rule, search and toc to the --doc document's version.

    Returns:
        The exit status of the chosen command.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--doc", choices=["cr", *DOCS], default="cr",
                        help="which document: cr (default), mtr, ipg or jar")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("rule", help="print rules, subrules or whole sections (several at once is fine)")
    p.add_argument("numbers", nargs="+", metavar="number")
    p.add_argument("--limit", type=int, default=60, help="maximum lines for each rule")
    p.add_argument("--all", action="store_true", help="tournament documents: include Examples and Philosophy")
    p.set_defaults(func=cmd_rule)

    p = sub.add_parser("search", help="find rules mentioning a term")
    p.add_argument("term")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--full", action="store_true", help="print complete rule text, not snippets")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("glossary", help="print a glossary entry")
    p.add_argument("term")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_glossary)

    p = sub.add_parser("toc", help="list section numbers and titles")
    p.set_defaults(func=cmd_toc)

    args = parser.parse_args()
    if args.doc != "cr":
        doc_commands = {cmd_rule: doc_rule, cmd_search: doc_search, cmd_toc: doc_toc}
        if args.func not in doc_commands:
            parser.error("glossary is only in the CR; use --doc cr")
        return doc_commands[args.func](args)
    return args.func(args)


if __name__ == "__main__":
    # Windows consoles default to cp1252, which has no infinity sign (rule 702.186).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Output was piped into something like `head`; not an error.
        sys.stderr.close()
        sys.exit(0)
