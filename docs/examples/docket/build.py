"""Build a case-file page ("docket") for one recorded challenge from its event files.

Usage: python build.py <challenges/<id> folder> <output.html>
The rule file is read from ../../rules/ next to that folder.
"""
import glob, json, html, sys
from pathlib import Path

REC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
ev = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(str(REC / "0*.json")))]
rule_file = glob.glob(str(REC.parent.parent / "rules" / "*.json"))[0]
final = json.load(open(rule_file, encoding="utf-8"))

LENS = {1: "CR text", 2: "Cards and their rulings", 3: "Game-state simulation",
        4: "Counterexamples and logic", 5: "Tournament documents and formats"}
GROUND = {"not-applicable": "Not applicable", "overridden": "Overridden", "misread": "Misread",
          "wrong-fact": "Wrong fact", "missing-fact": "Missing fact", "counterexample": "Counterexample"}


def e(s):
    return html.escape(str(s), quote=True)


def hhmmss(t):
    return t[11:19] + "Z"


def src(s):
    if not s:
        return '<span class="flag">no source</span>'
    return f'<span class="cite">{e(s["doc"].upper())} {e(s["ref"])}</span>'


def steps_html(steps, label="Step"):
    out = ['<ol class="steps">']
    for st in steps:
        flags = ""
        if st.get("stipulation"):
            flags = '<span class="flag stip">stipulation</span>'
        elif st.get("assumption"):
            flags = '<span class="flag">assumption</span>'
        prem = ", ".join(st.get("premises", []))
        s = st.get("source")
        quote = ""
        if s:
            quote = f'<blockquote>{e(s["excerpt"])}<cite>{src(s)}</cite></blockquote>'
        out.append(
            f'<li><div class="sline"><b>{label} {st["id"]}</b> {flags} <span class="prem">from {e(prem)}</span></div>'
            f'<p>{e(st["conclusion"])}</p>{quote}</li>')
    out.append("</ol>")
    return "".join(out)


def judge_tag(actor):
    k = int(actor.split("-")[1])
    return f'<span class="judge">Judge {k}</span> <span class="lens">{e(LENS[k])}</span>'


def filing(evt):
    k = int(evt["actor"].split("-")[1])
    head = f'<div class="filing-head">{judge_tag(evt["actor"])}<span class="when">{hhmmss(evt["time"])} &middot; seq {evt["seq"]}</span></div>'
    if evt["refutations"]:
        body = ""
        for i, r in enumerate(evt["refutations"], 1):
            body += (f'<div class="refut"><div class="rhead"><span class="num">Refutation {i}</span>'
                     f'<span class="badge g-{e(r["ground"])}">{e(GROUND.get(r["ground"], r["ground"]))}</span>'
                     f'<span class="target">against step {r["target"]}</span></div>'
                     f'<p>{e(r["argument"])}</p>'
                     f'<details><summary>The judge\'s own sourced steps ({len(r["steps"])})</summary>{steps_html(r["steps"], "Judge step")}</details></div>')
        return f'<article class="filing">{head}{body}</article>'
    ev_html = ""
    for x in evt.get("concede_evidence", []):
        ev_html += f'<li>{src(x)} <span class="lvl">level {x.get("level", "")}</span><br><q>{e(x["excerpt"])}</q></li>'
    return (f'<article class="filing concede">{head}<div class="rhead"><span class="badge b-concede">Concedes</span>'
            f'<span class="target">no refutation filed</span></div><p>{e(evt["concedes"])}</p>'
            f'<details><summary>Evidence cited ({len(evt.get("concede_evidence", []))})</summary><ul class="evid">{ev_html}</ul></details></article>')


