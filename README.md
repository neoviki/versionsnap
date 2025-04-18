## versionsnap - A Versioning Snapshot Utility

versionsnap is a Linux command-line utility for taking snapshots (copies) of your current directory (usually a project) with version identifiers. Snapshots are saved in a versions directory within the project. It helps manage simple versioning using a format like v0.0.0, v0.0.1, v0.0.2, etc. You can also tag versions (e.g., v2.1.3.production), and the tool will automatically handle version increments as needed.


### Features

- **Snapshot Creation**: Automatically create a snapshot of the current working directory.
- **Version Format**: Follows a simple 3-level versioning format (`v0.0.1`, `v0.0.2`, ...), with up to `999` versions are possible.
- **Version Labeling**: Supports version labeling for different environments or stages (e.g., `v2.1.3.production`, `v2.1.4.staging`).
- **Incremental Versioning**: Handles automatic version increment.

### How It Works

1. **Version Snapshot**: The tool creates a snapshot of the current working directory and stores it under the `versions` directory.
2. **Version Format**: By default, the version format is `vX.Y.Z` (where `X`, `Y`, and `Z` are numbers). The tool can automatically generate new versions, such as `v0.0.1`, `v0.0.2`, etc.
3. **Version Labeling**: You can add a label to a version, such as `v2.1.3.production`. The tool will automatically handle the versioning and generate the next version, as `v2.1.4`.
4. **Maximum Versions**: The tool supports up to `999` versions. You can define your own maximum version number and customize the versioning scheme.

---

### Example Usage

#### 1. **Create a Version Snapshot**

To create a snapshot of the current directory, simply run:

```bash
versionsnap
```

This will create a snapshot(copy) of the current working directory under the `versions` directory with an incremented version (e.g., `v0.0.1`, `v0.0.2`).

#### 2. **Labeling a Version**

You can also create a labeled version, like (production/staging):

```bash
versionsnap production
```

This command will create a version with the format `v0.0.1.production`, incrementing the version number appropriately.

---

### Installation

To install and set up **`versionsnap`**, follow these steps:

1. **Clone the Repository**:

```bash
git clone https://github.com/yourusername/versionsnap.git
cd versionsnap
```

2. **Run the Installer**:

The provided installer will make the script executable and optionally move it to a location like `/usr/local/bin` so it’s accessible globally.

```bash
chmod +x install.sh
sudo ./install.sh
```

Now you can use `versionsnap` directly from your terminal.

### Background of This Tool

This tool was originally created for internal project versioning as part of my personal workflow. I continue to use it alongside Git to maintain consistency. It helps me create quick, clear snapshots of my internal projects without disrupting my existing processes.

---

### Example Workflow

1. Create your first snapshot: `v0.0.1`.
2. Increment versions as you develop, e.g., `v0.0.1`, `v0.0.2`, etc.
3. Label versions for specific environments or releases: `v2.1.3.production`.
4. The tool will automatically generate the next version, e.g., `v2.1.4`.
