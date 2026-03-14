from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class GitHubRepoRef:
    owner: str
    repo: str
    ref: str | None
    clone_url: str


_GH_HOSTS = {"github.com", "www.github.com"}


def parse_github_repo_url(repo_url: str) -> GitHubRepoRef:
    """
    Accepts:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/<ref>
    - git@github.com:owner/repo.git
    """
    repo_url = repo_url.strip()

    m = re.match(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(\.git)?$", repo_url)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        return GitHubRepoRef(
            owner=owner,
            repo=repo,
            ref=None,
            clone_url=f"https://github.com/{owner}/{repo}.git",
        )

    u = urlparse(repo_url)
    if u.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {u.scheme}")
    if u.netloc not in _GH_HOSTS:
        raise ValueError(f"Unsupported host: {u.netloc}")

    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("URL must look like https://github.com/<owner>/<repo>")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")

    ref = None
    if len(parts) >= 4 and parts[2] == "tree":
        ref = parts[3]

    return GitHubRepoRef(owner=owner, repo=repo, ref=ref, clone_url=f"https://github.com/{owner}/{repo}.git")