def report(evt):
    st = evt["standing"]
    if st:
        who = ", ".join(f'judge {s["judge"]} #{s["index"]}' for s in st)
        txt = f'Every quote re-checked against the sources. <b>{len(st)} refutations stand</b> ({e(who)}).'
    else:
        txt = 'Every quote re-checked against the sources. <b>Nothing stands.</b>'
    stage = "attack filings" if evt["stage"] == "attack" else "the user's answers"
    c = "Level 1 conflict: yes (a refutation cites a rule that contradicts the proposal)." if evt["level1_conflict"] else "No level 1 conflict."
    return (f'<aside class="verifier"><b>Verifier&rsquo;s report</b> on {stage}<span class="when">{hhmmss(evt["time"])} &middot; seq {evt["seq"]}</span>'
            f'<p>{txt} {c}</p></aside>')


def answer(evt):
    out = f'<article class="answer"><div class="filing-head"><span class="judge user">The user</span><span class="lens">answer to round {evt["round"]}</span><span class="when">{hhmmss(evt["time"])} &middot; seq {evt["seq"]}</span></div><p class="words">{e(evt["words"])}</p>'
    for r in evt["replies"]:
        kind = {"fix": "Fixed", "rebut": "Rebutted", "concede": "Conceded"}.get(r["kind"], r["kind"])
        out += (f'<div class="reply"><span class="badge b-{e(r["kind"])}">{kind}</span>'
                f'<span class="target">to judge {r["judge"]}, refutation {r["index"]}</span><p>{e(r["words"])}</p>')
        if r.get("steps"):
            out += f'<details><summary>The user\'s sourced steps</summary>{steps_html(r["steps"])}</details>'
        out += "</div>"
    out += "</article>"
    return out


def vote(evt):
    k = int(evt["actor"].split("-")[1])
    ev_html = "".join(f'<li>{src(x)}<br><q>{e(x["excerpt"])}</q></li>' for x in evt["evidence"])
    return (f'<article class="filing vote"><div class="filing-head">{judge_tag(evt["actor"])}<span class="when">{hhmmss(evt["time"])} &middot; seq {evt["seq"]}</span></div>'
            f'<div class="rhead"><span class="badge b-convinced">Convinced</span></div><p>{e(evt["reason"])}</p>'
            f'<details><summary>Evidence cited ({len(evt["evidence"])})</summary><ul class="evid">{ev_html}</ul></details></article>')


# split events by round
rounds = {1: [], 2: [], 3: []}
for x in ev[3:27]:
    rounds[x["round"]].append(x)
votes = ev[27:32]

openev, brief, confirm = ev[0], ev[1], ev[2]
case = brief["case"]
rule_stages = [("As the clerk filed it", case["rule"])]
for r in (1, 2, 3):
    a = [x for x in rounds[r] if x["type"] == "answer"][0]
    rule_stages.append((f"After the user's answer to round {r}", a["case"]["rule"]))

counts = {r: sum(len(x["refutations"]) for x in rounds[r] if x["type"] == "file") for r in rounds}
total_ref = sum(counts.values())

docket_rows = ""
for x in ev:
    t = x["type"]
    label = {"open": "Petition opened", "brief": "Clerk's brief", "confirm": "User confirms the brief",
             "file": "Judge's filing", "report": "Verifier's report", "answer": "User's answer", "vote": "Judge's settling position"}[t]
    detail = ""
    if t == "file":
        detail = f'round {x["round"]}: ' + (f'{len(x["refutations"])} refutation(s)' if x["refutations"] else "concedes")
    elif t == "report":
        detail = f'round {x["round"]}, {x["stage"]}: ' + (f'{len(x["standing"])} stand' if x["standing"] else "none stand")
    elif t == "answer":
        detail = f'round {x["round"]}: {len(x["replies"])} replies, case revised'
    elif t == "vote":
        detail = "convinced"
    docket_rows += f'<tr><td>{x["seq"]}</td><td>{hhmmss(x["time"])}</td><td>{e(x["actor"])}</td><td>{label}</td><td>{e(detail)}</td></tr>'

