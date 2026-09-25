"""The config repo: services hot-reload files from target/config, and every change is a real git commit the change agent can diff.

The git dir lives OUTSIDE the work tree (target/.configrepo) so it never nests inside the project's own repo.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORK = ROOT / "target" / "config"
DEFAULT_GIT = ROOT / "target" / ".configrepo"


class ConfigRepo:
    def __init__(self, work: Path | str = DEFAULT_WORK, git_dir: Path | str = DEFAULT_GIT):
        self.work, self.git_dir = Path(work), Path(git_dir)

    def git(self, *args: str, author: str = "nightshift-chaos", when: float | None = None) -> str:
        env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_COMMITTER_NAME": author,
               "GIT_AUTHOR_EMAIL": f"{author}@example.com", "GIT_COMMITTER_EMAIL": f"{author}@example.com"}
        if when:
            iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(when)) + " +0000"
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = iso
        r = subprocess.run(["git", f"--git-dir={self.git_dir}", f"--work-tree={self.work}", *args], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    def init(self) -> str:
        if not self.git_dir.exists():
            subprocess.run(["git", "init", "-q", f"--separate-git-dir={self.git_dir}", str(self.work)], check=True, capture_output=True)
            # `git init --separate-git-dir` leaves a .git file in the work tree; keep only the external dir
            marker = self.work / ".git"
            if marker.exists():
                marker.unlink()
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "baseline: healthy configuration", author="ops")
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "--short=8", "HEAD")

    def commit_file(self, rel: str, message: str, author: str = "sam", when: float | None = None) -> str:
        self.git("add", rel)
        self.git("commit", "-q", "-m", message, author=author, when=when)
        return self.head()

    def set_yaml_key(self, service: str, key: str, value: object, message: str = "", author: str = "sam", when: float | None = None) -> str:
        path = self.work / f"{service}.yaml"
        text = path.read_text(encoding="utf8")
        line = f"{key}: {value}"
        if re.search(rf"^{re.escape(key)}:.*$", text, re.M):
            text = re.sub(rf"^{re.escape(key)}:.*$", line, text, flags=re.M)
        else:
            text += ("" if text.endswith("\n") else "\n") + line + "\n"
        path.write_text(text, encoding="utf8")
        return self.commit_file(f"{service}.yaml", message or f"{service}: set {key}={value}", author, when)

    def set_flag(self, flag: str, value: object, message: str = "", author: str = "li", when: float | None = None) -> str:
        path = self.work / "flags.json"
        flags = json.loads(path.read_text(encoding="utf8"))
        flags[flag] = str(value).lower() == "true" if isinstance(value, str) else value
        path.write_text(json.dumps(flags, indent=2) + "\n", encoding="utf8")
        return self.commit_file("flags.json", message or f"flags: {flag}={value}", author, when)

    def revert(self, sha: str) -> str:
        self.git("revert", "--no-edit", sha, author="nightshift")
        return self.head()

    def reset_to_baseline(self) -> None:
        first = self.git("rev-list", "--max-parents=0", "HEAD").splitlines()[-1]
        self.git("reset", "--hard", first)
