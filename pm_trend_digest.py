#!/usr/bin/env python3
"""
PM Trend Digest v3
-------------------
Pulls recent posts from curated Substack + Medium RSS feeds across four
focus areas: Product Management, AI/Agentic AI, Support, Customer Success.

Key behavior:
  - Category-weighted scoring: PM and AI/Agentic AI count most, Support is
    neutral, Customer Success is intentionally down-weighted (Medium-only
    source, lowest priority per your call).
  - Skills panel uses a CURATED VOCABULARY of real PM/AI/CS/Support skill
    concepts, matched against article text — not raw word-frequency. This
    is what prevents nonsense output like "Reading" or "Continue" showing
    up as a "skill". Shows however many real skills matched (no padding).
  - Top 10 articles only, ranked by relevance: vocabulary-term hits
    (weighted by category) + a recency tiebreaker.
  - Explicit source list and explicit date range shown in the header.
  - Larger, sans-serif-only typography (no DM Mono).

Setup:
    pip install feedparser python-dateutil --break-system-packages
    python pm_trend_digest.py --days 3 --out digests/latest.html
"""

import argparse
import datetime as dt
import re

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
# Feeds — 4 focus areas. Add/remove freely.
# Customer Success is intentionally Medium-only per your call (no Gainsight).
# ---------------------------------------------------------------------------
FEEDS = {
    "Product Management": [
        ("Lenny's Newsletter", "https://www.lennysnewsletter.com/feed"),
        ("One Knight in Product", "https://www.oneknightinproduct.com/feed"),
        ("Product Growth (Aakash Gupta)", "https://www.aakashg.com/feed"),
        ("Product Coalition", "https://productcoalition.substack.com/feed"),
        ("Roman Pichler", "https://www.romanpichler.com/feed"),
        ("Medium: product-management", "https://medium.com/feed/tag/product-management"),
        ("Medium: ai-product-management", "https://medium.com/feed/tag/ai-product-management"),
    ],
    "AI / Agentic AI": [
        ("The Batch (DeepLearning.AI)", "https://www.deeplearning.ai/the-batch/feed/"),
        ("Ben's Bites", "https://www.bensbites.com/feed"),
        ("Latent Space", "https://www.latent.space/feed"),
        ("Import AI", "https://importai.substack.com/feed"),
        ("Medium: artificial-intelligence", "https://medium.com/feed/tag/artificial-intelligence"),
        ("Medium: ai-agents", "https://medium.com/feed/tag/ai-agents"),
    ],
    "Support": [
        ("Medium: customer-experience", "https://medium.com/feed/tag/customer-experience"),
        ("Medium: customer-support", "https://medium.com/feed/tag/customer-support"),
    ],
    "Customer Success": [
        ("Medium: customer-success", "https://medium.com/feed/tag/customer-success"),
    ],
}

# Category weights: PM and AI count most, Support is neutral baseline,
# Customer Success is intentionally lowest priority.
CATEGORY_WEIGHTS = {
    "Product Management": 1.5,
    "AI / Agentic AI": 1.5,
    "Support": 1.0,
    "Customer Success": 0.5,
}