round_html = ""
titles = {1: "First attack", 2: "Second attack", 3: "Third attack"}
for r in (1, 2, 3):
    items = rounds[r]
    conceded = sum(1 for x in items if x["type"] == "file" and not x["refutations"])
    round_html += (f'<section class="part" id="round{r}"><h2><span class="pn">Part {r + 2}</span> {titles[r]}</h2>'
                   f'<p class="lede">{counts[r]} refutations filed, {conceded} judge(s) conceded. Each judge reads the clerk&rsquo;s case through their own lens and files either a sourced refutation or a concession with evidence.</p>')
    for x in items:
        if x["type"] == "file":
            round_html += filing(x)
        elif x["type"] == "report":
            round_html += report(x)
        elif x["type"] == "answer":
            round_html += answer(x)
    round_html += "</section>"

stage_html = ""
for i, (lab, txt) in enumerate(rule_stages):
    stage_html += f'<div class="rulestage{" last" if i == len(rule_stages) - 1 else ""}"><div class="rlabel">{e(lab)}</div><p>{e(txt)}</p></div>'

facts = "".join(f'<li><b>F{f["id"]}</b> {e(f["text"])}</li>' for f in case["facts"])
oq = "".join(f"<li>{e(q)}</li>" for q in case["open_questions"])
vote_html = "".join(vote(v) for v in votes)

