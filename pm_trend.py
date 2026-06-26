#!/usr/bin/env python3
"""
PM Trend Digest v2 — HTML visual + Top 3 synthesis
-----------------------------------------------------
Pulls recent posts from curated Substack + Medium RSS feeds (PM, AI/agentic,
support CX), then:
  1. Renders a styled HTML digest (dark/indigo, matches @thestackedpm look)
  2. Surfaces a "Top 3" section: ranked by cross-source recurrence + recency
     - Top 3 for PM SKILL-BUILDING (what to go learn/practice)
     - Top 3 for CONTENT (what to post about), weighted toward
       build-in-public angles: show the artifact, the eval, the prompt,
       the before/after — not just commentary on someone else's trend post.
 
Why RSS, not scraping:
Substack: <pub>.substack.com/feed
Medium tag: medium.com/feed/tag/<slug>
Both public, no paywall bypass, no bot-detection cat-and-mouse.
 
Setup:
    pip install feedparser python-dateutil --break-system-packages
    python pm_trend_digest.py
    python pm_trend_digest.py --days 1 --out digest.html
 
Scheduling: see github_workflow.yml in the same folder for a daily
GitHub Actions cron — no machine of yours needs to stay on.
"""
 
import argparse
import datetime as dt
import re
from collections import Counter
 
from dateutil import parser as dateparser
from dateutil.tz import tzutc
 
try:
    import feedparser
except ImportError:
    raise SystemExit(
        "Missing dependency. Run:\n"
        "  pip install feedparser python-dateutil --break-system-packages"
    )
 
# ---------------------------------------------------------------------------
# Feeds — add/remove freely.
# ---------------------------------------------------------------------------
FEEDS = {
    "PM / AI-PM": [
        ("Lenny's Newsletter", "https://www.lennysnewsletter.com/feed"),
        ("One Knight in Product", "https://www.oneknightinproduct.com/feed"),
        ("Product Growth (Aakash Gupta)", "https://www.aakashg.com/feed"),
        ("Medium: product-management", "https://medium.com/feed/tag/product-management"),
        ("Medium: ai-product-management", "https://medium.com/feed/tag/ai-product-management"),
    ],
    "AI / Agentic": [
        ("The Batch (DeepLearning.AI)", "https://www.deeplearning.ai/the-batch/feed/"),
        ("Ben's Bites", "https://www.bensbites.com/feed"),
        ("Medium: artificial-intelligence", "https://medium.com/feed/tag/artificial-intelligence"),
        ("Medium: ai-agents", "https://medium.com/feed/tag/ai-agents"),
    ],
    "Support / CX AI": [
        ("Medium: customer-experience", "https://medium.com/feed/tag/customer-experience"),
        ("Medium: customer-support", "https://medium.com/feed/tag/customer-support"),
    ],
}
 
STOPWORDS = set(
    """a an the of to for in on with and or is are be how why what your you
    our we this that it its from as at by into about how-to new best top
    2025 2026 product management ai agent agents customer service support
    pm guide guides way ways can will just not but more most than these those
    do does did how's it's don't i'm using use uses used vs part one two""".split()
)
 
SKILL_SIGNALS = {
    "eval", "evals", "evaluation", "governance", "accuracy", "resolution",
    "metrics", "framework", "orchestration", "compliance", "architecture",
    "prioritization", "roadmap", "strategy", "discovery",
}
CONTENT_SIGNALS = {
    "agent", "agentic", "build", "shipped", "prototype", "workflow",
    "automation", "case", "playbook", "launch", "demo", "pipeline",
}
 
 
def parse_date(entry):
    for key in ("published", "updated"):
        if key in entry:
            try:
                return dateparser.parse(entry[key])
            except (ValueError, TypeError):
                pass
    return None
 
 
