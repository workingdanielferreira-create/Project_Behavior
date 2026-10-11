"""
Project Behavior - whole-folder uploader (the reverse of update_game.py)
Compares EVERY file in this folder against the GitHub repo and uploads the
ones GitHub is missing or that you changed here, committed to main in parts
of up to BATCH_SIZE (500) files.
Files land at the same relative path they have in this folder, so the repo
and your PC keep the exact same layout.

Just double-click upload_game.bat after making changes on this PC.

How change detection works
--------------------------
Same trick as update_game.py: one request fetches the full repo tree (every
tracked file + its git blob SHA), and each local file's git blob SHA
(sha1 of b"blob <size>\\0" + content) is computed and compared.

  * Missing on GitHub          -> uploaded.
  * Different from GitHub      -> uploaded, UNLESS GitHub's copy was
                                  committed after your file was last
                                  modified.  That means your copy is simply
                                  out of date (run update_game.bat), so it
                                  is skipped instead of undoing newer work.
  * Same on both sides         -> left alone.

Nothing is ever deleted from GitHub.

What is never uploaded
----------------------
Everything matched by the repo's .gitignore, plus EXTRA_EXCLUDES below
(the pip-installed Lib/ folder with PyQt5/numpy, bytecode caches, your
token file, ...) and any file over MAX_FILE_MB.

Token (required for uploading)
------------------------------
Uploading needs a GitHub token with write access to this repo: a
fine-grained token with "Contents: Read and write" on Project_Behavior, or
a classic token with the "repo" scope.  Put it in the GITHUB_TOKEN env var
or in a one-line .gh_token file next to this script (the same place
update_game.py reads it from).  .gh_token.txt also works, since Notepad
adds .txt on save.  Token files are never uploaded.
"""
import base64
import fnmatch
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REPO = "workingdanielferreira-create/Project_Behavior"
BRANCH = "main"

HERE = os.path.dirname(os.path.abspath(__file__))

# Never uploaded, on top of the repo's .gitignore.  Same syntax as a
# .gitignore line: "name/" = a folder anywhere, "a/b" = a path from the
# repo root, "*.ext" = a file pattern anywhere.
EXTRA_EXCLUDES = [
    ".git/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".gh_token",
    ".gh_token.txt",
    "gh_token",
    "gh_token.txt",
    ".sync_state.json",
    "Lib/",        # pip-installed packages (PyQt5, numpy) - huge, per-PC
    "Scripts/",    # pip-generated launchers, rewritten on every pip install
]

# GitHub refuses files over 100 MB and warns from 50 MB.
MAX_FILE_MB = 50

# Files per commit.  Each finished commit is saved on GitHub straight away,
# so a big upload that gets interrupted resumes where it stopped next run.
BATCH_SIZE = 500


# --------------------------------------------------------------------------
# GitHub API
# --------------------------------------------------------------------------

# Windows hides extensions, so Notepad's "Save As .gh_token" usually
# produces .gh_token.txt; accept that and a few other natural spellings.
TOKEN_FILES = (".gh_token", ".gh_token.txt", "gh_token", "gh_token.txt")


def _read_token_file(p):
    """Token text from p, whatever encoding Notepad saved it in (UTF-8
    with/without BOM, or "Unicode" = UTF-16).  Only the first non-blank
    line counts, and surrounding quotes are dropped."""
    with open(p, "rb") as f:
        raw = f.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="ignore")
    for line in text.splitlines():
        line = line.strip().strip('"\'').strip()
        if line:
            return line
    return ""


def _token():
    """GITHUB_TOKEN env var, or a one-line token file (TOKEN_FILES) next to
    this script."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    for name in TOKEN_FILES:
        p = os.path.join(HERE, name)
        if os.path.isfile(p):
            try:
                tok = _read_token_file(p)
            except OSError:
                continue
            if tok:
                return tok
    return ""


def _token_hint():
    """Explain why no token was found: which files were looked for, and any
    file nearby that looks like a misplaced token file."""
    lines = [f"Looked in this folder:  {HERE}",
             "for a file named:       " + ", ".join(TOKEN_FILES)]
    for name in TOKEN_FILES:
        p = os.path.join(HERE, name)
        if os.path.isfile(p):
            lines.append(f"Found {name}, but it is empty.")
    near = [n for n in os.listdir(HERE)
            if "token" in n.lower() and n not in TOKEN_FILES]
    if near:
        lines.append("Possibly misnamed token file(s) here: " + ", ".join(near))
    return "\n".join(lines)


def gh(method, path, body=None):
    url = path if path.startswith("http") else \
        f"https://api.github.com/repos/{REPO}/{path}"
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "Project_Behavior-uploader",
               "Authorization": "token " + _token()}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def head_commit():
    return gh("GET", f"git/ref/heads/{BRANCH}")["object"]["sha"]


def remote_tree(commit):
    """{path: (sha, mode)} for every tracked blob at `commit`."""
    tree_sha = gh("GET", f"git/commits/{commit}")["tree"]["sha"]
    data = gh("GET", f"git/trees/{tree_sha}?recursive=1")
    if data.get("truncated"):
        print("WARNING: repo tree was truncated by GitHub; some files may "
              "be re-uploaded unnecessarily.")
    return {t["path"]: (t["sha"], t["mode"])
            for t in data.get("tree", []) if t["type"] == "blob"}


def last_commit_time(rel_path):
    """When GitHub's copy of rel_path last changed (POSIX seconds)."""
    q = urllib.parse.urlencode({"path": rel_path, "sha": BRANCH,
                                "per_page": 1})
    commits = gh("GET", f"commits?{q}")
    if not commits:
        return None
    stamp = commits[0]["commit"]["committer"]["date"]   # 2026-10-11T09:00:00Z
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp()


