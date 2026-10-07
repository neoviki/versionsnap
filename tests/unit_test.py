"""Unit tests for versionsnap.

Run from the project root, either way:
    python -m unittest tests/unit_test.py -v
    pytest tests/unit_test.py

Every test works in its own temporary directory, so nothing real is touched.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from versionsnap.cli import TABLE_FORMAT, main  # noqa: E402
from versionsnap.store import (  # noqa: E402
    Store,
    compare,
    continuation,
    fmt_id,
    parse_id,
    scan,
    Excludes,
)


class TempDirCase(unittest.TestCase):
    """Runs each test inside a fresh temp directory and drives the CLI."""

    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        os.chdir(self.root)
        # versionsnap treats "same size + same mtime" as unchanged (like rsync),
        # so tests give every write a strictly newer mtime.
        self._clock = time.time_ns() - 10**12
        patcher = mock.patch("versionsnap.cli.USE_COLOR", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------
    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self._clock += 10**9
        os.utime(p, ns=(self._clock, self._clock))

    def read(self, rel):
        return (self.root / rel).read_text()

    def exists(self, rel):
        return os.path.lexists(self.root / rel)

    def cli(self, *args, answers=()):
        """Run the CLI; `answers` feed input() prompts. Returns (exit code, output)."""
        queue = list(answers)

        def fake_input(prompt=""):
            if not queue:
                raise EOFError
            return queue.pop(0)

        out = io.StringIO()
        with mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(out):
            code = main(list(args))
        return code, out.getvalue()

    def snap(self, *label):
        code, out = self.cli(*label)
        self.assertEqual(code, 0, out)
        return out

    def store(self):
        return Store(self.root)

    def version_dirs(self):
        vdir = self.root / "versions"
        return sorted(p.name for p in vdir.iterdir() if p.is_dir()) if vdir.is_dir() else []

    def make_versions(self, n):
        """Create v0.0.1 .. v0.0.n where a.txt contains '1' .. 'n'."""
        for i in range(1, n + 1):
            self.write("a.txt", str(i))
            self.snap()


# --------------------------------------------------------------------------
class TestNumbering(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(parse_id("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_id("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_id("1.2"), (1, 2))
        self.assertIsNone(parse_id("v1.2.3.production"))
        self.assertIsNone(parse_id("production"))
        self.assertEqual(fmt_id((1, 2, 3)), "v1.2.3")

    def test_trunk_numbers_carry_after_nine(self):
        self.assertEqual(continuation((0, 0, 1)), (0, 0, 2))
        self.assertEqual(continuation((0, 0, 9)), (0, 1, 0))
        self.assertEqual(continuation((0, 9, 9)), (1, 0, 0))

    def test_branch_numbers_just_count_up(self):
        self.assertEqual(continuation((1, 2, 3, 1, 1)), (1, 2, 3, 1, 2))
        self.assertEqual(continuation((1, 2, 3, 1, 9)), (1, 2, 3, 1, 10))


# --------------------------------------------------------------------------
class TestScanAndCompare(TempDirCase):
    def test_detects_added_modified_deleted(self):
        a, b = self.root / "a", self.root / "b"
        self.write("a/same.txt", "same")
        self.write("a/changed.txt", "old")
        self.write("a/gone.txt", "bye")
        shutil.copytree(a, b)
        self.write("b/changed.txt", "new!")
        self.write("b/added.txt", "hi")
        (b / "gone.txt").unlink()
        ex = Excludes(self.root)
        ch = compare(scan(a, ex), scan(b, ex))
        self.assertEqual(ch.added, ["added.txt"])
        self.assertEqual(ch.modified, ["changed.txt"])
        self.assertEqual(ch.deleted, ["gone.txt"])
        self.assertEqual(ch.counts(), (1, 1, 1))

    def test_same_content_with_different_mtime_is_unchanged(self):
        self.write("a/f.txt", "content")
        self.write("b/f.txt", "content")  # newer mtime, identical bytes
        ex = Excludes(self.root)
        self.assertFalse(compare(scan(self.root / "a", ex), scan(self.root / "b", ex)))

    def test_same_size_different_content_is_modified(self):
        self.write("a/f.txt", "abc")
        self.write("b/f.txt", "xyz")
        ex = Excludes(self.root)
        self.assertEqual(compare(scan(self.root / "a", ex), scan(self.root / "b", ex)).modified, ["f.txt"])

    def test_root_excludes_and_ignore_file(self):
        self.write(".versionsnapignore", "# comment\n*.log\nbuild\n")
        for rel in ("keep.txt", "run.log", "sub/deep.log", "build/out.bin", ".git/config", "versions/x"):
            self.write(rel, "x")
        found = set(scan(self.root, Excludes(self.root)))
        self.assertIn("keep.txt", found)
        self.assertIn(".versionsnapignore", found)
        for skipped in ("run.log", "sub/deep.log", "build/out.bin", ".git/config", "versions/x"):
            self.assertNotIn(skipped, found)


# --------------------------------------------------------------------------
class TestSnapshot(TempDirCase):
    def test_first_snapshot_is_v0_0_1_and_copies_dotfiles(self):
        self.write("a.txt", "hello")
        self.write(".env", "secret")
        self.write("sub/b.txt", "x")
        out = self.snap()
        self.assertIn("v0.0.1", out)
        self.assertEqual(self.version_dirs(), ["v0.0.1"])
        self.assertEqual(self.read("versions/v0.0.1/.env"), "secret")
        self.assertEqual(self.read("versions/v0.0.1/sub/b.txt"), "x")
        self.assertFalse(self.exists("versions/v0.0.1/versions"))

    def test_git_directory_is_not_copied(self):
        self.write("a.txt", "x")
        self.write(".git/config", "x")
        self.snap()
        self.assertFalse(self.exists("versions/v0.0.1/.git"))

    def test_empty_directory_is_kept(self):
        self.write("a.txt", "x")
        (self.root / "empty").mkdir()
        self.snap()
        self.assertTrue((self.root / "versions/v0.0.1/empty").is_dir())

    def test_no_changes_skips_new_version(self):
        self.write("a.txt", "x")
        self.snap()
        code, out = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("No changes", out)
        self.assertEqual(self.version_dirs(), ["v0.0.1"])

    def test_change_creates_next_version(self):
        self.make_versions(2)
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.2"])
        self.assertEqual(self.store().head, "v0.0.2")

    def test_label_goes_into_directory_name(self):
        self.write("a.txt", "1")
        self.snap()
        self.write("a.txt", "2")
        self.snap("production")
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.2.production"])
        self.assertEqual(self.store().versions["v0.0.2"]["label"], "production")

    def test_invalid_label_is_rejected(self):
        self.write("a.txt", "x")
        code, out = self.cli("1bad")
        self.assertEqual(code, 1)
        self.assertIn("ERROR", out)
        self.assertEqual(self.version_dirs(), [])

    def test_label_that_looks_like_a_command_asks_first(self):
        self.write("a.txt", "x")
        code, out = self.cli("histroy", answers=["n"])
        self.assertIn("CANCELLED", out)
        self.assertEqual(self.version_dirs(), [])
        self.cli("histroy", answers=["y"])
        self.assertEqual(self.version_dirs(), ["v0.0.1.histroy"])

    def test_carry_to_next_minor_number(self):
        for i in range(1, 11):
            self.write("a.txt", str(i))
            self.snap()
        self.assertEqual(self.version_dirs()[-2:], ["v0.0.9", "v0.1.0"])
        self.assertEqual(len(self.version_dirs()), 10)

    def test_too_many_arguments(self):
        code, out = self.cli("one", "two")
        self.assertEqual(code, 1)
        self.assertIn("Too many", out)


# --------------------------------------------------------------------------
class TestListCurrentHistory(TempDirCase):
    def test_list_without_versions(self):
        code, out = self.cli("list")
        self.assertEqual(code, 1)
        self.assertIn("No versions yet", out)

    def test_list_shows_all_versions_and_marks_head(self):
        self.make_versions(2)
        code, out = self.cli("list")
        self.assertEqual(code, 0)
        self.assertIn("v0.0.1", out)
        self.assertIn("v0.0.2", out)
        self.assertEqual(out.count("◀"), 1)
        self.assertIn("╭" if TABLE_FORMAT == "rounded_grid" else "+---", out)  # grid border

    def test_current_clean_then_dirty(self):
        self.make_versions(1)
        code, out = self.cli("current")
        self.assertEqual(code, 0)
        self.assertIn("v0.0.1", out)
        self.assertIn("no changes", out)
        self.write("a.txt", "changed")
        self.write("new.txt", "n")
        _, out = self.cli("current")
        self.assertIn("+1 ~1 -0 not saved", out)

    def test_history_counts_per_version(self):
        self.write("a.txt", "one")
        self.write("b.txt", "bee")
        self.snap()
        self.write("a.txt", "two!")
        self.write("c.txt", "see")
        (self.root / "b.txt").unlink()
        self.snap()
        versions = self.store().versions
        self.assertEqual((versions["v0.0.1"]["added"], versions["v0.0.1"]["modified"], versions["v0.0.1"]["deleted"]), (2, 0, 0))
        self.assertEqual((versions["v0.0.2"]["added"], versions["v0.0.2"]["modified"], versions["v0.0.2"]["deleted"]), (1, 1, 1))
        code, out = self.cli("history")
        self.assertEqual(code, 0)
        self.assertIn("Added", out)

    def test_history_of_one_version_lists_files(self):
        self.write("a.txt", "one")
        self.write("b.txt", "bee")
        self.snap()
        self.write("a.txt", "two!")
        self.write("c.txt", "see")
        (self.root / "b.txt").unlink()
        self.snap()
        _, out = self.cli("history", "v0.0.2")
        self.assertIn("c.txt", out)
        self.assertIn("a.txt", out)
        self.assertIn("b.txt", out)
        for word in ("added", "modified", "deleted"):
            self.assertIn(word, out)

    def test_history_graph_shows_branch_and_head(self):
        self.make_versions(2)
        self.cli("move", "v0.0.1", answers=["y"])
        self.write("a.txt", "branch")
        self.snap()
        code, out = self.cli("history", "graph")
        self.assertEqual(code, 0)
        self.assertIn("v0.0.1.1.1", out)
        self.assertIn("├─╯", out)
        self.assertEqual(out.count("◉") - 1, 1)  # one in the table, one in the legend

    def test_history_graph_keeps_labels_on_their_own_row(self):
        self.write("a.txt", "1")
        self.snap()
        self.write("a.txt", "2")
        self.snap("production")
        self.write("a.txt", "3")
        self.snap()
        _, out = self.cli("history", "graph")
        row = [line for line in out.splitlines() if "production" in line]
        self.assertEqual(len(row), 1)
        self.assertIn("v0.0.2", row[0])
        self.assertNotIn("v0.0.3", row[0])

    def test_help_lists_commands(self):
        code, out = self.cli("help")
        self.assertEqual(code, 0)
        for text in ("versionsnap list", "versionsnap current", "versionsnap diff", "versionsnap move prev", "versionsnap undo", "versionsnap delete"):
            self.assertIn(text, out)


# --------------------------------------------------------------------------
class TestDiff(TempDirCase):
    def setUp(self):
        super().setUp()
        self.write("a.txt", "one\n")
        self.write("gone.txt", "bye\n")
        self.snap()
        self.write("a.txt", "one\ntwo\n")
        self.write("new.txt", "fresh\n")
        (self.root / "gone.txt").unlink()
        self.snap()

    def test_shows_what_the_newer_version_added(self):
        code, out = self.cli("diff", "v0.0.1", "v0.0.2")
        self.assertEqual(code, 0)
        self.assertIn("+two", out)
        self.assertIn("+fresh", out)
        self.assertIn("-bye", out)
        for word in ("added", "modified", "deleted", "new.txt", "gone.txt"):
            self.assertIn(word, out)

    def test_argument_order_does_not_matter(self):
        _, forward = self.cli("diff", "v0.0.1", "v0.0.2")
        _, backward = self.cli("diff", "v0.0.2", "v0.0.1")
        self.assertEqual(forward, backward)

    def test_unchanged_files_are_not_listed(self):
        self.write("a.txt", "one\ntwo\n")  # same content, newer mtime
        self.write("z.txt", "z")
        self.snap()
        # v0.0.3 differs from v0.0.2 only by z.txt
        _, out = self.cli("diff", "v0.0.2", "v0.0.3")
        self.assertIn("z.txt", out)
        self.assertNotIn("a.txt", out)

    def test_same_version_twice_is_an_error(self):
        code, out = self.cli("diff", "v0.0.1", "v0.0.1")
        self.assertEqual(code, 1)
        self.assertIn("different", out)

    def test_unknown_version_is_an_error(self):
        code, out = self.cli("diff", "v0.0.1", "v9.9.9")
        self.assertEqual(code, 1)
        self.assertIn("not found", out)

    def test_wrong_number_of_arguments(self):
        code, out = self.cli("diff", "v0.0.1")
        self.assertEqual(code, 1)
        self.assertIn("Usage", out)


# --------------------------------------------------------------------------
class TestMove(TempDirCase):
    def test_move_prev_restores_previous_content_and_keeps_all_versions(self):
        self.make_versions(3)
        code, out = self.cli("move", "prev", answers=["y"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read("a.txt"), "2")
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.2", "v0.0.3"])
        self.assertEqual(self.store().head, "v0.0.2")

    def test_move_prev_discards_unsaved_changes(self):
        self.make_versions(3)
        self.write("a.txt", "dirty")
        self.write("extra.txt", "not in any version")
        self.cli("move", "prev", answers=["y"])
        self.assertEqual(self.read("a.txt"), "2")
        self.assertFalse(self.exists("extra.txt"))

    def test_move_asks_and_can_be_declined(self):
        self.make_versions(3)
        code, out = self.cli("move", "prev", answers=["n"])
        self.assertIn("CANCELLED", out)
        self.assertEqual(self.read("a.txt"), "3")
        self.assertEqual(self.store().head, "v0.0.3")

    def test_move_prev_on_first_version_is_an_error(self):
        self.make_versions(1)
        code, out = self.cli("move", "prev")
        self.assertEqual(code, 1)
        self.assertIn("first version", out)

    def test_move_to_version_number_with_and_without_v(self):
        self.make_versions(3)
        self.cli("move", "v0.0.1", answers=["y"])
        self.assertEqual(self.read("a.txt"), "1")
        self.cli("move", "0.0.3", answers=["y"])
        self.assertEqual(self.read("a.txt"), "3")

    def test_move_to_label(self):
        self.write("a.txt", "1")
        self.snap()
        self.write("a.txt", "2")
        self.snap("production")
        self.write("a.txt", "3")
        self.snap()
        self.cli("move", "production", answers=["y"])
        self.assertEqual(self.read("a.txt"), "2")
        self.assertEqual(self.store().head, "v0.0.2")

    def test_move_restores_deleted_and_dot_files_and_removes_added(self):
        self.write("a.txt", "1")
        self.write(".env", "secret")
        self.write("sub/b.txt", "bee")
        self.snap()
        self.write("a.txt", "2")
        (self.root / ".env").unlink()
        shutil.rmtree(self.root / "sub")
        self.write("new/n.txt", "n")
        self.snap()
        self.cli("move", "prev", answers=["y"])
        self.assertEqual(self.read(".env"), "secret")
        self.assertEqual(self.read("sub/b.txt"), "bee")
        self.assertFalse(self.exists("new"))

    def test_move_to_matching_version_changes_nothing(self):
        self.make_versions(2)
        code, out = self.cli("move", "v0.0.2")
        self.assertEqual(code, 0)
        self.assertIn("already matches", out)

    def test_move_usage_and_unknown_version(self):
        self.make_versions(1)
        self.assertEqual(self.cli("move")[0], 1)
        code, out = self.cli("move", "v9.9.9")
        self.assertEqual(code, 1)
        self.assertIn("not found", out)

    def test_snapshot_after_move_starts_a_branch(self):
        self.make_versions(3)
        self.cli("move", "prev", answers=["y"])
        self.write("a.txt", "branch work")
        self.snap()
        self.assertIn("v0.0.2.1.1", self.version_dirs())
        self.assertEqual(self.store().versions["v0.0.2.1.1"]["parent"], "v0.0.2")
        # the old line is untouched
        self.assertIn("v0.0.3", self.version_dirs())

    def test_second_branch_and_continuing_a_branch(self):
        self.make_versions(3)
        self.cli("move", "v0.0.2", answers=["y"])
        self.write("a.txt", "b1")
        self.snap()                                   # v0.0.2.1.1
        self.write("a.txt", "b1 again")
        self.snap()                                   # v0.0.2.1.2 (same branch continues)
        self.cli("move", "v0.0.2", answers=["y"])
        self.write("a.txt", "b2")
        self.snap()                                   # v0.0.2.2.1 (new branch)
        self.assertEqual(
            self.version_dirs(),
            ["v0.0.1", "v0.0.2", "v0.0.2.1.1", "v0.0.2.1.2", "v0.0.2.2.1", "v0.0.3"],
        )

    def test_branch_from_a_branch(self):
        self.make_versions(2)
        self.cli("move", "v0.0.1", answers=["y"])
        self.write("a.txt", "b1")
        self.snap()                                   # v0.0.1.1.1
        self.write("a.txt", "b1-2")
        self.snap()                                   # v0.0.1.1.2
        self.cli("move", "v0.0.1.1.1", answers=["y"])
        self.write("a.txt", "deeper")
        self.snap()                                   # branch off a branch
        self.assertIn("v0.0.1.1.1.1.1", self.version_dirs())


# --------------------------------------------------------------------------
class TestUndo(TempDirCase):
    def test_undo_discards_changes(self):
        self.make_versions(2)
        self.write("a.txt", "dirty")
        self.write("extra.txt", "x")
        (self.root / "b.txt").write_text("keep? no, not in version")
        code, out = self.cli("undo", answers=["y"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read("a.txt"), "2")
        self.assertFalse(self.exists("extra.txt"))
        self.assertFalse(self.exists("b.txt"))
        self.assertEqual(self.store().head, "v0.0.2")

    def test_undo_restores_deleted_file(self):
        self.write("a.txt", "1")
        self.write("b.txt", "bee")
        self.snap()
        (self.root / "b.txt").unlink()
        self.cli("undo", answers=["y"])
        self.assertEqual(self.read("b.txt"), "bee")

    def test_undo_declined_keeps_changes(self):
        self.make_versions(1)
        self.write("a.txt", "dirty")
        _, out = self.cli("undo", answers=["n"])
        self.assertIn("CANCELLED", out)
        self.assertEqual(self.read("a.txt"), "dirty")

    def test_undo_with_nothing_to_discard(self):
        self.make_versions(1)
        code, out = self.cli("undo")
        self.assertEqual(code, 0)
        self.assertIn("already matches", out)

    def test_undo_without_versions(self):
        code, out = self.cli("undo")
        self.assertEqual(code, 1)
        self.assertIn("No versions yet", out)


# --------------------------------------------------------------------------
class TestDelete(TempDirCase):
    def setUp(self):
        super().setUp()
        self.make_versions(5)

    def test_delete_range_removes_folders_and_index_entries(self):
        code, out = self.cli("delete", "v0.0.2", "to", "v0.0.4", answers=["y"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.5"])
        versions = self.store().versions
        self.assertEqual(sorted(versions), ["v0.0.1", "v0.0.5"])
        self.assertEqual(versions["v0.0.5"]["parent"], "v0.0.1")

    def test_delete_lists_versions_before_asking(self):
        _, out = self.cli("delete", "v0.0.2", "to", "v0.0.3", answers=["n"])
        self.assertIn("will be deleted", out)
        self.assertIn("v0.0.2", out)
        self.assertIn("v0.0.3", out)

    def test_delete_declined_deletes_nothing(self):
        _, out = self.cli("delete", "v0.0.1", "to", "v0.0.5", answers=["n"])
        self.assertIn("CANCELLED", out)
        self.assertEqual(len(self.version_dirs()), 5)

    def test_delete_without_answer_defaults_to_no(self):
        self.cli("delete", "v0.0.1", "to", "v0.0.2")  # input() hits EOF
        self.assertEqual(len(self.version_dirs()), 5)

    def test_missing_upper_limit_is_asked(self):
        code, out = self.cli("delete", "v0.0.2", "to", answers=["v0.0.3", "y"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.4", "v0.0.5"])

    def test_no_arguments_asks_for_both_limits(self):
        code, out = self.cli("delete", answers=["v0.0.1", "v0.0.2", "y"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.version_dirs(), ["v0.0.3", "v0.0.4", "v0.0.5"])

    def test_empty_answer_for_upper_limit_is_an_error(self):
        code, out = self.cli("delete", "v0.0.2", "to", answers=[""])
        self.assertEqual(code, 1)
        self.assertEqual(len(self.version_dirs()), 5)

    def test_reversed_range_is_swapped(self):
        self.cli("delete", "v0.0.4", "to", "v0.0.2", answers=["y"])
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.5"])

    def test_single_version(self):
        self.cli("delete", "v0.0.3", answers=["y"])
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.2", "v0.0.4", "v0.0.5"])

    def test_deleting_current_version_moves_head_to_parent_and_keeps_files(self):
        self.cli("delete", "v0.0.4", "to", "v0.0.5", answers=["y"])
        self.assertEqual(self.store().head, "v0.0.3")
        self.assertEqual(self.read("a.txt"), "5")  # working directory untouched

    def test_range_includes_branches_in_between(self):
        self.cli("move", "v0.0.2", answers=["y"])
        self.write("a.txt", "branch")
        self.snap()                                   # v0.0.2.1.1
        self.cli("delete", "v0.0.2", "to", "v0.0.3", answers=["y"])
        self.assertEqual(self.version_dirs(), ["v0.0.1", "v0.0.4", "v0.0.5"])

    def test_numbers_are_reused_after_deleting_the_tip(self):
        self.cli("delete", "v0.0.4", "to", "v0.0.5", answers=["y"])
        self.write("a.txt", "new line")
        self.snap()
        self.assertEqual(self.version_dirs()[-1], "v0.0.4")


# --------------------------------------------------------------------------
class TestIndexAndErrors(TempDirCase):
    def test_folders_from_the_old_shell_script_are_imported(self):
        self.write("versions/v0.0.1/f.txt", "a")
        self.write("versions/v0.0.2.prod/f.txt", "b")
        self.write("f.txt", "b")
        store = self.store()
        self.assertEqual(sorted(store.versions), ["v0.0.1", "v0.0.2"])
        self.assertEqual(store.versions["v0.0.2"]["parent"], "v0.0.1")
        self.assertEqual(store.versions["v0.0.2"]["label"], "prod")
        self.assertEqual(store.head, "v0.0.2")
        code, out = self.cli("current")
        self.assertIn("no changes", out)

    def test_manually_deleted_folder_disappears_from_the_index(self):
        self.make_versions(2)
        shutil.rmtree(self.root / "versions" / "v0.0.1")
        store = self.store()
        self.assertEqual(list(store.versions), ["v0.0.2"])
        self.assertIsNone(store.versions["v0.0.2"]["parent"])

    def test_damaged_index_gives_a_clear_error(self):
        self.make_versions(1)
        (self.root / "versions" / ".versionsnap.json").write_text("{not json")
        code, out = self.cli("list")
        self.assertEqual(code, 1)
        self.assertIn("damaged", out)

    def test_versions_being_a_file_is_an_error(self):
        (self.root / "versions").write_text("oops")
        code, out = self.cli("list")
        self.assertEqual(code, 1)
        self.assertIn("named 'versions'", out)

    def test_help_works_even_when_versions_is_a_file(self):
        (self.root / "versions").write_text("oops")
        self.assertEqual(self.cli("help")[0], 0)

    def test_head_survives_between_runs(self):
        self.make_versions(3)
        self.cli("move", "v0.0.1", answers=["y"])
        self.assertEqual(self.store().head, "v0.0.1")
        _, out = self.cli("current")
        self.assertIn("v0.0.1", out)

    def test_symlinks_are_preserved(self):
        self.write("target.txt", "t")
        os.symlink("target.txt", self.root / "link.txt")
        self.snap()
        copied = self.root / "versions" / "v0.0.1" / "link.txt"
        self.assertTrue(os.path.islink(copied))
        self.assertEqual(os.readlink(copied), "target.txt")


if __name__ == "__main__":
    unittest.main()