page = f"""<title>Case File: Who Chooses</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Libre+Franklin:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#FBFAF7;--surface:#FFFFFF;--ink:#1C2B3A;--muted:#55606B;--line:#DCD7CB;--accent:#6B1E23;--paper:#F3EFE6;
--band:#1C2B3A;--band-fg:#FBFAF7;--band-muted:#C9D0D8;--gold:#E3C9A8;--good:#2F5D3A;--good-bg:#E6EFE6;--bad:#8C2A2F;--bad-bg:#F5E4E4;--warn:#8A5A12;--warn-bg:#F6ECD8;--info:#2A4A6B;--info-bg:#E4ECF5;
--display:'Playfair Display',Georgia,'Times New Roman',serif;--body:'Libre Franklin','Helvetica Neue',Arial,sans-serif;--mono:'IBM Plex Mono',ui-monospace,Consolas,monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#141C25;--surface:#1B2632;--ink:#E8E4DA;--muted:#A5AEB8;--line:#2F3C4A;--accent:#E3A8A0;--paper:#1F2B38;
--band:#0E141B;--band-fg:#FBFAF7;--band-muted:#B3BCC6;--gold:#E3C9A8;--good:#8FC79C;--good-bg:#1D3326;--bad:#E8A0A4;--bad-bg:#3A2024;--warn:#E3BE7C;--warn-bg:#392D16;--info:#9CC0E8;--info-bg:#1B2E44;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#141C25;--surface:#1B2632;--ink:#E8E4DA;--muted:#A5AEB8;--line:#2F3C4A;--accent:#E3A8A0;--paper:#1F2B38;
--band:#0E141B;--band-fg:#FBFAF7;--band-muted:#B3BCC6;--gold:#E3C9A8;--good:#8FC79C;--good-bg:#1D3326;--bad:#E8A0A4;--bad-bg:#3A2024;--warn:#E3BE7C;--warn-bg:#392D16;--info:#9CC0E8;--info-bg:#1B2E44;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.65;margin:0}}
.wrap{{max-width:860px;margin:0 auto;padding-inline:max(16px,env(safe-area-inset-left,0px)) max(16px,env(safe-area-inset-right,0px));padding-block:0}}
.band{{background:var(--band);color:var(--band-fg);padding-block:28px 34px}}
.band img{{width:min(340px,100%);height:auto;display:block;margin-bottom:26px}}
.court{{font-family:var(--display);letter-spacing:.14em;text-transform:uppercase;font-size:.78rem;color:var(--gold);margin:0 0 6px}}
.band h1{{font-family:var(--display);font-weight:500;font-size:clamp(1.6rem,4.4vw,2.4rem);line-height:1.2;margin:0 0 6px;text-wrap:balance}}
.caption{{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-top:22px;border:1px solid rgba(255,255,255,.28)}}
.caption>div{{padding:14px 16px;min-width:0}}
.caption>div:first-child{{border-right:1px solid rgba(255,255,255,.28)}}
.caption .k{{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--band-muted)}}
.caption .v{{font-family:var(--display);font-size:1.05rem}}
.disp{{margin-top:16px;display:flex;gap:14px 24px;flex-wrap:wrap;align-items:center}}
.stamp{{font-family:var(--display);font-weight:600;letter-spacing:.16em;border:2px solid var(--gold);color:var(--gold);padding:5px 14px;text-transform:uppercase;transform:rotate(-2deg)}}
.facts-row{{display:flex;gap:6px 22px;flex-wrap:wrap;color:var(--band-muted);font-size:.9rem}}
.facts-row b{{color:var(--band-fg);font-weight:600}}
.note{{background:var(--warn-bg);border-left:4px solid var(--warn);padding:12px 16px;margin:24px 0;font-size:.92rem}}
nav.toc{{display:flex;flex-wrap:wrap;gap:6px 18px;padding:14px 0;border-bottom:1px solid var(--line);font-size:.88rem;margin-bottom:8px}}
nav.toc a{{color:var(--accent);text-decoration:none}}
nav.toc a:hover{{text-decoration:underline}}
.part{{padding-block:30px 6px;border-bottom:1px solid var(--line)}}
h2{{font-family:var(--display);font-weight:600;font-size:clamp(1.35rem,3vw,1.75rem);line-height:1.25;margin:0 0 10px;text-wrap:balance}}
h2 .pn{{display:block;font-family:var(--body);font-weight:500;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:4px}}
h3{{font-family:var(--display);font-size:1.1rem;margin:22px 0 6px}}
.lede{{color:var(--muted);max-width:65ch}}
p{{max-width:68ch;margin:.5em 0}}
.petition{{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--accent);padding:16px 20px;font-family:var(--display);font-size:1.12rem;line-height:1.55;max-width:68ch}}
.who{{font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-family:var(--body);display:block;margin-bottom:6px}}
.box{{background:var(--surface);border:1px solid var(--line);padding:14px 18px;margin:12px 0}}
.box h4{{margin:0 0 4px;font-size:.74rem;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:600}}
.box ul,.box ol{{margin:.3em 0;padding-left:1.2em}}
.box.rule{{background:var(--paper);border-left:5px solid var(--accent)}}
.box.rule p{{font-family:var(--display);font-size:1.05rem}}
ol.steps{{list-style:none;padding:0;margin:8px 0}}
ol.steps>li{{border-top:1px dashed var(--line);padding:8px 0}}
.sline{{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}}
.prem,.when,.target,.lvl{{font-size:.8rem;color:var(--muted)}}
.when{{margin-left:auto}}
blockquote{{margin:6px 0;padding:6px 12px;border-left:3px solid var(--gold);background:var(--paper);font-family:var(--mono);font-size:.82rem;line-height:1.5;max-width:70ch}}
blockquote cite,q{{font-style:normal}}
blockquote cite{{display:block;margin-top:4px;font-family:var(--body)}}
q{{font-family:var(--mono);font-size:.8rem;color:var(--muted);quotes:none;line-height:1.5}}
.cite{{font-family:var(--mono);font-size:.78rem;background:var(--info-bg);color:var(--info);padding:1px 7px;border-radius:2px;white-space:nowrap}}
.flag{{font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;padding:1px 7px;border-radius:2px;background:var(--warn-bg);color:var(--warn)}}
.flag.stip{{background:var(--bad-bg);color:var(--bad)}}
.filing,.answer{{background:var(--surface);border:1px solid var(--line);margin:14px 0;padding:14px 18px}}
.answer{{border-left:5px solid var(--good)}}
.filing-head{{display:flex;gap:4px 12px;flex-wrap:wrap;align-items:baseline;margin-bottom:6px}}
.judge{{font-family:var(--display);font-weight:600}}
.judge.user{{color:var(--good)}}
.lens{{font-size:.85rem;color:var(--muted)}}
.refut{{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}}
.filing .refut:first-of-type{{border-top:0;margin-top:0;padding-top:0}}
.rhead{{display:flex;gap:4px 12px;flex-wrap:wrap;align-items:center}}
.num{{font-weight:600;font-size:.88rem}}
.badge{{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;padding:2px 9px;border-radius:2px;font-weight:600;background:var(--bad-bg);color:var(--bad)}}
.b-concede,.b-convinced,.b-fix,.b-rebut{{background:var(--good-bg);color:var(--good)}}
.b-rebut{{background:var(--info-bg);color:var(--info)}}
.g-misread,.g-missing-fact,.g-wrong-fact{{background:var(--warn-bg);color:var(--warn)}}
.filing.concede{{border-left:5px solid var(--good)}}
.filing.vote{{border-left:5px solid var(--good)}}
.reply{{margin:10px 0 0;padding-top:8px;border-top:1px dashed var(--line)}}
.words{{font-style:italic}}
.verifier{{background:var(--info-bg);color:var(--ink);border-left:5px solid var(--info);padding:10px 18px;margin:14px 0;font-size:.92rem}}
.verifier p{{margin:.2em 0}}
details{{margin-top:8px}}
summary{{cursor:pointer;color:var(--accent);font-size:.88rem}}
.evid{{padding-left:1.1em;font-size:.88rem}}
.evid li{{margin:8px 0}}
.rulestage{{border-left:3px solid var(--line);padding:2px 0 2px 16px;margin:14px 0}}
.rulestage.last{{border-left-color:var(--accent)}}
.rulestage p{{font-family:var(--display);font-size:1rem}}
.rlabel{{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:600}}
.tablewrap{{overflow-x:auto;margin:10px 0}}
table{{border-collapse:collapse;font-size:.84rem;min-width:560px;width:100%}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
td:first-child{{font-family:var(--mono)}}
.hash{{font-family:var(--mono);font-size:.78rem;word-break:break-all;color:var(--muted)}}
footer{{padding-block:30px 48px;color:var(--muted);font-size:.85rem}}
@media(max-width:560px){{.caption{{grid-template-columns:1fr}}.caption>div:first-child{{border-right:0;border-bottom:1px solid rgba(255,255,255,.28)}}.when{{margin-left:0}}}}
</style>
<header class="band"><div class="wrap">
<p class="court">Bishop &amp; Barrister &middot; Record of Challenges</p>
<h1>In the matter of a rule for who chooses who goes first</h1>
<div class="caption"><div><div class="k">Petitioner</div><div class="v">The user (a simulated user in an evaluation)</div></div>
<div><div class="k">Provision challenged</div><div class="v">Comprehensive Rules 103.1</div></div></div>
<div class="disp"><span class="stamp">Rule introduced</span>
<div class="facts-row"><span><b>Docket</b> {e(final["id"])}</span><span><b>Opened</b> {hhmmss(openev["time"])}</span><span><b>Closed</b> {hhmmss(ev[-1]["time"])}</span><span><b>Level</b> {final["level"]}</span></div></div>
<div class="facts-row" style="margin-top:8px"><span><b>{len(ev)}</b> events</span><span><b>3</b> attack rounds and a settling pass</span><span><b>{total_ref}</b> refutations, all verified</span><span><b>5</b> judges, unanimous</span></div>
</div></header>
<main class="wrap">
<div class="note"><b>Read this first.</b> This is a recorded evaluation run, not a real dispute. The petitioner was an AI playing a user, the clerk and the five judges were separate AI agents (Sonnet 5.5), and nobody has adopted the rule below. The words on this page are the recorded events, lightly laid out. Nothing is paraphrased except the headings.</div>
<nav class="toc"><a href="#petition">Petition</a><a href="#brief">Clerk&rsquo;s brief</a><a href="#round1">Round 1</a><a href="#round2">Round 2</a><a href="#round3">Round 3</a><a href="#settling">Settling</a><a href="#judgment">Judgment</a><a href="#docket">Docket</a></nav>

<section class="part" id="petition"><h2><span class="pn">Part 1</span> The petition</h2>
<p class="lede">Filed by the user, in their own words. This is the only thing a person writes; everything after it is the process.</p>
<div class="petition"><span class="who">Statement of the challenge &middot; {hhmmss(openev["time"])}</span>{e(openev["statement"])}</div></section>

<section class="part" id="brief"><h2><span class="pn">Part 2</span> The clerk&rsquo;s brief</h2>
<p class="lede">The clerk turns the petition into a case in the proof standard: numbered facts, the rule asked for, when it applies, what it challenges, and a chain of steps that each cite one pinned source or say plainly that they are a stipulation. The judges then attack this document.</p>
<div class="box"><h4>Facts</h4><ul style="list-style:none;padding:0">{facts}</ul></div>
<div class="box rule"><h4>Proposed rule</h4><p>{e(case["rule"])}</p></div>
<div class="box"><h4>Applies when</h4><ul>{"".join(f"<li>{e(a)}</li>" for a in case["applies_when"])}</ul><h4 style="margin-top:10px">What it challenges</h4><p style="margin:0">{e(case["challenges"])} <span class="lens">(No official answer exists, so this fills a gap. A gap rule must say so, and its gap-filling step is flagged a stipulation.)</span></p></div>
<h3>The chain of steps</h3>{steps_html(case["steps"])}
<h3>Questions the clerk left open for the petitioner</h3><div class="box"><ul>{oq}</ul></div>
<article class="answer"><div class="filing-head"><span class="judge user">The user</span><span class="lens">confirms the brief</span><span class="when">{hhmmss(confirm["time"])} &middot; seq {confirm["seq"]}</span></div><p class="words">{e(confirm["words"])}</p></article>
</section>

{round_html}

<section class="part" id="settling"><h2><span class="pn">Part 6</span> The judges settle</h2>
<p class="lede">With no refutation standing, each judge says whether they are convinced, with reasoning and evidence. Introducing a rule needs all five. These are the recorded positions, in the order they were filed.</p>
{vote_html}
<div class="note" style="background:var(--info-bg);border-left-color:var(--info)">Judge 3&rsquo;s first position was refused by the program because one quote did not match the source. It was corrected and filed again (seq 31). That is the verifier doing its job.</div>
</section>

<section class="part" id="judgment"><h2><span class="pn">Part 7</span> Judgment</h2>
<p class="lede">Five of five judges were convinced, no verified refutation stands, and the stipulation sits in a gap, so the program closes the case as <b>introduced</b>. Here is how the rule changed on the way.</p>
<h3>The rule, as it changed</h3>{stage_html}
<h3>The rule as recorded</h3>
<div class="box rule"><h4>Introduced at level {final["level"]}</h4><p>{e(final["rule"])}</p></div>
<div class="box"><h4>Stipulation, carried with the rule</h4><p>{e(final["stipulations"][0])}</p></div>
<div class="box"><h4>Opinion of the Court</h4><p>This run predates the opinion step (a pending change). It has the five settling positions above but no written opinion, no joins, concurrences or dissents. Those will appear here, in the same place, once that change merges.</p></div>
<h3>Where the chain ends</h3><p class="hash">Final hash {e(final["final_hash"])}</p>
</section>

<section class="part" id="docket" style="border-bottom:0"><h2><span class="pn">Appendix</span> The docket</h2>
<p class="lede">Every event in the record, in order. Each is a file on disk that names the hash of the one before it, so an edit anywhere breaks the chain.</p>
<div class="tablewrap"><table><thead><tr><th>Seq</th><th>Time</th><th>Actor</th><th>Event</th><th>Detail</th></tr></thead><tbody>{docket_rows}</tbody></table></div>
</section>
</main>
<footer><div class="wrap">Source: <code>multiplayer-match-who-chooses</code>, second challenge eval run (consensus model), 2026-10-27. Built from the recorded event files.</div></footer>
"""
OUT.write_text(page, encoding="utf-8")
print(len(page), "bytes")