# ---------------------------------------------------------------------------
# Curated skill vocabulary. Each canonical skill maps to phrase variants to
# match (case-insensitive substring match). This replaces free-text word
# frequency counting so the skills panel can ONLY ever show real, named
# PM/AI/CS/Support concepts — never leftover nouns like "Reading" or
# "Continue". Add/edit freely as your own skill priorities shift.
# ---------------------------------------------------------------------------
SKILL_VOCAB = {
    "Eval design": ["eval", "evals", "evaluation", "benchmark", "accuracy testing", "test set"],
    "Agent orchestration": ["orchestration", "multi-agent", "orchestrate", "agent workflow", "agent framework"],
    "Governance & compliance": ["governance", "compliance", "soc 2", "iso 42001", "gdpr", "hipaa", "audit"],
    "Resolution & escalation metrics": ["resolution rate", "automation rate", "escalation", "ticket deflection", "first response time"],
    "Prioritization frameworks": ["prioritization", "roadmap", "backlog", "rice score", "prioritize"],
    "Agent handoff design": ["handoff", "escalation path", "human handoff", "human in the loop"],
    "Agentic system architecture": ["architecture", "agentic architecture", "system design", "agent infrastructure", "agent design"],
    "Customer discovery & research": ["discovery", "user research", "customer interview", "voice of customer", "user interview"],
    "Pricing & packaging": ["pricing", "packaging", "usage-based pricing", "tiered pricing", "monetization"],
    "Stakeholder alignment": ["stakeholder", "cross-functional alignment", "buy-in", "alignment"],
    "Platform strategy": ["platform strategy", "platform pm", "platform thinking", "platform product"],
    "Build vs. buy decisions": ["build vs buy", "vendor evaluation", "vendor selection", "build vs. buy"],
    "Change management & adoption": ["change management", "adoption", "rollout strategy", "user adoption"],
    "Retention & expansion (NRR/GRR)": ["retention", "expansion revenue", "net revenue retention", "nrr", "grr", "churn", "renewal"],
    "Onboarding design": ["onboarding", "activation", "time to value", "user onboarding"],
    "QBR & customer reporting": ["qbr", "quarterly business review", "customer health score", "health score"],
    "Support automation strategy": ["support automation", "deflection", "self-service support", "ticket automation"],
    "Conversational AI design": ["conversational ai", "chatbot design", "voice agent", "chatbot"],
    "Prompt engineering": ["prompt engineering", "prompt design", "system prompt", "prompting"],
    "AI safety & guardrails": ["guardrail", "ai safety", "hallucination", "model risk", "safety layer"],
    "Product-led growth": ["product-led growth", "plg", "self-serve growth"],
    "Customer journey mapping": ["customer journey", "journey mapping", "touchpoint mapping"],
    "AI agent monitoring & observability": ["observability", "agent monitoring", "telemetry", "tracing"],
}


def parse_date(entry):
    for key in ("published", "updated"):
        if key in entry:
            try:
                return dateparser.parse(entry[key])
            except (ValueError, TypeError):
                pass
    return None


def fetch_recent(name, url, since, category):
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
                "category": category,
                "title": entry.get("title", "(untitled)"),
                "link": entry.get("link", ""),
                "summary": re.sub("<[^<]+?>", "", entry.get("summary", "") or "")[:280].strip(),
                "published": published,
            }
        )
    return items


def text_of(item):
    return f"{item['title']} {item['summary']}".lower()


def score_skills(all_items, top_n=3):
    """Score each curated skill using category-weighted hits. PM/AI content
    counts 1.5x, Support 1x, Customer Success 0.5x. Only returns skills that
    actually matched real content — never backfills with junk."""
    hits = {}  # skill -> {"articles": set(title), "sources": set(source), "weighted_score": float}
    for item in all_items:
        text = text_of(item)
        weight = CATEGORY_WEIGHTS.get(item["category"], 1.0)
        for skill, phrases in SKILL_VOCAB.items():
            if any(phrase in text for phrase in phrases):
                bucket = hits.setdefault(skill, {"articles": set(), "sources": set(), "weighted_score": 0.0})
                bucket["articles"].add(item["title"])
                bucket["sources"].add(item["source"])
                bucket["weighted_score"] += weight

    scored = []
    for skill, bucket in hits.items():
        # cross-source diversity adds a small bonus on top of the weighted hits
        score = bucket["weighted_score"] + len(bucket["sources"]) * 0.5
        scored.append((skill, score, bucket["sources"]))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def score_articles(all_items, top_n=10):
    """Relevance = category-weighted count of distinct skill-vocab terms
    touched (substance) + a recency tiebreaker. PM/AI articles get a boost
    relative to Customer Success articles at equal vocab-hit count."""
    most_recent = max((item["published"] for item in all_items), default=None)
    scored = []
    for item in all_items:
        text = text_of(item)
        weight = CATEGORY_WEIGHTS.get(item["category"], 1.0)
        vocab_hits = sum(
            1 for phrases in SKILL_VOCAB.values() if any(p in text for p in phrases)
        )
        recency_bonus = 0.0
        if most_recent:
            age_hours = (most_recent - item["published"]).total_seconds() / 3600
            recency_bonus = max(0.0, 1.0 - (age_hours / (24 * 7)))  # decays over a week
        relevance = (vocab_hits * 2 * weight) + recency_bonus
        scored.append((relevance, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_n]]


