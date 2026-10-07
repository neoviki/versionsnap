# MIT License - Copyright (c) 2010 Vignesh | VIKI - https://www.viki.design
"""Storage layer for versionsnap.

Handles the version index (versions/.versionsnap.json), version numbering
(including branches), scanning directory trees, comparing them, and copying
or restoring files.
"""

from __future__ import annotations

import filecmp
import fnmatch
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

VERSIONS_DIR = "versions"
INDEX_NAME = ".versionsnap.json"
IGNORE_FILE = ".versionsnapignore"
ROOT_EXCLUDES = (".git", VERSIONS_DIR)  # only excluded at the project root

Id = Tuple[int, ...]
Entry = Tuple[str, str]  # (kind, absolute path); kind: f=file, l=symlink, d=empty dir

DIR_RE = re.compile(r"^v(\d+(?:\.\d+)*)(?:\.([A-Za-z][A-Za-z0-9_-]*))?$")
ID_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")


class UserError(Exception):
    """An error that is shown to the user without a traceback."""


# --------------------------------------------------------------------------
# Version ids:  v1.2.3 = trunk,  v1.2.3.1.1 = branch 1 off v1.2.3, seq 1
# --------------------------------------------------------------------------

def parse_id(text: str) -> Optional[Id]:
    m = ID_RE.match(text)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def fmt_id(t: Id) -> str:
    return "v" + ".".join(str(x) for x in t)


def key(vid: str) -> Id:
    t = parse_id(vid)
    assert t is not None
    return t


def continuation(t: Id) -> Id:
    """The version that normally follows t on the same line."""
    if len(t) == 3:
        i, j, k = t
        k += 1
        if k > 9:
            k, j = 0, j + 1
        if j > 9:
            j, i = 0, i + 1
        return (i, j, k)
    return t[:-1] + (t[-1] + 1,)


# --------------------------------------------------------------------------
# Scanning and comparing trees
# --------------------------------------------------------------------------

class Excludes:
    """Built-in root excludes plus optional patterns from .versionsnapignore."""

    def __init__(self, root: Path):
        self.patterns: List[str] = []
        f = root / IGNORE_FILE
        if f.is_file():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    self.patterns.append(line.rstrip("/"))

    def skip(self, rel: str) -> bool:
        if rel in ROOT_EXCLUDES:
            return True
        base = rel.rsplit("/", 1)[-1]
        return any(
            fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(base, p)
            for p in self.patterns
        )


def scan(root: Path, ex: Excludes) -> Dict[str, Entry]:
    """Map relative path -> (kind, absolute path). Empty dirs end with '/'."""
    out: Dict[str, Entry] = {}
    base = str(root)
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        kept = 0
        keep_dirs = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if ex.skip(rel):
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                out[rel] = ("l", full)
            else:
                keep_dirs.append(name)
            kept += 1
        dirnames[:] = keep_dirs
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if ex.skip(rel):
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                out[rel] = ("l", full)
            elif os.path.isfile(full):
                out[rel] = ("f", full)
            else:
                continue
            kept += 1
        if rel_dir and kept == 0:
            out[rel_dir + "/"] = ("d", dirpath)
    return out


def same(a: Entry, b: Entry) -> bool:
    (ka, pa), (kb, pb) = a, b
    if ka != kb:
        return False
    if ka == "d":
        return True
    try:
        if ka == "l":
            return os.readlink(pa) == os.readlink(pb)
        sa, sb = os.stat(pa), os.stat(pb)
        if sa.st_size != sb.st_size:
            return False
        if sa.st_mtime_ns == sb.st_mtime_ns:
            return True
        return filecmp.cmp(pa, pb, shallow=False)
    except OSError:
        return False


@dataclass
class Changes:
    added: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    def counts(self) -> Tuple[int, int, int]:
        """(added, modified, deleted) counting files only, not empty dirs."""
        def n(items: List[str]) -> int:
            return sum(1 for r in items if not r.endswith("/"))
        return n(self.added), n(self.modified), n(self.deleted)