# --------------------------------------------------------------------------
# Local scan
# --------------------------------------------------------------------------

def _git_blob_sha(content):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def load_ignore_patterns():
    patterns = list(EXTRA_EXCLUDES)
    try:
        with open(os.path.join(HERE, ".gitignore"), "r",
                  encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith(("#", "!")):
                    patterns.append(line)
    except OSError:
        pass
    return patterns


def is_ignored(rel_path, patterns):
    """Simplified .gitignore matching (enough for this repo's rules)."""
    parts = rel_path.split("/")
    for pat in patterns:
        dir_only = pat.endswith("/")
        pat = pat.strip("/")
        if "/" in pat:
            # Anchored to the repo root: match the path or any parent of it.
            for i in range(1, len(parts) + 1):
                if dir_only and i == len(parts):
                    break
                if fnmatch.fnmatchcase("/".join(parts[:i]), pat):
                    return True
        else:
            names = parts[:-1] if dir_only else parts
            if any(fnmatch.fnmatchcase(n, pat) for n in names):
                return True
    return False


def local_files(patterns):
    """[(rel_path, abs_path)] of every uploadable file in this folder."""
    out = []
    for root, dirs, files in os.walk(HERE):
        rel_root = os.path.relpath(root, HERE).replace("\\", "/")
        rel_root = "" if rel_root == "." else rel_root + "/"
        # Prune ignored folders so huge ones (Lib/) aren't even walked.
        dirs[:] = [d for d in dirs
                   if not is_ignored(rel_root + d + "/x", patterns)]
        for name in files:
            rel = rel_root + name
            p = os.path.join(root, name)
            if os.path.islink(p) or is_ignored(rel, patterns):
                continue
            out.append((rel, p))
    return out


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------

def plan_uploads(remote):
    """Work out what to upload.  Returns (uploads, stale, too_big, failed)
    where uploads is [(rel_path, abs_path, mode)].  File contents are read
    again at upload time so thousands of files never sit in memory."""
    uploads, stale, too_big, failed = [], [], [], []
    by_lower = {p.lower(): p for p in remote}   # Windows ignores case
    patterns = load_ignore_patterns()

    for rel, path in local_files(patterns):
        try:
            if os.path.getsize(path) > MAX_FILE_MB * 1024 * 1024:
                too_big.append(rel)
                continue
            with open(path, "rb") as f:
                content = f.read()
        except OSError as e:
            failed.append(f"{rel} ({e})")
            continue

        remote_path = by_lower.get(rel.lower(), rel)
        entry = remote.get(remote_path)
        if entry is None:
            uploads.append((remote_path, path, "100644"))
            continue
        sha, mode = entry
        if _git_blob_sha(content) == sha:
            continue
        # Differs: only upload if this PC's copy is newer than GitHub's.
        try:
            remote_time = last_commit_time(remote_path)
        except Exception:
            remote_time = None
        if remote_time is not None and os.path.getmtime(path) < remote_time:
            stale.append(remote_path)
            continue
        uploads.append((remote_path, path, mode))
    return uploads, stale, too_big, failed


def push_commit(base_commit, batch, message, done, total):
    """Create blobs, a tree on top of base_commit, a commit, and move main
    to it.  Raises urllib.error.HTTPError 422 if main moved meanwhile."""
    tree_items = []
    for i, (rel, path, mode) in enumerate(batch, done + 1):
        print(f"  [{i}/{total}] {rel}")
        with open(path, "rb") as f:
            content = f.read()
        blob = gh("POST", "git/blobs", {
            "content": base64.b64encode(content).decode(),
            "encoding": "base64"})
        tree_items.append({"path": rel, "mode": mode, "type": "blob",
                           "sha": blob["sha"]})
    base_tree = gh("GET", f"git/commits/{base_commit}")["tree"]["sha"]
    tree = gh("POST", "git/trees", {"base_tree": base_tree,
                                    "tree": tree_items})
    commit = gh("POST", "git/commits", {"message": message,
                                        "tree": tree["sha"],
                                        "parents": [base_commit]})
    gh("PATCH", f"git/refs/heads/{BRANCH}", {"sha": commit["sha"],
                                              "force": False})
    return commit["sha"]


def commit_message(batch, remote, part, parts):
    new = [u[0] for u in batch if u[0] not in remote]
    changed = [u[0] for u in batch if u[0] in remote]
    title = (f"Upload from local folder: {len(new)} new, "
             f"{len(changed)} changed file(s)")
    if parts > 1:
        title += f" (part {part}/{parts})"
    lines = [title, ""]
    lines += [f"+ {p}" for p in new]
    lines += [f"~ {p}" for p in changed]
    return "\n".join(lines)


def _explain_http_error(e):
    if e.code == 401:
        return ("GitHub rejected the token (401 - revoked, expired or "
                "mis-pasted). Replace it in .gh_token.")
    if e.code in (403, 404):
        return (f"GitHub refused the upload ({e.code}). The token needs "
                "write access: 'Contents: Read and write' on "
                "Project_Behavior (fine-grained) or the 'repo' scope "
                "(classic).")
    return f"GitHub error {e.code}: {e.reason}"


def main():
    dry_run = "--dry-run" in sys.argv

    if not _token():
        print("No GitHub token found, so nothing can be uploaded.\n\n"
              + _token_hint() + "\n\n"
              "Create one at https://github.com/settings/tokens with write "
              "access\n('Contents: Read and write' on Project_Behavior) and "
              "paste it as the\nonly line of a file named .gh_token next to "
              "upload_game.py.")
        return

    for attempt in range(2):
        print("Checking GitHub for what's already there...\n")
        try:
            base = head_commit()
            remote = remote_tree(base)
            print(f"GitHub has {len(remote)} files (commit {base[:7]}). "
                  "Comparing with this folder...\n")
            uploads, stale, too_big, failed = plan_uploads(remote)
        except urllib.error.HTTPError as e:
            print(_explain_http_error(e))
            return
        except Exception as e:
            print(f"Could not reach GitHub ({e}).")
            return

        if stale:
            print("Skipped - GitHub has a NEWER version (run update_game.bat "
                  "first, then redo your change):")
            for p in stale:
                print(f"  - {p}")
            print()
        if too_big:
            print(f"Skipped - larger than {MAX_FILE_MB} MB:")
            for p in too_big:
                print(f"  - {p}")
            print()
        if failed:
            print("Could not read:")
            for p in failed:
                print(f"  - {p}")
            print()

        if not uploads:
            print("Nothing to upload - GitHub already has all your files.")
            return

        if dry_run:
            print("Would upload (dry run, nothing sent):")
            for rel, *_ in uploads:
                print(f"  {'~' if rel in remote else '+'} {rel}")
            return

        batches = [uploads[i:i + BATCH_SIZE]
                   for i in range(0, len(uploads), BATCH_SIZE)]
        print(f"Uploading {len(uploads)} file(s) to {BRANCH} in "
              f"{len(batches)} commit(s) of up to {BATCH_SIZE} files:")
        commits, done = [], 0
        try:
            for part, batch in enumerate(batches, 1):
                base = push_commit(base, batch,
                                   commit_message(batch, remote, part,
                                                  len(batches)),
                                   done, len(uploads))
                done += len(batch)
                commits.append(base)
                print(f"  -> committed part {part}/{len(batches)} "
                      f"({base[:7]})")
        except urllib.error.HTTPError as e:
            if e.code == 422 and attempt == 0:
                # Someone pushed while we were uploading: rescan on top of
                # the new commit.  Parts already committed now match GitHub,
                # so only the rest is uploaded and nothing of theirs is lost.
                print("\nGitHub changed while uploading - retrying on top "
                      "of the latest version...\n")
                time.sleep(2)
                continue
            print("\n" + _explain_http_error(e))
            _report_partial(commits, done, len(uploads))
            return
        except Exception as e:
            print(f"\nUpload failed ({e}).")
            _report_partial(commits, done, len(uploads))
            return

        print(f"\nDone - uploaded {done} file(s) in {len(commits)} "
              "commit(s):")
        for sha in commits:
            print(f"https://github.com/{REPO}/commit/{sha}")
        return


def _report_partial(commits, done, total):
    if commits:
        print(f"{done} of {total} file(s) were already saved to GitHub in "
              f"{len(commits)} commit(s). Run upload_game.bat again to "
              "upload the rest - finished parts are skipped automatically.")
    else:
        print("Nothing was changed on GitHub.")


if __name__ == "__main__":
    main()