def build_html(since, until, all_sources, skills, top_articles, out_path):
    today = dt.date.today().isoformat()
    date_range = f"{since.strftime('%b %d, %Y')} – {until.strftime('%b %d, %Y')}"
    sources_line = ", ".join(sorted(all_sources))

    def skill_li(skill, score, sources):
        src = ", ".join(sorted(sources))
        return f"<li><span class='skill-name'>{skill}</span><span class='skill-meta'>seen across: {src}</span></li>"

    skills_html = "\n".join(skill_li(s, sc, src) for s, sc, src in skills)
    if not skills_html:
        skills_html = "<li class='empty'>No strong skill signal in this window — try a larger --days value, or expand SKILL_VOCAB.</li>"

    cards = ""
    for item in top_articles:
        date_str = item["published"].strftime("%b %d")
        cards += f"""
        <div class="card">
          <div class="card-meta">{item['source']} · {date_str}</div>
          <a class="card-title" href="{item['link']}" target="_blank">{item['title']}</a>
          <div class="card-summary">{item['summary']}…</div>
        </div>"""

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
    --muted: #a8a59c;
    --indigo: #5b5bd6;
    --indigo-soft: #9b9af2;
  }}
  body {{
    background: var(--bg);
    color: var(--fg);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 44px 28px 80px;
    max-width: 960px;
    margin-inline: auto;
    font-size: 17px;
    line-height: 1.5;
  }}
  h1 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 2.4rem;
    margin-bottom: 4px;
    color: var(--fg);
  }}
  .meta-line {{
    color: var(--muted);
    font-size: 0.95rem;
    margin-bottom: 4px;
  }}
  .sources-line {{
    color: var(--muted);
    font-size: 0.88rem;
    margin-bottom: 36px;
  }}
  h2 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 1.5rem;
    border-bottom: 1px solid #2a2a30;
    padding-bottom: 10px;
    margin-top: 48px;
  }}
  .skills-panel {{
    background: var(--panel);
    border: 1px solid #26262c;
    border-radius: 12px;
    padding: 24px 28px;
    margin-bottom: 12px;
  }}
  .skills-panel h3 {{
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--indigo-soft);
    margin: 0 0 18px;
    font-weight: 700;
  }}
  .skills-panel ol {{ padding-left: 20px; margin: 0; }}
  .skills-panel li {{ margin-bottom: 18px; font-size: 1.05rem; }}
  .skills-panel li.empty {{ list-style: none; padding-left: 0; color: var(--muted); font-size: 0.95rem; }}
  .skill-name {{
    font-weight: 700;
    font-size: 1.15rem;
  }}
  .skill-meta {{
    display: block;
    color: var(--muted);
    font-size: 0.82rem;
    margin-top: 3px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }}
  @media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: var(--panel);
    border: 1px solid #26262c;
    border-radius: 12px;
    padding: 16px 18px;
  }}
  .card-meta {{
    font-size: 0.78rem;
    color: var(--muted);
    margin-bottom: 8px;
  }}
  .card-title {{
    color: var(--fg);
    text-decoration: none;
    font-weight: 700;
    font-size: 1.05rem;
    display: block;
    margin-bottom: 8px;
  }}
  .card-title:hover {{ color: var(--indigo-soft); }}
  .card-summary {{ color: var(--muted); font-size: 0.92rem; line-height: 1.5; }}
</style>
</head>
<body>
  <h1>PM Trend Digest</h1>
  <div class="meta-line">Data window: {date_range}</div>
  <div class="sources-line">Sources: {sources_line}</div>

  <h2>Top 3 — Skills to Sharpen</h2>
  <div class="skills-panel">
    <h3>Based on what's actually showing up across sources (PM &amp; AI weighted highest, Customer Success lowest)</h3>
    <ol>{skills_html}</ol>
  </div>

  <h2>Top 10 — Most Relevant Articles</h2>
  <div class="grid">{cards}</div>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def build_digest(days, out_path):
    since = dt.datetime.now(tz=tzutc()) - dt.timedelta(days=days)
    until = dt.datetime.now(tz=tzutc())
    all_items = []
    all_sources = set()

    for category, feeds in FEEDS.items():
        print(f"Fetching: {category}")
        for name, url in feeds:
            found = fetch_recent(name, url, since, category)
            print(f"  {name}: {len(found)} new item(s)")
            all_items.extend(found)
            if found:
                all_sources.add(name)

    skills = score_skills(all_items, top_n=3)
    top_articles = score_articles(all_items, top_n=10)

    build_html(since, until, all_sources, skills, top_articles, out_path)
    print(f"\nDone. {len(all_items)} item(s) fetched, top 10 selected. Digest written to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the PM/AI/CS/Support trend digest.")
    parser.add_argument("--days", type=int, default=3, help="How many days back to pull (default: 3)")
    parser.add_argument("--out", type=str, default="pm_trend_digest.html", help="Output HTML file path")
    args = parser.parse_args()
    build_digest(args.days, args.out)
