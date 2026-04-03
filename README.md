![Logo](logo.png)

**Segmenta** is a high-performance media utility designed to help you turn messy stream segments into a polished personal archive. It automatically groups, merges, and transcodes timestamped source files (`.ts` and `.mp4`) into organized H.265 (`.mp4`) libraries.

![Python >=3.10](https://img.shields.io/badge/python-3.10%2B-blue)
![FFmpeg required](https://img.shields.io/badge/ffmpeg-required-orange)
![Scope local files only](https://img.shields.io/badge/scope-local%20files%20only-green)

---

## ✨ Why Segmenta?

If you record live sessions from platforms like **Twitch**, **YouTube**, or use **OBS** split recordings, you often end up with many timestamped chunks (`.ts` or `.mp4`). **Segmenta** automates the tedious work:

- 🧵 **Smart Merging**: Groups files by source and date, then joins them in perfect chronological order.
- ⚡ **GPU Accelerated**: Prefers your NVIDIA (NVENC), Intel (QSV), or AMD (AMF) hardware for blazing-fast HEVC encoding.
- 📁 **Auto-Organization**: Creates beautifully named folders and files based on your preferences.
- 📊 **Real-time Progress**: A live ASCII progress bar keeps you updated on the transcoding status.
- 🖼️ **Preview Sheets by Default**: After each output `.mp4`, Segmenta generates a thumbnail sheet preview with a full metadata header.

---

## ⚖️ Disclaimer & Scope

**Segmenta is intended for legal and personal archival purposes only.**

- **Local Files Only**: This tool strictly processes files already present on your local disk.
- **No Downloading**: It does not contain functionality to record, download, or scrape streams from any platform.
- **User Responsibility**: Users are solely responsible for ensuring they have the legal right to process, transcode, and store the media files they use with this tool. Please respect the Terms of Service of the platforms you use.

---

## 🚀 Quick Start

### 1. Installation

Install Segmenta as a global tool using [uv](https://github.com/astral-sh/uv):

```bash
uv tool install .
```

### 2. Prepare Your Files

Ensure your input files follow one of these patterns:

- `<source>_YYYY-MM-DD_HH-MM-SS.ts` or `<source>_YYYY-MM-DD_HH-MM-SS.mp4`
- `<source>-YYYYMMDD-HHMMSS.ts` or `<source>-YYYYMMDD-HHMMSS.mp4`

**Examples:**
- `shroud_2026-03-22_09-06-01.ts`
- `shroud_2026-03-22_12-53-01.mp4`
- `swanprincess-20260403-143120.mp4`

In both formats, Segmenta extracts the model/source name and timestamp from the filename.

### 3. Run the Archiver

Simply point Segmenta to your recordings folder:

```bash
segmenta "C:\Recordings\Twitch" --source twitch
```

By default, each successful output also creates a preview image in the same folder:

- Output video: `.../<folder-name>.mp4`
- Preview sheet: `.../<folder-name>_preview.jpg`

---

## 🛠️ Advanced Customization

### Naming Templates

Fully control your archive structure with the `--name-template` option. 

**Example:**
```bash
segmenta "E:\VODs" --name-template "[{source_label}] {source} - {date_iso} [{resolution}]"
```

Available variables:
- `{source_label}`: The platform name (e.g., Twitch, YouTube Live).
- `{source}`: The creator or channel name parsed from the file.
- `{show}`: Custom session label (default: "Session").
- `{month_abbr}`, `{day}`, `{year}`: Date components.
- `{date_iso}`: The full date (YYYY-MM-DD).
- `{resolution}`: The detected video height (e.g., 1080p).

Run `segmenta --print-template-vars` for a full list of options.

### Encoder Options

Segmenta automatically detects and prefers GPU encoders. You can manually override this:

```bash
# Force CPU (high quality, slow)
segmenta "input" --encoder cpu --crf 22

# Force NVIDIA NVENC
segmenta "input" --encoder nvenc --cq 24
```

### Preview Sheet Generation

Preview generation is enabled by default and runs on the resulting `.mp4` file.

- Default layout: `3 x 9` tiles
- Tile width: `400px`
- Styling: black background, full technical header, per-tile timestamps
- Performance mode: fast keyframe sampling with multithreaded decode and FFmpeg scaling

Disable preview generation if needed:

```bash
segmenta "input" --no-thumbnail
```

### Source File Deletion

Segmenta no longer prompts interactively to delete processed source segment files (`.ts`/`.mp4`).

- Source files are kept by default.
- To delete processed source files explicitly, use:

```bash
segmenta "input" --delete-original
```

- `--keep-source-files` always preserves source segment files, even if `--delete-original` is set.

---

## 🌐 Supported Source Presets

Segmenta comes with built-in labels for many popular platforms:

- **General**: `platform`, `obs`, `custom`
- **Social**: `twitch`, `youtube-live`, `kick`, `tiktok-live`, `rumble`, `vimeo-livestream`
- **Archive Compatible**: `chaturbate`, `stripchat`, `camsoda`, and many more.

*Run `segmenta --help` to see the full list of supported presets. Use `--source custom --source-label "My App"` for unsupported platforms.*

---

## 📝 Requirements

- **Python 3.10+**
- **FFmpeg & FFprobe**: Must be installed and available in your system `PATH`.

---

## 📦 Publishing (PyPI + GitHub)

Segmenta is published as a standard Python package and can be installed as a `uv` tool.

### Install after publish

```bash
uv tool install segmenta-archiver
```

### Release flow

1. Bump version in `pyproject.toml` and `src/segmenta/__init__.py`.
2. Create and push a Git tag (for example `v0.1.3`).
3. Create a GitHub Release from that tag.
4. GitHub Actions will build with `uv build` and publish to PyPI automatically.

### One-time PyPI setup (Trusted Publishing)

In PyPI project settings, add a trusted publisher with:

- **Owner**: your GitHub org/user
- **Repository**: `segmenta` repository name
- **PyPI Project Name**: `segmenta-archiver`
- **Workflow**: `.github/workflows/publish.yml`
- **Environment**: `pypi`

No PyPI API token is required when using trusted publishing.