def compare(old: Dict[str, Entry], new: Dict[str, Entry]) -> Changes:
    """What changed going from old to new."""
    ch = Changes()
    for rel, ent in new.items():
        o = old.get(rel)
        if o is None:
            ch.added.append(rel)
        elif not same(o, ent):
            ch.modified.append(rel)
    ch.deleted = [r for r in old if r not in new]
    # An empty-dir marker is noise when the other side has files inside it.
    new_paths, old_paths = list(new), list(old)
    ch.deleted = [r for r in ch.deleted
                  if not (r.endswith("/") and any(p.startswith(r) for p in new_paths))]
    ch.added = [r for r in ch.added
                if not (r.endswith("/") and any(p.startswith(r) for p in old_paths))]
    ch.added.sort()
    ch.modified.sort()
    ch.deleted.sort()
    return ch


def stats(cur: Dict[str, Entry], old: Dict[str, Entry]) -> dict:
    size = 0
    files = 0
    for kind, path in cur.values():
        if kind == "d":
            continue
        files += 1
        try:
            size += os.lstat(path).st_size
        except OSError:
            pass
    a, m, d = compare(old, cur).counts()
    return {"files": files, "size": size, "added": a, "modified": m, "deleted": d}


def _remove_path(p: Path) -> None:
    if os.path.islink(p) or os.path.isfile(p):
        os.unlink(p)
    elif os.path.isdir(p):
        shutil.rmtree(p)


def _prune_empty_parents(p: Path, stop: Path) -> None:
    while p != stop and stop in p.parents:
        try:
            os.rmdir(p)
        except OSError:
            break
        p = p.parent


def apply(dst: Path, new: Dict[str, Entry], ch: Changes) -> List[str]:
    """Make dst match `new` by applying ch. Returns a list of error messages."""
    errors: List[str] = []
    for rel in sorted(ch.deleted, reverse=True):
        target = dst / rel.rstrip("/")
        try:
            if rel.endswith("/"):
                try:
                    os.rmdir(target)
                except OSError:
                    pass
            else:
                _remove_path(target)
            _prune_empty_parents(target.parent, dst)
        except OSError as e:
            errors.append(f"{rel}: {e.strerror or e}")
    for rel in sorted(ch.added + ch.modified):
        kind, src = new[rel]
        target = dst / rel.rstrip("/")
        try:
            if kind == "d":
                if os.path.lexists(target) and not os.path.isdir(target):
                    _remove_path(target)
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(target):
                _remove_path(target)
            if kind == "l":
                os.symlink(os.readlink(src), target)
            else:
                shutil.copy2(src, target)
        except OSError as e:
            errors.append(f"{rel}: {e.strerror or e}")
    return errors


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------

