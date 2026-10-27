#!/usr/bin/env python3
"""Download and convert the rules documents the skill reads.

| Key | Document                     | Found on                                  |
| --- | ---------------------------- | ----------------------------------------- |
| cr  | Comprehensive Rules (.txt)   | magic.wizards.com/en/rules (update_rules) |
| mtr | Magic Tournament Rules (PDF) | wpn.wizards.com/en/rules-documents        |
| ipg | Infraction Procedure Guide   | wpn.wizards.com/en/rules-documents        |
| jar | Judging at Regular REL       | blogs.magicjudges.org/rules/jar           |

Every PDF is downloaded from Wizards' own host, media.wizards.com; the pages
above only say which file is current. None of these documents ships with the
skill: they belong to Wizards and change several times a year, so each copy
downloads its own. They live outside the skill's folder, in documents/ in the
skill's home (lookup.DATA_DIR), so a plugin update keeps them. A PDF is kept in
documents/docs/<key>.pdf and converted to documents/docs/<key>.json (sections,
for lookup.py --doc). documents/sources.json
records the version of each.

When a document changes, the judge's record is rechecked (judge.py recheck
--offline), so rulings that cite a changed section are flagged. `update` and
`list` also name the reference/formats/ files whose header records an older
version of a document than the one installed.

Needs pypdf for the PDFs: pip install pypdf

Usage:
    python scripts/sources.py update            # every document, if changed
    python scripts/sources.py update ipg jar    # just these
    python scripts/sources.py update --check    # report, install nothing
    python scripts/sources.py list              # what is installed
    python scripts/sources.py convert           # re-convert the kept PDFs
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import lookup  # noqa: E402  (DOCS and DOCS_DIR)

REGISTRY = lookup.DATA_DIR / "sources.json"
UA = "bishop-and-barrister/1.0"
PDF_HOST = "https://media.wizards.com/"
PAGES = {
    "mtr": ("https://wpn.wizards.com/en/rules-documents", r"MTG_MTR_[^\"'\s<>/]*_EN\.pdf"),
    "ipg": ("https://wpn.wizards.com/en/rules-documents", r"MTG_IPG_[^\"'\s<>/]*_EN\.pdf"),
    "jar": ("https://blogs.magicjudges.org/rules/jar/", r"MTG_JAR_[^\"'\s<>/]*_EN\.pdf"),
}
EFFECTIVE = re.compile(r"(?:Effective|Updated)\s+([A-Z][a-z]+ \d{1,2}, \d{4})")
# A contents line: "2.1.   Game Play Error — Missed Trigger ....... 7" or "Appendix A—Changes ... 47".
TOC_LINE = re.compile(
    r"^\s*(?:Appendix\s+(?P<app>[A-Z])\s*[—–-]\s*|(?P<num>\d+(?:\.\d+)?)\.?\s+)?(?P<title>\S.*?)\s*\.{4,}\s*\d+\s*$"
)


def get(url: str, timeout: int = 120) -> bytes:
    """GET a URL and return its body.

    Raises:
        urllib.error.URLError: When the server can't be reached or answers with an error.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def now() -> str:
    """Return the current UTC time as an ISO 8601 string to the second, ending in Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_registry() -> dict:
    """Read documents/sources.json, or an empty registry if nothing has been installed."""
    return json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}


def save_registry(registry: dict) -> None:
    """Write documents/sources.json."""
    REGISTRY.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_pdf_url(doc: str) -> str:
    """Find the current PDF's address, read from the page that links it.

    Only Wizards' host is accepted.

    Args:
        doc: The document key: "mtr", "ipg" or "jar".

    Returns:
        The PDF's URL on media.wizards.com.

    Raises:
        SystemExit: When the page has no link to the PDF, or the link points to another host.
        urllib.error.URLError: When the page can't be fetched.
    """
    page, name = PAGES[doc]
    # The WPN page embeds its links in JSON with "/" escaped as /.
    html = get(page).decode("utf-8", errors="replace").replace("\\u002F", "/")
    found = sorted(set(re.findall(r"https:/+media\.wizards\.com/[^\"'\s<>]*?" + name, html)))
    if not found:
        raise SystemExit(f"Couldn't find the {lookup.DOCS[doc]} on {page}. The page may have changed; check it by hand.")
    url = re.sub(r"^https:/+", "https://", found[-1])
    if not url.startswith(PDF_HOST):
        raise SystemExit(f"The {lookup.DOCS[doc]} link points away from {PDF_HOST}: {url}")
    return url


# --- conversion ------------------------------------------------------------------------------


def pdf_lines(path: Path) -> list[tuple[str, bool]]:
    """Read each text line of the PDF, with whether it is entirely in a bold font.

    Lines that are only a page number are dropped.

    Args:
        path: The PDF.

    Returns:
        (text, bold) for each line, in reading order.

    Raises:
        SystemExit: When pypdf isn't installed.
    """
    try:
        import pypdf
    except ImportError:
        raise SystemExit("Reading the PDFs needs pypdf: pip install pypdf")
    lines: list[tuple[str, bool]] = []
    for page in pypdf.PdfReader(str(path)).pages:
        cur = {"y": None, "parts": [], "bold": True}

        def flush():
            """End the current line: keep it if it has text, and start a new one."""
            text ="".join(cur["parts"]).strip()
            if text:
                lines.append((text, cur["bold"]))
            cur["parts"], cur["bold"] = [], True

        def visit(text, cm, tm, font, size):
            """Collect one run of text from pypdf, starting a new line when the baseline moves.

            Args:
                text: The run's text, which may contain newlines.
                cm: The current transformation matrix.
                tm: The text matrix.
                font: The font dictionary, or None.
                size: The font size (unused; pypdf passes it).
            """
            y =round(tm[5] * cm[3] + cm[5], 1)
            if cur["y"] is not None and abs(y - cur["y"]) > 1:
                flush()
            cur["y"] = y
            for i, piece in enumerate(text.split("\n")):
                if i:
                    flush()
                cur["parts"].append(piece)
                if piece.strip() and "Bold" not in str((font or {}).get("/BaseFont", "")):
                    cur["bold"] = False

        page.extract_text(visitor_text=visit)
        flush()
    # Page numbers sit alone on a line.
    return [(t, b) for t, b in lines if not re.fullmatch(r"\d{1,3}", t)]


def squash(text: str) -> str:
    """Collapse whitespace and lower-case, so headings compare despite PDF spacing."""
    return re.sub(r"\s+", " ", text).strip().lower()


def by_contents(lines: list[str]) -> list[dict]:
    """Split a numbered document (MTR, IPG) into sections, using its own table of contents.

    Contents entries whose heading can't be found in the body are named in a warning on stderr.

    Args:
        lines: The document's text lines.

    Returns:
        One dict per section found, with "key" (such as "2.1" or "C.1"), "heading" and "text".

    Raises:
        SystemExit: When there is no table of contents.
    """
    toc, first, last, parent, child = [], None, -1, None, 0
    for i, line in enumerate(lines):
        m = TOC_LINE.match(line)
        if m:
            first = i if first is None else first
            key = m.group("app") or m.group("num")
            if key:
                parent, child = key, 0
            elif parent:
                # An unnumbered entry under a numbered one (the MTR's tiebreakers under Appendix C).
                child += 1
                key = f"{parent}.{child}"
            else:
                key = squash(m.group("title")).replace(" ", "-")
            toc.append((key, m.group("title").strip()))
            last = i
    if not toc:
        raise SystemExit("No table of contents found; the document's layout may have changed.")
    sections, current, want, skipped = [], None, 0, []
    # The IPG puts its unnumbered opening sections before the contents; collect those first.
    for line in lines[:first]:
        heading = next(((k, t) for k, t in toc[want:want + 2] if not k[0].isdigit() and squash(line) == squash(t)), None)
        if heading:
            current = {"key": heading[0], "heading": heading[1], "text": []}
            sections.append(current)
            want = toc.index(heading) + 1
        elif current is not None:
            current["text"].append(line)
    current = None
    for line in lines[last + 1:]:
        flat = squash(line)
        hit = None
        # Look a few entries ahead, so one heading the PDF garbles doesn't derail the rest.
        for j in range(want, min(want + 4, len(toc))):
            key, title = toc[j]
            prefix = squash(title)[:24]
            if key[0].isdigit():
                if re.match(re.escape(key) + r"\.?\s", flat + " ") and prefix in flat:
                    hit = j
            elif flat.startswith(("appendix " + key.lower(), prefix)) and len(flat) < len(squash(title)) + 40:
                hit = j
            if hit is not None:
                break
        if hit is not None:
            current = {"key": toc[hit][0], "heading": toc[hit][1], "text": []}
            # IPG headings carry the penalty after the title ("... Missed Trigger No Penalty").
            rest = re.sub(r"^\s*(?:Appendix\s+[A-Z]\s*[—–-]\s*|\d+(?:\.\d+)?\.?\s+)", "", line).strip()
            if squash(rest) != squash(toc[hit][1]) and squash(rest).startswith(squash(toc[hit][1])):
                current["heading"] = re.sub(r"\s+", " ", rest)
            sections.append(current)
            skipped += [k for k, _ in toc[want:hit]]
            want = hit + 1
        elif current is not None:
            current["text"].append(line)
    missing = skipped + [k for k, _ in toc[want:]]
    if missing:
        print(f"  warning: these contents entries weren't found in the body: {', '.join(missing)}", file=sys.stderr)
    return [{**s, "text": "\n".join(s["text"]).strip()} for s in sections]


def by_bold_headings(lines: list[tuple[str, bool]]) -> list[dict]:
    """Split an unnumbered document (JAR) at its bold headings, numbering them in order.

    Args:
        lines: (text, bold) pairs from pdf_lines().

    Returns:
        One dict per section, with "key", "heading" and "text"; text before the first heading
        becomes section "0", "Introduction", if there is any.
    """
    sections = [{"key": "0", "heading": "Introduction", "text": []}]
    prev_bold = False
    for text, bold in lines:
        heading = sections[-1]["heading"]
        wrapped = len(heading) > 60 and not heading.endswith((".", ":", "?", ")"))
        if bold and prev_bold and not sections[-1]["text"] and wrapped:
            sections[-1]["heading"] += " " + text  # a heading that wraps onto a second line
        elif bold:
            sections.append({"key": str(len(sections)), "heading": text, "text": []})
        else:
            sections[-1]["text"].append(text)
        prev_bold = bold
    return [{**s, "text": "\n".join(s["text"]).strip()} for s in sections if s["text"] or s["key"] != "0"]


def convert(doc: str, pdf: Path) -> dict:
    """Convert a document's PDF into the sections lookup.py --doc reads.

    Args:
        doc: The document key: "mtr", "ipg" or "jar".
        pdf: The downloaded PDF.

    Returns:
        A dict with "title", "effective" (None if the first lines don't state it) and "sections".

    Raises:
        SystemExit: When pypdf is missing or the document can't be split into sections.
    """
    lines = pdf_lines(pdf)
    head = "\n".join(t for t, _ in lines[:12])
    m = EFFECTIVE.search(head)
    if doc == "jar":
        # The title line is first; it isn't a section.
        sections = by_bold_headings(lines[2:])
    else:
        sections = by_contents([t for t, _ in lines])
    return {"title": lookup.DOCS[doc], "effective": m.group(1) if m else None, "sections": sections}


def install(doc: str, data: bytes, url: str) -> dict:
    """Keep a downloaded PDF and its conversion in documents/docs/.

    Args:
        doc: The document key.
        data: The PDF's bytes.
        url: Where it was downloaded from.

    Returns:
        The document's new registry entry. The caller saves it.

    Raises:
        SystemExit: When the conversion fails.
    """
    lookup.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    pdf = lookup.DOCS_DIR / f"{doc}.pdf"
    pdf.write_bytes(data)
    converted = convert(doc, pdf)
    (lookup.DOCS_DIR / f"{doc}.json").write_text(json.dumps(converted, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "effective": converted["effective"],
        "sections": len(converted["sections"]),
        "downloaded_at": now(),
    }


# --- commands --------------------------------------------------------------------------------


def update_pdf(doc: str, check: bool, force: bool) -> bool:
    """Download one PDF document and install it if its content changed.

    Args:
        doc: The document key: "mtr", "ipg" or "jar".
        check: Report whether there is an update without installing it.
        force: Install even if the content is unchanged.

    Returns:
        True when a new version was installed.

    Raises:
        SystemExit: When the PDF can't be found or converted.
        urllib.error.URLError: When a download fails.
    """
    registry = load_registry()
    local = registry.get(doc)
    url = find_pdf_url(doc)
    data = get(url)
    digest = hashlib.sha256(data).hexdigest()
    name = lookup.DOCS[doc]
    if local and local.get("sha256") == digest and not force:
        print(f"{name}: up to date (effective {local.get('effective')}).")
        return False
    if check:
        print(f"{name}: update available ({url.rsplit('/', 1)[-1]}). Run without --check to install it.")
        return False
    info = install(doc, data, url)
    registry[doc] = info
    save_registry(registry)
    print(f"{name}: installed, effective {info['effective']}, {info['sections']} sections, sha256 {digest[:12]}.")
    return True


def update_cr(check: bool, force: bool) -> bool:
    """Update the Comprehensive Rules by running update_rules.py.

    Args:
        check: Pass --check: report, install nothing.
        force: Pass --force: re-download regardless.

    Returns:
        True when the rules file on disk changed.

    Raises:
        subprocess.CalledProcessError: When update_rules.py fails.
    """
    before = lookup.RULES_FILE.read_bytes() if lookup.RULES_FILE.exists() else None
    args = [sys.executable, str(SCRIPTS / "update_rules.py")] + (["--check"] if check else []) + (["--force"] if force else [])
    subprocess.run(args, check=True)
    after = lookup.RULES_FILE.read_bytes() if lookup.RULES_FILE.exists() else None
    return before != after


def recheck() -> None:
    """Flag recorded rulings whose cited text changed, if the user has a record."""
    judge = SCRIPTS / "judge.py"
    print("\nRechecking recorded rulings against the new text...")
    result = subprocess.run([sys.executable, str(judge), "recheck", "--offline"], capture_output=True, text=True, encoding="utf-8")
    print((result.stdout or result.stderr).strip())


FORMATS_DIR = lookup.REFERENCE_DIR / "formats"


def installed_versions() -> dict:
    """Return the effective date of each installed document, as `list` prints it, by key."""
    versions = {doc: info.get("effective") for doc, info in load_registry().items()}
    cr = lookup.DATA_DIR / "version.json"
    if cr.exists():
        versions["cr"] = json.loads(cr.read_text(encoding="utf-8")).get("effective_date")
    return {doc: v for doc, v in versions.items() if v}


def format_header(path: Path) -> dict:
    """Read the `sources:` versions in a format file's header (see reference/formats/README.md).

    Args:
        path: The format file.

    Returns:
        The version each document was checked against, by key; empty when the file has no header.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    versions, in_sources = {}, False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("sources:"):
            in_sources = True
        elif in_sources and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            versions[key.strip()] = value.strip()
        else:
            in_sources = False
    return versions


def stale_formats(formats_dir: Path, installed: dict) -> list[tuple[str, list[str]]]:
    """Find format files checked against a different version of a document than the one installed.

    Args:
        formats_dir: The directory of format files.
        installed: The installed version of each document, from installed_versions().

    Returns:
        (file name, reasons) for each stale file, where each reason reads like "CR <checked> → <installed>".
    """
    stale = []
    for path in sorted(formats_dir.glob("*.md")):
        reasons = [f"{doc.upper()} {checked} → {installed[doc]}" for doc, checked in format_header(path).items()
                   if doc in installed and installed[doc] != checked]
        if reasons:
            stale.append((path.name, reasons))
    return stale


def report_stale_formats() -> None:
    """Print the format files that need re-checking, if any."""
    stale = stale_formats(FORMATS_DIR, installed_versions())
    if stale:
        print("\nFormat files to re-check (re-run lookup.py on the numbers they cite, then update their header):")
        for name, reasons in stale:
            print(f"  reference/formats/{name}: {'; '.join(reasons)}")


def cmd_update(args) -> int:
    """Run `update`: install each changed document, then recheck the judge's record if anything changed.

    Args:
        args: The parsed command line: docs, check and force.

    Returns:
        The exit status.
    """
    docs = args.docs or ["cr", *lookup.DOCS]
    changed = False
    for doc in docs:
        if doc == "cr":
            changed |= update_cr(args.check, args.force)
        else:
            changed |= update_pdf(doc, args.check, args.force)
    if changed and not args.check:
        recheck()
    report_stale_formats()
    return 0


def cmd_list(args) -> int:
    """Run `list`: print the installed version of each document.

    Args:
        args: The parsed command line (unused).

    Returns:
        The exit status.
    """
    registry = load_registry()
    cr = lookup.DATA_DIR / "version.json"
    if cr.exists():
        v = json.loads(cr.read_text(encoding="utf-8"))
        print(f"cr   Comprehensive Rules: effective {v.get('effective_date')}, sha256 {v.get('sha256', '')[:12]}")
    else:
        print("cr   Comprehensive Rules: not downloaded")
    for doc, name in lookup.DOCS.items():
        info = registry.get(doc)
        if info:
            print(f"{doc}  {name}: effective {info.get('effective')}, {info.get('sections')} sections, "
                  f"downloaded {info.get('downloaded_at')}, sha256 {info.get('sha256', '')[:12]}")
        else:
            print(f"{doc}  {name}: not downloaded")
    report_stale_formats()
    return 0


def cmd_convert(args) -> int:
    """Run `convert`: re-convert the kept PDFs, after a change to the conversion code.

    Args:
        args: The parsed command line: docs, defaulting to every PDF document.

    Returns:
        The exit status.
    """
    registry = load_registry()
    for doc in args.docs or list(lookup.DOCS):
        pdf = lookup.DOCS_DIR / f"{doc}.pdf"
        if not pdf.exists():
            print(f"{lookup.DOCS[doc]}: no PDF kept; run `sources.py update {doc}`.")
            continue
        converted = convert(doc, pdf)
        (lookup.DOCS_DIR / f"{doc}.json").write_text(json.dumps(converted, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        registry.setdefault(doc, {})["sections"] = len(converted["sections"])
        print(f"{lookup.DOCS[doc]}: {len(converted['sections'])} sections.")
    save_registry(registry)
    return 0


def main() -> int:
    """Run the command line.

    Returns:
        The exit status of the chosen command.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("update", help="download documents that have changed")
    p.add_argument("docs", nargs="*", choices=["cr", *lookup.DOCS], help="which documents (default: all)")
    p.add_argument("--check", action="store_true", help="report what changed, install nothing")
    p.add_argument("--force", action="store_true", help="install even if unchanged")
    p.set_defaults(func=cmd_update)
    p = sub.add_parser("list", help="show the installed version of each document")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("convert", help="re-convert the kept PDFs (after a change to this script)")
    p.add_argument("docs", nargs="*", choices=list(lookup.DOCS))
    p.set_defaults(func=cmd_convert)
    args = parser.parse_args()
    lookup.adopt_legacy_documents()  # documents downloaded into the skill folder by an earlier version
    return args.func(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except urllib.error.URLError as err:
        print(f"Network error: {err}", file=sys.stderr)
        sys.exit(1)
