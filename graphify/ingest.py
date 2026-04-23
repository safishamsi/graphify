# fetch URLs (tweet/arxiv/pdf/web) and save as annotated markdown
from __future__ import annotations
import json
import re
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from graphify.security import safe_fetch, safe_fetch_text, validate_url


def _yaml_str(s: str) -> str:
    """Escape a string for embedding in a YAML double-quoted scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def _safe_filename(url: str, suffix: str) -> str:
    """Turn a URL into a safe filename."""
    parsed = urllib.parse.urlparse(url)
    name = parsed.netloc + parsed.path
    name = re.sub(r"[^\w\-]", "_", name).strip("_")
    name = re.sub(r"_+", "_", name)[:80]
    return name + suffix


_ANSWER_SECRET_PATTERNS = [
    re.compile(r"sk-(live|test|proj)-[A-Za-z0-9_-]{12,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}", re.IGNORECASE),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(
        r"""(?ix)
        (
            \b(?:api[_-]?key|secret|token|password|passwd|bearer)\b
            [^=\n:]{0,32}
            (?:=|:)
            [ \t]*["']?
        )
        ([A-Za-z0-9_\-./+=]{12,})
        (["']?)
        """
    ),
]


def _redact_answer_secrets(answer: str) -> str:
    """Remove credential-like substrings before persisting query memory.

    Query memory is re-ingested into future graph runs, so raw credentials must
    never be written here even if an agent accidentally included them.
    """
    redacted = answer
    for pattern in _ANSWER_SECRET_PATTERNS[:-1]:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)

    assignment_pattern = _ANSWER_SECRET_PATTERNS[-1]
    redacted = assignment_pattern.sub(r"\1[REDACTED_SECRET]\3", redacted)
    return redacted


def _detect_url_type(url: str) -> str:
    """Classify the URL for targeted extraction."""
    lower = url.lower()
    if "twitter.com" in lower or "x.com" in lower:
        return "tweet"
    if "arxiv.org" in lower:
        return "arxiv"
    if "github.com" in lower:
        return "github"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if any(path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return "webpage"


def _fetch_html(url: str) -> str:
    return safe_fetch_text(url)


def _html_to_markdown(html: str, url: str) -> str:
    """Convert HTML to clean markdown. Uses html2text if available, else basic strip."""
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html)
    except ImportError:
        # Fallback: strip tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000]


def _fetch_tweet(url: str, author: str | None, contributor: str | None) -> tuple[str, str]:
    """Fetch a tweet URL. Returns (content, filename)."""
    # Normalize to twitter.com for oEmbed
    oembed_url = url.replace("x.com", "twitter.com")
    oembed_api = f"https://publish.twitter.com/oembed?url={urllib.parse.quote(oembed_url)}&omit_script=true"
    try:
        data = json.loads(safe_fetch_text(oembed_api))
        tweet_text = re.sub(r"<[^>]+>", "", data.get("html", "")).strip()
        tweet_author = data.get("author_name", "unknown")
    except Exception:
        # oEmbed failed - save URL stub
        tweet_text = f"Tweet at {url} (could not fetch content)"
        tweet_author = "unknown"

    now = datetime.now(timezone.utc).isoformat()
    content = f"""---
source_url: "{_yaml_str(url)}"
type: tweet
author: "{_yaml_str(tweet_author)}"
captured_at: {now}
contributor: "{_yaml_str(contributor or author or 'unknown')}"
---

# Tweet by @{tweet_author}

{tweet_text}

Source: {url}
"""
    filename = _safe_filename(url, ".md")
    return content, filename


def _fetch_webpage(url: str, author: str | None, contributor: str | None) -> tuple[str, str]:
    """Fetch a generic webpage and convert to markdown."""
    html = _fetch_html(url)
    # Extract title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else url

    markdown = _html_to_markdown(html, url)
    now = datetime.now(timezone.utc).isoformat()
    content = f"""---
source_url: "{_yaml_str(url)}"
type: webpage
title: "{_yaml_str(title)}"
captured_at: {now}
contributor: "{_yaml_str(contributor or author or 'unknown')}"
---

# {title}

Source: {url}

---

{markdown[:12000]}
"""
    filename = _safe_filename(url, ".md")
    return content, filename


def _fetch_arxiv(url: str, author: str | None, contributor: str | None) -> tuple[str, str]:
    """Fetch arXiv abstract page."""
    # Convert /abs/ or /pdf/ to abs for the API
    arxiv_id = re.search(r"(\d{4}\.\d{4,5})", url)
    if arxiv_id:
        api_url = f"https://export.arxiv.org/abs/{arxiv_id.group(1)}"
        try:
            html = _fetch_html(api_url)
            abstract_match = re.search(r'class="abstract[^"]*"[^>]*>(.*?)</blockquote>', html, re.DOTALL | re.IGNORECASE)
            abstract = re.sub(r"<[^>]+>", "", abstract_match.group(1)).strip() if abstract_match else ""
            title_match = re.search(r'class="title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            title = re.sub(r"<[^>]+>", " ", title_match.group(1)).strip() if title_match else arxiv_id.group(1)
            authors_match = re.search(r'class="authors"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
            paper_authors = re.sub(r"<[^>]+>", "", authors_match.group(1)).strip() if authors_match else ""
        except Exception:
            title, abstract, paper_authors = arxiv_id.group(1), "", ""
    else:
        return _fetch_webpage(url, author, contributor)

    now = datetime.now(timezone.utc).isoformat()
    content = f"""---
source_url: "{_yaml_str(url)}"
arxiv_id: "{_yaml_str(arxiv_id.group(1) if arxiv_id else '')}"
type: paper
title: "{_yaml_str(title)}"
paper_authors: "{_yaml_str(paper_authors)}"
captured_at: {now}
contributor: "{_yaml_str(contributor or author or 'unknown')}"
---

# {title}

**Authors:** {paper_authors}
**arXiv:** {arxiv_id.group(1) if arxiv_id else url}

## Abstract

{abstract}

Source: {url}
"""
    filename = f"arxiv_{arxiv_id.group(1).replace('.', '_')}.md" if arxiv_id else _safe_filename(url, ".md")
    return content, filename


def _download_binary(url: str, suffix: str, target_dir: Path) -> Path:
    """Download a binary file (PDF, image) directly."""
    filename = _safe_filename(url, suffix)
    out_path = target_dir / filename
    out_path.write_bytes(safe_fetch(url))
    return out_path


def ingest(url: str, target_dir: Path, author: str | None = None, contributor: str | None = None) -> Path:
    """
    Fetch a URL and save it into target_dir as a graphify-ready file.

    Returns the path of the saved file.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    url_type = _detect_url_type(url)

    try:
        validate_url(url)
    except ValueError as exc:
        raise ValueError(f"ingest: {exc}") from exc

    try:
        if url_type == "pdf":
            out = _download_binary(url, ".pdf", target_dir)
            print(f"Downloaded PDF: {out.name}")
            return out

        if url_type == "image":
            suffix = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
            out = _download_binary(url, suffix, target_dir)
            print(f"Downloaded image: {out.name}")
            return out

        if url_type == "youtube":
            from graphify.transcribe import download_audio
            out = download_audio(url, target_dir)
            print(f"Downloaded audio: {out.name}")
            return out

        if url_type == "tweet":
            content, filename = _fetch_tweet(url, author, contributor)
        elif url_type == "arxiv":
            content, filename = _fetch_arxiv(url, author, contributor)
        else:
            content, filename = _fetch_webpage(url, author, contributor)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"ingest: failed to fetch {url!r}: {exc}") from exc

    out_path = target_dir / filename
    # Avoid overwriting - append counter if needed
    counter = 1
    while out_path.exists() and counter < 1000:
        stem = Path(filename).stem
        out_path = target_dir / f"{stem}_{counter}.md"
        counter += 1

    out_path.write_text(content, encoding="utf-8")
    print(f"Saved {url_type}: {out_path.name}")
    return out_path


def save_query_result(
    question: str,
    answer: str,
    memory_dir: Path,
    query_type: str = "query",
    source_nodes: list[str] | None = None,
) -> Path:
    """Save a Q&A result as markdown so it gets extracted into the graph on next --update.

    Files are stored in memory_dir (typically graphify-out/memory/) with YAML frontmatter
    that graphify's extractor reads as node metadata. This closes the feedback loop:
    the system grows smarter from both what you add AND what you ask.
    """
    memory_dir = Path(memory_dir)
    memory_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^\w]", "_", question.lower())[:50].strip("_")
    filename = f"query_{now.strftime('%Y%m%d_%H%M%S')}_{slug}.md"

    frontmatter_lines = [
        "---",
        f'type: "{query_type}"',
        f'date: "{now.isoformat()}"',
        f'question: "{_yaml_str(question)}"',
        'contributor: "graphify"',
    ]
    if source_nodes:
        nodes_str = ", ".join(f'"{n}"' for n in source_nodes[:10])
        frontmatter_lines.append(f"source_nodes: [{nodes_str}]")
    frontmatter_lines.append("---")

    body_lines = [
        "",
        f"# Q: {question}",
        "",
        "## Answer",
        "",
        _redact_answer_secrets(answer),
    ]
    if source_nodes:
        body_lines += ["", "## Source Nodes", ""]
        body_lines += [f"- {n}" for n in source_nodes]

    content = "\n".join(frontmatter_lines + body_lines)
    out_path = memory_dir / filename
    out_path.write_text(content, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch a URL into a graphify /raw folder")
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("target_dir", nargs="?", default="./raw", help="Target directory (default: ./raw)")
    parser.add_argument("--author", help="Your name (stored as node metadata)")
    parser.add_argument("--contributor", help="Contributor name for team graphs")
    args = parser.parse_args()
    out = ingest(args.url, Path(args.target_dir), author=args.author, contributor=args.contributor)
    print(f"Ready for graphify: {out}")
