"""scripts/sync-github-readme.sh against two local bare repositories and a local HTTP server."""

import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync-github-readme.sh"
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


class Site:
    """Serves /github/readme/<name>.md from `bodies`; a status other than 200 can be forced."""

    def __init__(self) -> None:
        self.bodies = {"personal": "# personal\n" + "p" * 300, "org": "# org\n" + "o" * 300}
        self.status = 200
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                name = self.path.rsplit("/", 1)[-1].removesuffix(".md")
                body = site.bodies.get(name, "").encode()
                self.send_response(site.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"


@pytest.fixture
def site() -> Iterator[Site]:
    served = Site()
    yield served
    served.server.shutdown()


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, env={**GIT_ENV, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return done.stdout.strip()


def make_remote(tmp: Path, name: str, files: dict[str, str]) -> Path:
    bare = tmp / f"{name}.git"
    git("init", "--bare", "-b", "main", str(bare), cwd=tmp)
    seed = tmp / f"seed-{name}"
    git("clone", str(bare), str(seed), cwd=tmp)
    for path, text in files.items():
        (seed / path).parent.mkdir(parents=True, exist_ok=True)
        (seed / path).write_text(text)
    git("add", "-A", cwd=seed)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init", cwd=seed)
    git("push", "origin", "HEAD:main", cwd=seed)
    return bare


@pytest.fixture
def remotes(tmp_path: Path) -> tuple[Path, Path]:
    return (
        make_remote(tmp_path, "personal", {"README.md": "old personal\n", "other.txt": "keep\n"}),
        make_remote(tmp_path, "org", {"profile/README.md": "old org\n"}),
    )


def run(site: Site, remotes: tuple[Path, Path]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(remotes[0].parent),
        **GIT_ENV,
        "README_SYNC_BASE_URL": site.url,
        "README_SYNC_REPO_PERSONAL": str(remotes[0]),
        "README_SYNC_REPO_ORG": str(remotes[1]),
    }
    return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)


def show(bare: Path, path: str) -> str:
    return git("show", f"main:{path}", cwd=bare)


def count(bare: Path) -> int:
    return int(git("rev-list", "--count", "main", cwd=bare))


def test_changed_readmes_are_committed_and_pushed(site: Site, remotes: tuple[Path, Path]) -> None:
    done = run(site, remotes)

    assert done.returncode == 0, done.stderr
    assert show(remotes[0], "README.md") == site.bodies["personal"].strip()
    assert show(remotes[1], "profile/README.md") == site.bodies["org"].strip()
    assert show(remotes[0], "other.txt") == "keep"
    assert git("log", "-1", "--format=%s", "main", cwd=remotes[0]) == (
        "chore: sync README from sandcorp.co.kr"
    )
    assert count(remotes[0]) == 2 and count(remotes[1]) == 2


def test_unchanged_readmes_make_no_commit(site: Site, remotes: tuple[Path, Path]) -> None:
    assert run(site, remotes).returncode == 0

    again = run(site, remotes)

    assert again.returncode == 0, again.stderr
    assert "personal: unchanged" in again.stdout and "org: unchanged" in again.stdout
    assert count(remotes[0]) == 2 and count(remotes[1]) == 2


def test_only_the_changed_repo_gets_a_commit(site: Site, remotes: tuple[Path, Path]) -> None:
    run(site, remotes)
    site.bodies["org"] += "\nnew line"

    assert run(site, remotes).returncode == 0

    assert count(remotes[0]) == 2 and count(remotes[1]) == 3


@pytest.mark.parametrize("status", [500, 404])
def test_bad_status_stops_without_commits(
    site: Site, remotes: tuple[Path, Path], status: int
) -> None:
    site.status = status

    done = run(site, remotes)

    assert done.returncode != 0 and f"HTTP {status}" in done.stderr
    assert count(remotes[0]) == 1 and count(remotes[1]) == 1


def test_short_body_stops_before_touching_either_repo(
    site: Site, remotes: tuple[Path, Path]
) -> None:
    site.bodies["org"] = "tiny"

    done = run(site, remotes)

    assert done.returncode != 0 and "under 200 bytes" in done.stderr
    assert show(remotes[0], "README.md") == "old personal"  # personal was fine, still not pushed
    assert count(remotes[0]) == 1 and count(remotes[1]) == 1
