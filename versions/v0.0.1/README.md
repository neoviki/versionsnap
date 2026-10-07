# versionsnap

**A simple project versioning tool: snapshots, branches, diff, move and undo.**

`versionsnap` is a command-line tool that takes snapshots (full copies) of your current directory, usually a project, and stores them in a `versions/` folder as `v0.0.1`, `v0.0.2`, `v0.0.3`, and so on. You can label a snapshot (`v0.0.2.production`), list and compare versions, go back to an older one, and delete ranges you no longer need.

It is not a replacement for Git. It is the quick "save a copy I can go back to" tool that I use alongside Git for my own projects: no commits, no staging, no setup. Everything is printed as readable tables.

## Features

- **One-word snapshots**: `versionsnap` copies the directory into `versions/vX.Y.Z`
- **Labels**: `versionsnap production` creates `v0.0.2.production`
- **Nothing to save, nothing created**: if the directory has not changed since the current version, no new version is made
- **Branches**: go back to an older version, change things, snapshot again, and you get a numbered branch (`v0.0.2.1.1`) instead of losing or overwriting anything
- **History and graph**: see what changed in every version, or draw the version tree
- **Diff**: see exactly what the newer of two versions added over the older one
- **Move and undo**: restore any version into your directory, or discard your unsaved changes
- **Delete ranges**: `delete v0.0.1 to v0.0.4`, with a list and a confirmation first
- **Plain commands**: no flags to remember, and every table is a rounded grid

## Installation

