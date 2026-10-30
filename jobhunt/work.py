"""Your work: projects that prove what you've done, beyond what fits on a resume.

You point jobhunt at a GitHub repo (or your GitHub profile) or pick a project folder. It reads the parts that
describe a project (README, package and build files, the file list, recent commit messages), never the whole
codebase and never secrets, and writes a short list of facts. You check the list once; after that the facts
count as true everywhere the resume does: fit scoring, letters, form answers, interview prep and the fact check.

Stored as documents with kind='work'. status 'draft' = waiting for you to check it; 'active' = in use."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePosixPath

import httpx
from pydantic import BaseModel, Field

from . import config, db, documents, llm

# Files that describe a project. Matched on the file name (lower case) anywhere in the tree.
DESCRIBE = re.compile(
    r"^(readme(\.[a-z]+)?|changelog(\.[a-z]+)?|claude\.md|agents\.md|package\.json|pyproject\.toml|requirements[\w.-]*\.txt|"
    r"setup\.py|setup\.cfg|pipfile|cargo\.toml|go\.mod|gemfile|composer\.json|pom\.xml|build\.gradle(\.kts)?|"
    r"[\w.-]+\.csproj|dockerfile|docker-compose[\w.-]*\.ya?ml|compose\.ya?ml|[\w.-]+\.uproject|manifest\.json|"
    r"projectversion\.txt|pubspec\.yaml|mix\.exs|deno\.json|tsconfig\.json)$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "target", "bin", "obj",
             "library", "temp", "logs", ".next", ".nuxt", ".cache", ".idea", ".vs", ".vscode", "coverage", "vendor",
             "packages", "data", "uploads", "screenshots", ".gradle", "pods", "deriveddata", "intermediate", "saved"}
# Never read, even if picked: secrets, keys, databases.
NEVER = re.compile(r"(^\.env|\.pem$|\.key$|\.p12$|\.pfx$|^id_rsa|^id_ed25519|secret|credential|password|token|"
                   r"\.db$|\.sqlite3?$|\.kdbx$)", re.I)
REDACT = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[private key removed]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                r"AKIA[0-9A-Z]{16}|xox[abposr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})\b"), "[key removed]"),
    (re.compile(r"(?im)^(\s*[\"']?[\w.-]*(api[_-]?key|secret|password|passwd|token)[\w.-]*[\"']?\s*[:=]\s*)\S.*$"), r"\1[removed]"),
]
MAX_FILE_CHARS = 6000
MAX_BUNDLE_CHARS = 40000
MAX_REPOS_FROM_PROFILE = 8


def redact(text: str) -> str:
    for pat, rep in REDACT:
        text = pat.sub(rep, text)
    return text


def wanted(path: str) -> bool:
    """True for a file that describes the project and is safe to read."""
    parts = [p.lower() for p in PurePosixPath(path.replace("\\", "/")).parts]
    if not parts or any(p in SKIP_DIRS for p in parts[:-1]) or len(parts) > 4:
        return False
    name = parts[-1]
    if NEVER.search(name):
        return False
    return bool(DESCRIBE.match(name)) or (len(parts) <= 3 and parts[-2:-1] == ["docs"] and name.endswith(".md"))


def skipped(path: str) -> bool:
    parts = [p.lower() for p in PurePosixPath(path.replace("\\", "/")).parts]
    return any(p in SKIP_DIRS for p in parts[:-1])


def _languages_from_tree(paths: list[str]) -> dict[str, int]:
    ext = Counter(PurePosixPath(p).suffix.lower() for p in paths if PurePosixPath(p).suffix)
    return dict(ext.most_common(12))


def bundle(name: str, files: dict[str, str], tree: list[str], extra: str = "") -> str:
    """One text block for the summarizer: what we know, capped, with secrets stripped."""
    tree = [p for p in tree if not skipped(p) and not NEVER.search(PurePosixPath(p).name)]
    out = [f"PROJECT: {name}"]
    if extra:
        out.append(extra.strip())
    if tree:
        out.append("FILE TYPES (by count): " + ", ".join(f"{k} {v}" for k, v in _languages_from_tree(tree).items()))
        out.append("FILES (first 250):\n" + "\n".join(tree[:250]))
    # READMEs first, then the rest in path order.
    order = sorted(files, key=lambda p: (0 if PurePosixPath(p).name.lower().startswith("readme") else 1, p.count("/"), p))
    for p in order:
        out.append(f"--- {p} ---\n{files[p][:MAX_FILE_CHARS]}")
    return redact("\n\n".join(out))[:MAX_BUNDLE_CHARS]


# ---- GitHub ------------------------------------------------------------------------------------------------

GH = re.compile(r"github\.com/([A-Za-z0-9-]+)(?:/([A-Za-z0-9._-]+))?", re.I)


class SourceError(Exception):
    pass


def _gh(client: httpx.Client, url: str, raw: bool = False):
    r = client.get(url, headers={"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"})
    if r.status_code == 404:
        return None
    if r.status_code in (403, 429):
        raise SourceError("GitHub says too many requests for now. Try again in an hour.")
    r.raise_for_status()
    return r.text if raw else r.json()


def github_repos(url: str) -> list[tuple[str, str]]:
    """(owner, repo) pairs for a repo link, or the newest public non-fork repos for a profile link."""
    m = GH.search(url or "")
    if not m:
        raise SourceError("That doesn't look like a GitHub link. Use github.com/you/project or github.com/you.")
    owner, repo = m.group(1), (m.group(2) or "").removesuffix(".git")
    if repo:
        return [(owner, repo)]
    with httpx.Client(timeout=20, follow_redirects=True) as c:
        rows = _gh(c, f"https://api.github.com/users/{owner}/repos?sort=pushed&per_page=30") or []
    rows = [r for r in rows if not r.get("fork") and not r.get("archived")]
    if not rows:
        raise SourceError(f"No public projects found for {owner}.")
    return [(owner, r["name"]) for r in rows[:MAX_REPOS_FROM_PROFILE]]


def github_bundle(owner: str, repo: str) -> tuple[str, str]:
    """(title, bundle text) for one public repo."""
    with httpx.Client(timeout=20, follow_redirects=True) as c:
        meta = _gh(c, f"https://api.github.com/repos/{owner}/{repo}")
        if not meta:
            raise SourceError(f"Couldn't find github.com/{owner}/{repo}. Is it public?")
        branch = meta.get("default_branch") or "HEAD"
        tree_json = _gh(c, f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1") or {}
        tree = [t["path"] for t in tree_json.get("tree", []) if t.get("type") == "blob"]
        langs = _gh(c, f"https://api.github.com/repos/{owner}/{repo}/languages") or {}
        commits = _gh(c, f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=40") or []
        files: dict[str, str] = {}
        for p in [p for p in tree if wanted(p)][:20]:
            r = c.get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{p}")
            if r.status_code == 200 and len(r.content) < 400_000:
                files[p] = r.text
    authors = Counter((x.get("commit", {}).get("author") or {}).get("name") or "?" for x in commits)
    dates = sorted((x.get("commit", {}).get("author") or {}).get("date", "")[:10] for x in commits if x.get("commit"))
    extra = "\n".join([
        f"GITHUB: github.com/{owner}/{repo}" + (" (a fork of someone else's project)" if meta.get("fork") else ""),
        f"DESCRIPTION: {meta.get('description') or ''}",
        f"TOPICS: {', '.join(meta.get('topics') or [])}",
        f"LANGUAGES (bytes): {', '.join(f'{k} {v}' for k, v in list(langs.items())[:10])}",
        f"CREATED: {(meta.get('created_at') or '')[:10]}  LAST PUSH: {(meta.get('pushed_at') or '')[:10]}  STARS: {meta.get('stargazers_count', 0)}",
        f"COMMIT AUTHORS (recent): {', '.join(f'{k} ({v})' for k, v in authors.most_common(5))}",
        f"RECENT COMMITS ({dates[0] if dates else '?'} to {dates[-1] if dates else '?'}):\n" +
        "\n".join("- " + ((x.get("commit") or {}).get("message") or "").splitlines()[0][:140] for x in commits[:40]),
    ])
    return repo, bundle(repo, files, tree, extra)


# ---- summary ------------------------------------------------------------------------------------------------

class WorkFacts(BaseModel):
    title: str = Field(description="Short project name, as a person would say it.")
    summary: str = Field(description="One plain sentence: what the project is and what it does.")
    facts: list[str] = Field(description="4-10 concrete facts about what the candidate built or did, one line each, past tense, "
                                         "each one directly shown by the evidence. Name the technologies.")
    skills: list[str] = Field(description="Technologies, languages, frameworks, APIs and tools the project clearly uses.")
    period: str = Field(default="", description="When the work happened, e.g. '2025-2026', from commit or file dates; empty if unknown.")
    unsure: str = Field(default="", description="Anything the candidate should double-check, e.g. 'several people committed; check which parts were yours'.")


SYSTEM = """You turn the evidence from one software project into a short list of facts a job seeker can use on applications.
Write only what the evidence directly shows: the README, build and package files, the file list, and commit messages.
Assume the candidate built the project unless the evidence says otherwise (a fork, or many other commit authors): then say so in 'unsure'.
Name technologies precisely. A dependency in a package or build file counts as used. If the project calls an AI or LLM API
(Anthropic/Claude, OpenAI, Gemini, local models, LangChain and similar), say that plainly in a fact: it matters to employers.
Never invent numbers, users, scale, employers, results or dates. No adjectives like 'robust' or 'cutting-edge'.
Write facts in past tense without 'I', e.g. 'Built a FastAPI web app with a SQLite database and background jobs'."""


def summarize(text: str) -> WorkFacts:
    return llm.extract(SYSTEM, text, WorkFacts, model=config.get("model_main"), effort="medium", max_tokens=2000, purpose="your work")


def as_text(w: WorkFacts) -> str:
    lines = [w.summary.strip(), ""] + [f"- {f.strip()}" for f in w.facts if f.strip()]
    if w.skills:
        lines += ["", "Skills: " + ", ".join(s.strip() for s in w.skills if s.strip())]
    if w.period:
        lines.append("When: " + w.period.strip())
    return "\n".join(lines).strip()


def save_draft(source: str, text: str) -> int:
    w = summarize(text)
    notes = source + (f"\nCheck: {w.unsure.strip()}" if w.unsure.strip() else "")
    return documents.add_document("work", w.title.strip()[:80] or "Project", as_text(w), status="draft", source="ai", notes=notes)


def add_github(url: str, log=lambda s: None) -> list[int]:
    ids = []
    repos = github_repos(url)
    for owner, repo in repos:
        log(f"reading github.com/{owner}/{repo}")
        try:
            _, text = github_bundle(owner, repo)
            ids.append(save_draft(f"github.com/{owner}/{repo}", text))
        except SourceError as e:
            if len(repos) == 1:
                raise
            log(str(e))
    return ids


def add_folder(name: str, files: dict[str, str], tree: list[str]) -> int:
    files = {p: t for p, t in files.items() if wanted(p)}
    if not files and not tree:
        raise SourceError("Nothing readable in that folder. Pick the project's main folder, the one with its README.")
    return save_draft(f"Folder: {name}", bundle(name, files, tree))


# ---- used by every prompt -----------------------------------------------------------------------------------

def active() -> list[dict]:
    return db.q("SELECT * FROM documents WHERE kind='work' AND status='active' ORDER BY updated_at DESC")


def drafts() -> list[dict]:
    return db.q("SELECT * FROM documents WHERE kind='work' AND status='draft' ORDER BY created_at DESC")


def block(limit_chars: int = 30000) -> str:
    """The candidate's checked projects, for prompts. Empty when there are none."""
    rows = active()
    if not rows:
        return ""
    parts = [f"PROJECT: {r['title']}\n{r['content'].strip()}" for r in rows]
    return ("PROJECTS AND OTHER WORK (checked by the candidate; treat as true, same as the resume):\n\n" + "\n\n".join(parts))[:limit_chars]
