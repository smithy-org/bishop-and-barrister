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
    python scripts/lookup.py --doc ipg rule 2.2
    python scripts/lookup.py --doc jar search "extra cards"
    python scripts/lookup.py --doc mtr toc
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
RULES_FILE = REFERENCE_DIR / "MagicCompRules.txt"
DOCS_DIR = Path(os.environ.get("BISHOP_AND_BARRISTER_DOCS") or REFERENCE_DIR / "docs")
# The tournament documents (level 2). Each is converted by sources.py into
# DOCS_DIR/<key>.json: {"title", "effective", "sections": [{"key", "heading", "text"}]}.
DOCS = {
    "mtr": "Magic Tournament Rules",
    "ipg": "Infraction Procedure Guide",
    "jar": "Judging at Regular REL",
}

RULE_LINE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s+(.*)$")
SECTION_LINE = re.compile(r"^(\d{3})\.\s+(\S.*)$")


def load() -> list[str]:
    if not RULES_FILE.exists():
        sys.exit(
            "Rules file not found. Download it first:\n"
            "    python scripts/update_rules.py"
        )
    return RULES_FILE.read_text(encoding="utf-8-sig").splitlines()


def body_start(lines: list[str]) -> int:
    """Skip the table of contents, which repeats the section headings.

    Rule 100.1 is the first real rule, but section header '100. General' sits
    just above it and belongs to the body too, so back up to catch it.
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
    lines = load()
    start = body_start(lines)
    target = args.number.rstrip(".")

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
        print(f"No rule found matching {args.number}.", file=sys.stderr)
        return 1

    if len(out) > args.limit:
        print("\n".join(out[: args.limit]))
        print(f"\n[truncated: {len(out) - args.limit} more lines; raise --limit to see them]")
    else:
        print("\n".join(out))
    return 0


def snippet(line: str, pattern: re.Pattern, width: int = 260) -> str:
    """Trim a long rule down to a window around the match, keeping its number."""
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
    path = DOCS_DIR / f"{doc}.json"
    if not path.exists():
        sys.exit(f"The {DOCS[doc]} isn't downloaded. Download it first:\n    python scripts/sources.py update {doc}")
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def find_sections(doc: str, ref: str) -> list[dict]:
    """The sections a reference names: a number ("2.2", "A" for Appendix A) or words from a heading.

    A number also takes its subsections ("3" gives 3, 3.1, 3.2 ...). Heading words match when they are
    part of exactly the headings returned.
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
    """The one section a citation's ref names, or None if it names none or several."""
    found = find_sections(doc, ref)
    key = ref.strip().rstrip(".").lower()
    exact = [s for s in found if s["key"].lower() == key]
    if exact:
        return exact[0]
    return found[0] if len(found) == 1 else None


def doc_rule(args) -> int:
    found = find_sections(args.doc, args.number)
    if not found:
        print(f"No section of the {DOCS[args.doc]} matches {args.number!r}. Try `--doc {args.doc} toc`.", file=sys.stderr)
        return 1
    out = []
    for s in found:
        out.append(f"{s['key']}  {s['heading']}")
        out.extend(s["text"].splitlines())
        out.append("")
    if len(out) > args.limit:
        print("\n".join(out[: args.limit]))
        print(f"\n[truncated: {len(out) - args.limit} more lines; raise --limit or ask for one subsection]")
    else:
        print("\n".join(out).rstrip())
    return 0


def doc_search(args) -> int:
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
    print(f"{len(hits)} section(s) of the {DOCS[args.doc]} mention {args.term!r}:\n")
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
    data = load_doc(args.doc)
    print(f"{data['title']} (effective {data.get('effective') or 'unknown'})")
    for s in data["sections"]:
        print(f"{s['key']}  {s['heading']}")
    return 0


def cmd_toc(args) -> int:
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--doc", choices=["cr", *DOCS], default="cr",
                        help="which document: cr (default), mtr, ipg or jar")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("rule", help="print a rule, subrule, or whole section")
    p.add_argument("number")
    p.add_argument("--limit", type=int, default=60)
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