def fetch_recent(name, url, since):
    items = []
    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        print(f"  [skip] {name}: fetch error ({e})")
        return items
 
    if parsed.bozo and not parsed.entries:
        print(f"  [skip] {name}: could not parse feed")
        return items
 
    for entry in parsed.entries:
        published = parse_date(entry)
        if published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=tzutc())
        if published < since:
            continue
        items.append(
            {
                "source": name,
                "title": entry.get("title", "(untitled)"),
                "link": entry.get("link", ""),
                "summary": re.sub("<[^<]+?>", "", entry.get("summary", "") or "")[:280].strip(),
                "published": published,
            }
        )
    return items
 
 
def extract_keywords(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 3]
 
 
def rank_topics(all_items, top_n=3):
    freq = Counter()
    sources_by_kw = {}
 
    for item in all_items:
        text = f"{item['title']} {item['summary']}"
        kws = set(extract_keywords(text))
        for kw in kws:
            freq[kw] += 1
            sources_by_kw.setdefault(kw, set()).add(item["source"])
 
    scored = []
    for kw, count in freq.items():
        cross_source_bonus = len(sources_by_kw[kw]) * 2
        scored.append((kw, count + cross_source_bonus))
    scored.sort(key=lambda x: x[1], reverse=True)
 
    skill_topics, content_topics = [], []
    for kw, score in scored:
        if kw in SKILL_SIGNALS and len(skill_topics) < top_n:
            skill_topics.append((kw, score, sources_by_kw[kw]))
        elif kw in CONTENT_SIGNALS and len(content_topics) < top_n:
            content_topics.append((kw, score, sources_by_kw[kw]))
        if len(skill_topics) >= top_n and len(content_topics) >= top_n:
            break
 
    fallback = [k for k, _ in scored if k not in SKILL_SIGNALS and k not in CONTENT_SIGNALS]
    i = 0
    while len(skill_topics) < top_n and i < len(fallback):
        kw = fallback[i]
        skill_topics.append((kw, freq[kw], sources_by_kw[kw]))
        i += 1
    while len(content_topics) < top_n and i < len(fallback):
        kw = fallback[i]
        content_topics.append((kw, freq[kw], sources_by_kw[kw]))
        i += 1
 
    return skill_topics, content_topics
 
 
