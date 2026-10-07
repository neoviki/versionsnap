# MIT License - Copyright (c) 2010 Vignesh | VIKI - https://www.viki.design
"""versionsnap command line interface."""

from __future__ import annotations

import difflib
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

from tabulate import tabulate

from .store import (
    Changes,
    Entry,
    Excludes,
    Store,
    UserError,
    apply,
    compare,
    key,
    scan,
)

COMMANDS = ("help", "list", "move", "history", "diff", "delete", "undo", "current")
LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
MAX_ROWS = 40            # file rows shown in a confirmation table
MAX_DIFF_BYTES = 2_000_000
USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def table(rows, headers, align=None) -> None:
    print(
        tabulate(
            rows,
            headers=headers,
            tablefmt="rounded_grid",
            disable_numparse=True,
            colalign=align,
            preserve_whitespace=True,
        )
    )


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def fmt_time(iso: str) -> str:
    return iso.replace("T", " ")[:16]


def confirm(question: str) -> bool:
    try:
        return input(f"{question} [y/N]: ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def ask(question: str) -> str:
    try:
        return input(f"{question}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def need_versions(store: Store) -> None:
    if not store.versions:
        raise UserError("No versions yet. Run 'versionsnap' to create the first one.")


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_help() -> None:
    rows = [
        ["versionsnap", "Create a new version of the current directory"],
        ["versionsnap <label>", "Create a new version with a label (e.g. production)"],
        ["versionsnap help", "Show this help"],
        ["versionsnap list", "List all versions"],
        ["versionsnap history", "Show what changed in every version"],
        ["versionsnap history graph", "Show the versions as a tree (branches included)"],
        ["versionsnap history <version>", "Show the files changed in one version"],
        ["versionsnap diff <v1> <v2>", "Show what the newer of the two versions added"],
        ["versionsnap move prev", "Discard current changes, go back to the previous version"],
        ["versionsnap move <version>", "Discard current changes, go to that version"],
        ["versionsnap undo", "Discard current changes, back to the current version"],
        ["versionsnap delete <v1> to <v2>", "Delete all versions from v1 to v2"],
        ["versionsnap current", "Show the current version and whether the directory has changes"],
    ]
    table(rows, ["Command", "What it does"])
    print("A version can be written as v1.2.3, 1.2.3 or by its label.")
    print("Moving back and snapshotting again starts a branch, e.g. v1.2.3.1.1")
    print("Put names to skip in a .versionsnapignore file (one per line).")


def cmd_snapshot(store: Store, label: str) -> None:
    if label:
        if not LABEL_RE.match(label):
            raise UserError("A label must start with a letter and use only letters, digits, '_' or '-'.")

    if store.head:
        ex = Excludes(store.root)
        if not compare(scan(store.path(store.head), ex), scan(store.root, ex)):
            print(f"[ INFO ] No changes since {store.head}. No new version needed, skipping.")
            return

    if label:
        close = difflib.get_close_matches(label, COMMANDS, n=1, cutoff=0.75)
        if close and not confirm(
            f"'{label}' looks like the command '{close[0]}'. Create a version with that label anyway?"
        ):
            print("[ CANCELLED ] No version created.")
            return
    vid, e = store.snapshot(label)
    table(
        [[
            vid,
            e["parent"] or "-",
            label or "-",
            e["files"],
            human_size(e["size"]),
            f'+{e["added"]} ~{e["modified"]} -{e["deleted"]}',
            f'versions/{e["dir"]}',
        ]],
        ["Version", "Parent", "Label", "Files", "Size", "Changes", "Directory"],
        align=("left", "left", "left", "right", "right", "left", "left"),
    )


def cmd_list(store: Store) -> None:
    need_versions(store)
    vs = store.versions
    rows = []
    for vid in store.natural():
        e = vs[vid]
        rows.append([
            vid,
            e["label"] or "-",
            fmt_time(e["created"]),
            e["parent"] or "-",
            e["files"],
            human_size(e["size"]),
            "◀" if vid == store.head else "",
        ])
    table(
        rows,
        ["Version", "Label", "Created", "Parent", "Files", "Size", "HEAD"],
        align=("left", "left", "left", "left", "right", "right", "center"),
    )

def cmd_current(store: Store) -> None:
    need_versions(store)
    e = store.versions[store.head]
    ex = Excludes(store.root)
    ch = compare(scan(store.path(store.head), ex), scan(store.root, ex))
    a, m, d = ch.counts()
    status = f"+{a} ~{m} -{d} not saved" if ch else "no changes"
    table(
        [[
            store.head,
            e["label"] or "-",
            fmt_time(e["created"]),
            e["parent"] or "-",
            e["files"],
            human_size(e["size"]),
            status,
        ]],
        ["Version", "Label", "Created", "Parent", "Files", "Size", "Working directory"],
        align=("left", "left", "left", "left", "right", "right", "left"),
    )

def _file_rows(ch: Changes) -> List[List[str]]:
    rows = [["added", r] for r in ch.added if not r.endswith("/")]
    rows += [["modified", r] for r in ch.modified if not r.endswith("/")]
    rows += [["deleted", r] for r in ch.deleted if not r.endswith("/")]
    return rows


def cmd_history(store: Store, args: List[str]) -> None:
    need_versions(store)
    vs = store.versions
    if not args:
        rows = []
        for vid in store.by_order():
            e = vs[vid]
            rows.append([
                vid,
                e["label"] or "-",
                fmt_time(e["created"]),
                e["parent"] or "-",
                e["added"],
                e["modified"],
                e["deleted"],
                "◀" if vid == store.head else "",
            ])
        table(
            rows,
            ["Version", "Label", "Created", "Parent", "Added", "Modified", "Deleted", "HEAD"],
            align=("left", "left", "left", "left", "right", "right", "right", "center"),
        )
    elif args == ["graph"]:
        print_graph(store)
    elif len(args) == 1:
        vid = store.resolve(args[0])
        parent = vs[vid]["parent"]
        ex = Excludes(store.root)
        old = scan(store.path(parent), ex) if parent else {}
        ch = compare(old, scan(store.path(vid), ex))
        rows = _file_rows(ch)
        print(f"Files changed in {vid}" + (f" compared to {parent}:" if parent else " (first version):"))
        if rows:
            table(rows, ["Change", "File"])
        else:
            print("[ INFO ] No file changes.")
    else:
        raise UserError("Usage: versionsnap history | history graph | history <version>")


def print_graph(store: Store) -> None:
    vs = store.versions
    kids: dict = {}
    for vid in store.by_order():
        kids.setdefault(vs[vid]["parent"], []).append(vid)
    rows: List[tuple] = []  # (graph text, version id or None); newest on top

    def lane(start: str, depth: int) -> None:
        chain = [start]
        while kids.get(chain[-1]):
            chain.append(kids[chain[-1]][0])  # first-created child continues the line
        for node in reversed(chain):
            for branch in reversed(kids.get(node, [])[1:]):
                lane(branch, depth + 1)
                rows.append(("│ " * depth + "├─╯", None))
            rows.append(("│ " * depth + ("◉ " if node == store.head else "● "), node))

    for n, root in enumerate(reversed(kids.get(None, []))):
        if n:
            rows.append(("", None))
        lane(root, 0)

    def cell(fn) -> str:
        return "\n".join(fn(v) if v else "" for _, v in rows)

    table(
        [[
            "\n".join(g for g, _ in rows),
            cell(lambda v: v),
            cell(lambda v: vs[v]["label"]),
            cell(lambda v: fmt_time(vs[v]["created"])),
            cell(lambda v: f'+{vs[v]["added"]} ~{vs[v]["modified"]} -{vs[v]["deleted"]}'),
        ]],
        ["Graph", "Version", "Label", "Created", "Changes"],
    )
    print("◉ current version (HEAD)   ● other version   branches are drawn to the right of the line they started from")


def _read_lines(entry: Entry) -> Optional[List[str]]:
    kind, path = entry
    if kind == "l":
        return ["-> " + os.readlink(path)]
    try:
        if os.path.getsize(path) > MAX_DIFF_BYTES:
            return None
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace").splitlines()


def _color_diff_line(line: str) -> str:
    if line.startswith(("+++", "---")):
        return paint(line, "1")
    if line.startswith("+"):
        return paint(line, "32")
    if line.startswith("-"):
        return paint(line, "31")
    if line.startswith("@@"):
        return paint(line, "36")
    return line


def cmd_diff(store: Store, args: List[str]) -> None:
    if len(args) != 2:
        raise UserError("Usage: versionsnap diff <version1> <version2>")
    a, b = store.resolve(args[0]), store.resolve(args[1])
    if a == b:
        raise UserError("Please give two different versions.")
    vs = store.versions
    older, newer = sorted((a, b), key=lambda v: vs[v]["order"])
    ex = Excludes(store.root)
    old, new = scan(store.path(older), ex), scan(store.path(newer), ex)
    ch = compare(old, new)
    items = [("added", r) for r in ch.added] + [("modified", r) for r in ch.modified] + [("deleted", r) for r in ch.deleted]
    items = [(s, r) for s, r in items if not r.endswith("/")]
    if not items:
        print(f"[ INFO ] {newer} has no file differences compared to {older}.")
        return
    summary, bodies = [], []
    for status, rel in items:
        a_lines = [] if status == "added" else _read_lines(old[rel])
        b_lines = [] if status == "deleted" else _read_lines(new[rel])
        if a_lines is None or b_lines is None:
            summary.append([status, rel, "binary/large", "binary/large"])
            bodies.append(f"{status}: {rel} (binary or large file, content not shown)")
            continue
        diff = list(difflib.unified_diff(
            a_lines, b_lines,
            fromfile="/dev/null" if status == "added" else f"{older}/{rel}",
            tofile="/dev/null" if status == "deleted" else f"{newer}/{rel}",
            lineterm="",
        ))
        plus = sum(1 for l in diff[2:] if l.startswith("+"))
        minus = sum(1 for l in diff[2:] if l.startswith("-"))
        summary.append([status, rel, f"+{plus}", f"-{minus}"])
        if diff:
            bodies.append("\n".join(_color_diff_line(l) for l in diff))
    print(f"What {newer} changed compared to {older} (always older -> newer):")
    table(summary, ["Change", "File", "Lines added", "Lines removed"], align=("left", "left", "right", "right"))
    for body in bodies:
        print()
        print(body)


def _change_rows(ch: Changes) -> List[List[str]]:
    rows = [["create", r] for r in ch.added]
    rows += [["overwrite", r] for r in ch.modified]
    rows += [["remove", r] for r in ch.deleted]
    if len(rows) > MAX_ROWS:
        extra = len(rows) - MAX_ROWS
        rows = rows[:MAX_ROWS] + [["...", f"and {extra} more"]]
    return rows


def restore(store: Store, target: str, verb: str) -> None:
    """Make the working directory match `target`, discarding current changes."""
    ex = Excludes(store.root)
    work = scan(store.root, ex)
    snap = scan(store.path(target), ex)
    ch = compare(work, snap)
    if ch:
        print(f"These files will change to match {target}:")
        table(_change_rows(ch), ["Action", "File"])
        question = (
            f"Discard all current changes and {verb} {target}? "
            f"({len(ch.added)} create, {len(ch.modified)} overwrite, {len(ch.deleted)} remove)"
        )
        if not confirm(question):
            print("[ CANCELLED ] Nothing was changed.")
            return
        errors = apply(store.root, snap, ch)
        if errors:
            raise UserError("Some files could not be updated: " + "; ".join(errors[:3]))
    else:
        print(f"[ INFO ] The working directory already matches {target}.")
    store.set_head(target)
    print(f"[ DONE ] Current version is now {target}")


def cmd_move(store: Store, args: List[str]) -> None:
    if len(args) != 1:
        raise UserError("Usage: versionsnap move prev | versionsnap move <version>")
    need_versions(store)
    if args[0].lower() == "prev":
        parent = store.versions[store.head]["parent"]
        if not parent:
            raise UserError(f"{store.head} is the first version; there is no previous version.")
        target = parent
    else:
        target = store.resolve(args[0])
    restore(store, target, "move to")


def cmd_undo(store: Store) -> None:
    need_versions(store)
    restore(store, store.head, "restore")


def cmd_delete(store: Store, args: List[str]) -> None:
    need_versions(store)
    if not args:
        cmd_list(store)
        lo, hi = ask("Delete from version"), ask("Delete up to version")
    elif len(args) == 1:
        lo = hi = args[0]
    elif len(args) in (2, 3) and args[1].lower() == "to":
        lo = args[0]
        if len(args) == 3:
            hi = args[2]
        else:
            cmd_list(store)
            hi = ask(f"Delete from {lo} up to which version")
    else:
        raise UserError("Usage: versionsnap delete <version1> to <version2>")
    if not lo or not hi:
        raise UserError("No version given; nothing deleted.")
    lo, hi = store.resolve(lo), store.resolve(hi)
    if key(lo) > key(hi):
        lo, hi = hi, lo
    vs = store.versions
    victims = [v for v in store.natural() if key(lo) <= key(v) <= key(hi)]
    rows = [
        [v, vs[v]["label"] or "-", fmt_time(vs[v]["created"]), vs[v]["files"], human_size(vs[v]["size"])]
        for v in victims
    ]
    print("These versions will be deleted:")
    table(rows, ["Version", "Label", "Created", "Files", "Size"], align=("left", "left", "left", "right", "right"))
    if store.head in victims:
        print(f"[ NOTE ] The current version {store.head} is included; the current version will move to the nearest remaining parent. Your files are not touched.")
    if not confirm(f"Delete {len(victims)} version(s)? This cannot be undone. Continue?"):
        print("[ CANCELLED ] Nothing was deleted.")
        return
    store.delete(victims)
    print(f"[ DONE ] Deleted {len(victims)} version(s). Current version: {store.head or '-'}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""
    try:
        if cmd in ("help", "-h", "--help"):
            cmd_help()
            return 0
        store = Store(Path.cwd())
        rest = args[1:]
        if cmd == "list" and not rest:
            cmd_list(store)
        elif cmd == "current" and not rest:
            cmd_current(store)
        elif cmd == "history":
            cmd_history(store, rest)
        elif cmd == "diff":
            cmd_diff(store, rest)
        elif cmd == "move":
            cmd_move(store, rest)
        elif cmd == "undo" and not rest:
            cmd_undo(store)
        elif cmd == "delete":
            cmd_delete(store, rest)
        elif cmd in COMMANDS:
            raise UserError(f"Too many arguments for '{cmd}'. Run 'versionsnap help'.")
        elif len(args) > 1:
            raise UserError("Too many arguments. Run 'versionsnap help'.")
        else:
            cmd_snapshot(store, cmd)
    except UserError as e:
        print(f"[ ERROR ] {e}")
        return 1
    except KeyboardInterrupt:
        print()
        return 130
    except BrokenPipeError:  # e.g. `versionsnap diff a b | head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    return 0