class Store:
    """All versions of the project in the current directory."""

    def __init__(self, root: Path):
        self.root = root
        self.vdir = root / VERSIONS_DIR
        self.index_path = self.vdir / INDEX_NAME
        self.data: dict = {"head": None, "next_order": 1, "versions": {}}
        self._load()

    # -- basic access ------------------------------------------------------
    @property
    def versions(self) -> dict:
        return self.data["versions"]

    @property
    def head(self) -> Optional[str]:
        return self.data["head"]

    def path(self, vid: str) -> Path:
        return self.vdir / self.versions[vid]["dir"]

    def by_order(self) -> List[str]:
        vs = self.versions
        return sorted(vs, key=lambda v: vs[v]["order"])

    def natural(self) -> List[str]:
        return sorted(self.versions, key=key)

    def set_head(self, vid: str) -> None:
        self.data["head"] = vid
        self.save()

    def resolve(self, token: str) -> str:
        """Turn 'v1.2.3', '1.2.3', a directory name or a label into a version id."""
        vs = self.versions
        t = parse_id(token)
        if t is not None:
            if len(t) < 3:
                t = t + (0,) * (3 - len(t))
            vid = fmt_id(t)
            if vid in vs:
                return vid
            raise UserError(f"Version {vid} not found. Run 'versionsnap list' to see all versions.")
        for vid, e in vs.items():
            if e["dir"] == token:
                return vid
        matches = sorted((v for v, e in vs.items() if e["label"] == token), key=key)
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise UserError(f"Label '{token}' is used by {', '.join(matches)}; please use the version number.")
        raise UserError(f"'{token}' is not a version or a label. Run 'versionsnap list' to see all versions.")

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        if self.vdir.exists() and not self.vdir.is_dir():
            raise UserError("A file named 'versions' exists. Remove or rename it, then run again.")
        if self.index_path.is_file():
            try:
                self.data = json.loads(self.index_path.read_text(encoding="utf-8"))
            except ValueError:
                raise UserError(
                    f"{VERSIONS_DIR}/{INDEX_NAME} is damaged. Delete it and run again "
                    "to rebuild it from the version folders."
                )
        self._sync()

    def save(self) -> None:
        self.vdir.mkdir(exist_ok=True)
        tmp = self.vdir / (INDEX_NAME + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.index_path)

    def _drop(self, vid: str) -> None:
        vs = self.versions
        parent = vs[vid]["parent"]
        for e in vs.values():
            if e["parent"] == vid:
                e["parent"] = parent
        if self.data["head"] == vid:
            self.data["head"] = parent
        del vs[vid]

    def _fix_head(self) -> None:
        if self.data["head"] not in self.versions:
            order = self.by_order()
            self.data["head"] = order[-1] if order else None

    def _sync(self) -> None:
        """Bring the index in line with the folders on disk (also imports
        folders made by the old shell script)."""
        if not self.vdir.is_dir():
            return
        vs = self.versions
        on_disk: Dict[str, Tuple[str, str]] = {}
        for p in sorted(self.vdir.iterdir()):
            m = DIR_RE.match(p.name)
            if p.is_dir() and m:
                t = tuple(int(x) for x in m.group(1).split("."))
                if len(t) >= 3:
                    on_disk.setdefault(fmt_id(t), (p.name, m.group(2) or ""))
        changed = False
        for vid in list(vs):
            if vid not in on_disk or not (self.vdir / vs[vid]["dir"]).is_dir():
                self._drop(vid)
                changed = True
        ex = Excludes(self.root)
        for vid in sorted((v for v in on_disk if v not in vs), key=key):
            name, label = on_disk[vid]
            t = key(vid)
            if len(t) == 3:
                earlier = [v for v in vs if len(key(v)) == 3 and key(v) < t]
                parent = max(earlier, key=key) if earlier else None
            else:
                cand = t[:-1] + (t[-1] - 1,) if t[-1] > 1 else t[:-2]
                parent = fmt_id(cand) if fmt_id(cand) in vs else None
            path = self.vdir / name
            cur = scan(path, ex)
            old = scan(self.vdir / vs[parent]["dir"], ex) if parent else {}
            entry = {
                "parent": parent,
                "created": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "label": label,
                "dir": name,
                "order": self.data["next_order"],
            }
            entry.update(stats(cur, old))
            vs[vid] = entry
            self.data["next_order"] += 1
            changed = True
        before = self.data["head"]
        self._fix_head()
        if changed or before != self.data["head"]:
            self.save()

    # -- operations --------------------------------------------------------
    def next_id(self) -> Id:
        vs = self.versions
        if not vs:
            return (0, 0, 1)
        head = key(self.head)  # type: ignore[arg-type]
        cont = continuation(head)
        if fmt_id(cont) not in vs:
            return cont
        n = len(head)
        used = [key(v)[n] for v in vs if len(key(v)) == n + 2 and key(v)[:n] == head]
        return head + (max(used, default=0) + 1, 1)

    def snapshot(self, label: str = "") -> Tuple[str, dict]:
        ex = Excludes(self.root)
        work = scan(self.root, ex)
        new_id = self.next_id()
        vid = fmt_id(new_id)
        name = vid + ("." + label if label else "")
        self.vdir.mkdir(exist_ok=True)
        dest = self.vdir / name
        dest.mkdir()
        errors = apply(dest, work, Changes(added=sorted(work)))
        if errors:
            shutil.rmtree(dest, ignore_errors=True)
            raise UserError("Could not copy: " + "; ".join(errors[:3]))
        parent = self.head
        old = scan(self.path(parent), ex) if parent else {}
        entry = {
            "parent": parent,
            "created": datetime.now().isoformat(timespec="seconds"),
            "label": label,
            "dir": name,
            "order": self.data["next_order"],
        }
        entry.update(stats(work, old))
        self.versions[vid] = entry
        self.data["next_order"] += 1
        self.data["head"] = vid
        self.save()
        return vid, entry

    def delete(self, ids: Iterable[str]) -> None:
        for vid in sorted(ids, key=key):
            shutil.rmtree(self.path(vid), ignore_errors=True)
            self._drop(vid)
        self._fix_head()
        self.save()