CONTENT_ANGLE_TEMPLATES = [
    "Build a small working demo around '{kw}' and post the before/after — show the prompt or eval you used, not just the take.",
    "Take one '{kw}' claim from a vendor/newsletter this week and stress-test it yourself — screenshot the result.",
    "Document your own '{kw}' workflow as a teardown: what you tried, what broke, what you'd ship differently.",
]
 
 
def build_html(days, sections, skill_topics, content_topics, out_path):
    today = dt.date.today().isoformat()
 
    def topic_li(kw, score, sources, template_idx=None):
        src = ", ".join(sorted(sources))
        extra = ""
        if template_idx is not None:
            extra = f"<div class='angle'>{CONTENT_ANGLE_TEMPLATES[template_idx % len(CONTENT_ANGLE_TEMPLATES)].format(kw=kw)}</div>"
        return f"<li><span class='kw'>{kw}</span><span class='meta'>mentioned across: {src}</span>{extra}</li>"
 
    skill_html = "\n".join(topic_li(kw, s, src) for kw, s, src in skill_topics)
    content_html = "\n".join(
        topic_li(kw, s, src, i) for i, (kw, s, src) in enumerate(content_topics)
    )
 
    sections_html = ""
    for category, items in sections.items():
        if not items:
            continue
        cards = ""
        for item in items:
            date_str = item["published"].strftime("%b %d")
            cards += f"""
            <div class="card">
              <div class="card-meta">{item['source']} · {date_str}</div>
              <a class="card-title" href="{item['link']}" target="_blank">{item['title']}</a>
              <div class="card-summary">{item['summary']}…</div>
            </div>"""
        sections_html += f"<h2>{category}</h2><div class='grid'>{cards}</div>"
 
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PM Trend Digest — {today}</title>
<style>
  :root {{
    --bg: #0d0d0f;
    --panel: #16161a;
    --fg: #f5f3ee;
    --muted: #9a978f;
    --indigo: #5b5bd6;
    --indigo-soft: #8b8af0;
  }}
  body {{
    background: var(--bg);
    color: var(--fg);
    font-family: 'DM Sans', -apple-system, sans-serif;
    margin: 0;
    padding: 40px 24px 80px;
    max-width: 920px;
    margin-inline: auto;
  }}
  h1 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 2.1rem;
    margin-bottom: 0;
    color: var(--fg);
  }}
  .subtitle {{
    color: var(--muted);
    font-family: 'DM Mono', monospace;
    font-size: 0.85rem;
    margin-top: 6px;
    margin-bottom: 36px;
  }}
  h2 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 1.3rem;
    border-bottom: 1px solid #2a2a30;
    padding-bottom: 8px;
    margin-top: 44px;
  }}
  .top3-wrap {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 12px;
  }}
  @media (max-width: 640px) {{ .top3-wrap {{ grid-template-columns: 1fr; }} }}
  .top3-panel {{
    background: var(--panel);
    border: 1px solid #26262c;
    border-radius: 10px;
    padding: 18px 20px;
  }}
  .top3-panel h3 {{
    font-family: 'DM Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.75rem;
    color: var(--indigo-soft);
    margin: 0 0 12px;
  }}
  .top3-panel ol {{ padding-left: 18px; margin: 0; }}
  .top3-panel li {{ margin-bottom: 16px; }}
  .kw {{
    font-weight: 600;
    text-transform: capitalize;
    font-size: 1.02rem;
  }}
  .meta {{
    display: block;
    color: var(--muted);
    font-size: 0.78rem;
    font-family: 'DM Mono', monospace;
    margin-top: 2px;
  }}
  .angle {{
    margin-top: 6px;
    font-size: 0.88rem;
    color: var(--fg);
    background: #1c1c22;
    border-left: 2px solid var(--indigo);
    padding: 8px 10px;
    border-radius: 4px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }}
  @media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: var(--panel);
    border: 1px solid #26262c;
    border-radius: 10px;
    padding: 14px 16px;
  }}
  .card-meta {{
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  .card-title {{
    color: var(--fg);
    text-decoration: none;
    font-weight: 600;
    display: block;
    margin-bottom: 6px;
  }}
  .card-title:hover {{ color: var(--indigo-soft); }}
  .card-summary {{ color: var(--muted); font-size: 0.85rem; line-height: 1.4; }}
</style>
</head>
<body>
  <h1>PM Trend Digest</h1>
  <div class="subtitle">{today} · last {days} day(s) · The Operator PM lens</div>
 
  <div class="top3-wrap">
    <div class="top3-panel">
      <h3>Top 3 — sharpen this skill</h3>
      <ol>{skill_html or '<li>No strong signal yet — widen --days.</li>'}</ol>
    </div>
    <div class="top3-panel">
      <h3>Top 3 — post about this (build-in-public)</h3>
      <ol>{content_html or '<li>No strong signal yet — widen --days.</li>'}</ol>
    </div>
  </div>
 
  {sections_html}
</body>
</html>"""
 
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
 
 
def build_digest(days, out_path):
    since = dt.datetime.now(tz=tzutc()) - dt.timedelta(days=days)
    sections = {}
    all_items = []
 
    for category, feeds in FEEDS.items():
        print(f"Fetching: {category}")
        section_items = []
        for name, url in feeds:
            found = fetch_recent(name, url, since)
            print(f"  {name}: {len(found)} new item(s)")
            section_items.extend(found)
        section_items.sort(key=lambda x: x["published"], reverse=True)
        sections[category] = section_items
        all_items.extend(section_items)
 
    skill_topics, content_topics = rank_topics(all_items)
    build_html(days, sections, skill_topics, content_topics, out_path)
    print(f"\nDone. {len(all_items)} item(s) across feeds. Digest written to {out_path}")
 
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a visual PM/AI trend digest.")
    parser.add_argument("--days", type=int, default=2, help="How many days back to pull (default: 2)")
    parser.add_argument("--out", type=str, default="pm_trend_digest.html", help="Output HTML file path")
    args = parser.parse_args()
    build_digest(args.days, args.out)