Requirements: Python 3.8 or newer and [pipx](https://pipx.pypa.io). The only dependency, [tabulate](https://pypi.org/project/tabulate/) (0.9 or newer for the rounded tables), is installed automatically.

### From GitHub

```bash
pipx install git+https://github.com/neoviki/versionsnap.git
```

### From a local clone

```bash
git clone https://github.com/neoviki/versionsnap.git
cd versionsnap
pipx install .

or

./install.sh
```

For development, install it editable, so code changes take effect immediately:

```bash
pipx install -e .
```

Update or remove:

```bash
pipx upgrade versionsnap          # installed from GitHub
pipx install --force .            # installed from a local clone, after pulling changes
pipx uninstall versionsnap

or

./uninstall.sh
```

## Quick start

```bash
cd my-project
versionsnap                 # v0.0.1
# ...work...
versionsnap production      # v0.0.2.production
versionsnap list
versionsnap move prev       # go back to v0.0.1 (nothing is deleted)
```

## Commands

| Command | What it does |
|---|---|
| `versionsnap` | Create a new version of the current directory |
| `versionsnap <label>` | Create a new version with a label, e.g. `production` or `staging` |
| `versionsnap help` | Show the command table |
| `versionsnap list` | List all versions |
| `versionsnap current` | Show the current version and whether the directory has unsaved changes |
| `versionsnap history` | Show what changed in every version |
| `versionsnap history graph` | Show the versions as a tree, branches included |
| `versionsnap history <version>` | Show the files changed in one version |
| `versionsnap diff <v1> <v2>` | Show what the newer of the two versions added over the older one |
| `versionsnap move prev` | Discard current changes and go to the previous version |
| `versionsnap move <version>` | Discard current changes and go to that version |
| `versionsnap undo` | Discard current changes and restore the current version |
| `versionsnap delete <v1> to <v2>` | Delete all versions from v1 to v2 |

A version can be written as `v1.2.3`, `1.2.3`, or by its label (`versionsnap move production`).

### Creating versions

```bash
versionsnap               # new version
versionsnap production    # new version with a label
```

If nothing changed since the current version, versionsnap says so and skips creating a version. A label must start with a letter and can contain letters, digits, `_` and `-`.

### list and current

```
$ versionsnap list
╭────────────┬────────────┬──────────────────┬──────────┬─────────┬────────┬────────╮
│ Version    │ Label      │ Created          │ Parent   │   Files │   Size │  HEAD  │
├────────────┼────────────┼──────────────────┼──────────┼─────────┼────────┼────────┤
│ v0.0.1     │ -          │ 2026-10-07 20:09 │ -        │       2 │   19 B │        │
├────────────┼────────────┼──────────────────┼──────────┼─────────┼────────┼────────┤
│ v0.0.2     │ production │ 2026-10-07 20:09 │ v0.0.1   │       3 │   25 B │        │
├────────────┼────────────┼──────────────────┼──────────┼─────────┼────────┼────────┤
│ v0.0.2.1.1 │ -          │ 2026-10-07 20:09 │ v0.0.2   │       3 │   33 B │   ◀    │
├────────────┼────────────┼──────────────────┼──────────┼─────────┼────────┼────────┤
│ v0.0.3     │ -          │ 2026-10-07 20:09 │ v0.0.2   │       3 │   25 B │        │
╰────────────┴────────────┴──────────────────┴──────────┴─────────┴────────┴────────╯
```

`◀` marks the **current version** (HEAD): the version your directory is based on. `versionsnap current` shows it, together with `no changes` or the number of added, modified and deleted files you have not saved to a version yet.

### history

`versionsnap history` lists every version in creation order with the number of files added, modified and deleted compared to its parent. `versionsnap history v0.0.2` lists the files that changed in that one version.

```
$ versionsnap history graph
╭─────────┬────────────┬────────────┬──────────────────┬───────────╮
│ Graph   │ Version    │ Label      │ Created          │ Changes   │
├─────────┼────────────┼────────────┼──────────────────┼───────────┤
│ ●       │ v0.0.3     │ -          │ 2026-10-07 20:09 │ +0 ~1 -0  │
│ │ ◉     │ v0.0.2.1.1 │ -          │ 2026-10-07 20:09 │ +0 ~1 -0  │
│ ├─╯     │            │            │                  │           │
│ ●       │ v0.0.2     │ production │ 2026-10-07 20:09 │ +1 ~1 -0  │
│ ●       │ v0.0.1     │ -          │ 2026-10-07 20:09 │ +2 ~0 -0  │
╰─────────┴────────────┴────────────┴──────────────────┴───────────╯
◉ current version (HEAD)   ● other version   branches are drawn to the right of the line they started from
```

The newest version is at the top. `+1 ~1 -0` means one file added, one modified, none deleted.

### diff

```
$ versionsnap diff v0.0.3 v0.0.1
What v0.0.3 changed compared to v0.0.1 (always older -> newer):
╭──────────┬───────────┬───────────────┬─────────────────╮
│ Change   │ File      │   Lines added │   Lines removed │
├──────────┼───────────┼───────────────┼─────────────────┤
│ added    │ notes.txt │            +1 │              -0 │
├──────────┼───────────┼───────────────┼─────────────────┤
│ modified │ app.py    │            +1 │              -1 │
╰──────────┴───────────┴───────────────┴─────────────────╯

--- v0.0.1/app.py
+++ v0.0.3/app.py
@@ -1 +1 @@
-print('v1')
+print('v3')
```

The argument order does not matter: `diff v0.0.3 v0.0.1` and `diff v0.0.1 v0.0.3` print the same thing, always from the older version to the newer one. A summary table comes first, then the line-by-line changes.

### move and undo

```bash
versionsnap move prev       # previous version
versionsnap move v0.0.1     # any version, by number
versionsnap move production # or by label
versionsnap undo            # throw away unsaved changes
```

`move` and `undo` make your directory match a version exactly. **Unsaved changes are discarded**, so before touching anything they show a table of every file that will be created, overwritten or removed, and ask `[y/N]`. No version is ever deleted by `move` or `undo`. To keep your current work, run `versionsnap` first.

### delete

```bash
versionsnap delete v0.0.2 to v0.0.4   # everything from v0.0.2 to v0.0.4
versionsnap delete v0.0.2 to          # asks for the upper limit
versionsnap delete                    # asks for both limits
versionsnap delete v0.0.3             # just that one version
```

It lists the versions that will be deleted and asks `[y/N]` before removing anything. Branches that sit inside the range are included. If you delete the current version, HEAD moves to the nearest remaining parent; your files are not touched.

## Version numbers and branches

Versions on the main line are numbered `v0.0.1`, `v0.0.2`, `v0.0.3`... After `.9` the next number carries over (`v0.0.9` is followed by `v0.1.0`).

When you move back to an older version and snapshot again, the new version starts a **branch** instead of overwriting anything. Branch versions add two numbers, the branch number and the step:

```
v0.0.1 ── v0.0.2 ── v0.0.3                (main line)
             ├── v0.0.2.1.1 ── v0.0.2.1.2     (first branch from v0.0.2)
             └── v0.0.2.2.1                   (second branch from v0.0.2)
```

Branching from a branch simply adds two more numbers (`v0.0.2.1.1.1.1`). Labels always come last and start with a letter: `v0.0.2.1.1.production`.

## How it works

```
my-project/
├── src/...
└── versions/
    ├── .versionsnap.json      # parent of each version, and which one is current
    ├── v0.0.1/
    ├── v0.0.2.production/
    └── v0.0.2.1.1/
```

- Each version is a plain copy of your project, so you can open it, run it or compare it with any other tool.
- Hidden files such as `.env` and `.gitignore` are included. Symbolic links and empty folders are preserved.
- `.git` and `versions` are never copied. To skip anything else, create a `.versionsnapignore` file in the project root with one name or pattern per line (`#` starts a comment):

  ```
  *.log
  build
  node_modules
  ```

- Use `versionsnap` in a project folder, not in a huge folder such as your home directory: every snapshot is a full copy.

### Coming from the shell version

Existing `versions/vX.Y.Z[.label]` folders made by the old shell script are picked up automatically. The 999-version limit no longer exists.

## Running the tests

```bash
python3 -m unittest tests/unit_test.py -v
```

## Background

I originally wrote this tool for versioning my own internal projects, and I still use it alongside Git to keep quick, clear snapshots without disturbing my normal workflow.

It started as a Bash script and has since been rewritten in Python. Python is easier to debug, and it made room for the newer commands: `list`, `current`, `history`, `diff`, `move`, `undo`, `delete` and branches.

## License

MIT. See the [LICENSE](LICENSE) file.

Project: <https://github.com/neoviki/versionsnap>


## Acknowledgements

The Python version was implemented with the help of LLM tools, mainly Claude (Anthropic) and, to a smaller extent, Qwen (Alibaba Cloud). The behaviour is covered by the included unit tests.
