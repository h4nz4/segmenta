import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from string import Formatter
from typing import NamedTuple


TEMPLATE_KEYS = {
    "source_label",
    "source",
    "show",
    "month_abbr",
    "day",
    "year",
    "date_iso",
    "resolution",
}


class ParsedFile(NamedTuple):
    source: str
    timestamp: datetime
    path: Path


def parse_filename(path: Path) -> ParsedFile | None:
    pattern = r"^(.+)_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.ts$"
    match = re.match(pattern, path.name)
    if not match:
        return None

    source = match.group(1)
    year, month, day, hour, minute, second = map(int, match.groups()[1:])
    try:
        timestamp = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

    return ParsedFile(source=source, timestamp=timestamp, path=path)


def scan_and_sort_ts_files(input_dir: Path) -> list[ParsedFile]:
    parsed_files: list[ParsedFile] = []
    for candidate in input_dir.glob("*.ts"):
        parsed = parse_filename(candidate.resolve())
        if parsed is not None:
            parsed_files.append(parsed)

    parsed_files.sort(key=lambda item: item.timestamp)
    return parsed_files


def group_files_by_source_and_date(
    parsed_files: list[ParsedFile],
) -> dict[tuple[str, date], list[ParsedFile]]:
    grouped: dict[tuple[str, date], list[ParsedFile]] = defaultdict(list)
    for parsed in parsed_files:
        grouped[(parsed.source, parsed.timestamp.date())].append(parsed)

    for files in grouped.values():
        files.sort(key=lambda item: item.timestamp)

    return dict(grouped)


def create_output_folder_name(
    source: str,
    scene_date: date,
    resolution_label: str,
    source_label: str,
    show_label: str,
) -> str:
    month_name = scene_date.strftime("%b")
    cleaned_source_label = source_label.strip() or "Platform"
    cleaned_show_label = show_label.strip()
    middle = f" {cleaned_show_label}" if cleaned_show_label else ""
    return (
        f"[{cleaned_source_label}] {source}{middle} - "
        f"{month_name} {scene_date.day} {scene_date.year} [{resolution_label}]"
    )


def create_output_folder_name_from_template(
    source: str,
    scene_date: date,
    resolution_label: str,
    source_label: str,
    show_label: str,
    name_template: str,
) -> str:
    cleaned_source_label = source_label.strip() or "Platform"
    cleaned_show_label = show_label.strip()

    formatter = Formatter()
    invalid_keys: set[str] = set()
    for _, field_name, _, _ in formatter.parse(name_template):
        if field_name is None:
            continue
        if field_name not in TEMPLATE_KEYS:
            invalid_keys.add(field_name)

    if invalid_keys:
        allowed = ", ".join(sorted(TEMPLATE_KEYS))
        invalid = ", ".join(sorted(invalid_keys))
        raise ValueError(f"Unknown template key(s): {invalid}. Allowed keys: {allowed}")

    values = {
        "source_label": cleaned_source_label,
        "source": source,
        "show": cleaned_show_label,
        "month_abbr": scene_date.strftime("%b"),
        "day": str(scene_date.day),
        "year": str(scene_date.year),
        "date_iso": scene_date.isoformat(),
        "resolution": resolution_label,
    }
    rendered = name_template.format(**values).strip()
    if not rendered:
        raise ValueError("Rendered template is empty. Adjust --name-template.")

    return rendered


def detect_available_hevc_encoders() -> set[str]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to query ffmpeg encoders:\n{result.stderr}")

    known = {"hevc_nvenc", "hevc_qsv", "hevc_amf", "libx265"}
    available: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in known:
            available.add(parts[1])

    return available


def resolve_encoder_choice(requested: str, available: set[str]) -> tuple[str, bool]:
    requested_normalized = requested.lower()

    if requested_normalized == "cpu":
        if "libx265" not in available:
            raise ValueError("libx265 encoder is not available in ffmpeg build")
        return "libx265", False

    if requested_normalized in {"auto", "gpu"}:
        for codec in ("hevc_nvenc", "hevc_qsv", "hevc_amf"):
            if codec in available:
                return codec, False
        if "libx265" in available:
            return "libx265", True
        raise ValueError("No supported HEVC encoder found (GPU or CPU)")

    explicit_map = {
        "nvenc": "hevc_nvenc",
        "qsv": "hevc_qsv",
        "amf": "hevc_amf",
    }
    codec = explicit_map.get(requested_normalized)
    if codec is None:
        raise ValueError(f"Unsupported encoder option: {requested}")
    if codec not in available:
        raise ValueError(f"Requested encoder '{codec}' is not available")
    return codec, False


def quality_label_for_codec(codec: str, crf: int, cq: int) -> str:
    if codec == "libx265":
        return f"CRF={crf}"
    if codec == "hevc_qsv":
        return f"GlobalQuality={cq}"
    return f"CQ={cq}"


def build_video_encoder_args(
    codec: str,
    crf: int,
    cq: int,
    preset: str,
) -> list[str]:
    if codec == "libx265":
        return ["-c:v", "libx265", "-crf", str(crf), "-preset", preset]

    if codec == "hevc_nvenc":
        return [
            "-c:v",
            "hevc_nvenc",
            "-rc",
            "vbr",
            "-cq",
            str(cq),
            "-preset",
            "p5",
        ]

    if codec == "hevc_qsv":
        return [
            "-c:v",
            "hevc_qsv",
            "-global_quality",
            str(cq),
            "-look_ahead",
            "1",
        ]

    if codec == "hevc_amf":
        return [
            "-c:v",
            "hevc_amf",
            "-rc",
            "hqvbr",
            "-qvbr_quality_level",
            str(cq),
            "-quality",
            "quality",
        ]

    raise ValueError(f"Unsupported codec selected: {codec}")


def format_seconds(total_seconds: float) -> str:
    total = max(0, int(total_seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def probe_duration_seconds(path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path.as_posix(),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    if not value:
        return None

    try:
        duration = float(value)
    except ValueError:
        return None

    if duration <= 0:
        return None
    return duration


def probe_resolution(path: Path) -> tuple[int, int] | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            path.as_posix(),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not values:
        return None

    value = values[0]
    if "x" not in value:
        return None

    width_text, height_text = value.split("x", 1)
    try:
        width = int(width_text)
        height = int(height_text)
    except ValueError:
        return None

    if width <= 0 or height <= 0:
        return None

    return width, height


def detect_group_resolution_label(parsed_files: list[ParsedFile]) -> str:
    best_width = 0
    best_height = 0
    for parsed in parsed_files:
        resolution = probe_resolution(parsed.path)
        if resolution is None:
            continue

        width, height = resolution
        if (height, width) > (best_height, best_width):
            best_width = width
            best_height = height

    if best_height <= 0:
        return "unknown"

    return f"{best_height}p"


def estimate_total_duration_seconds(parsed_files: list[ParsedFile]) -> float | None:
    durations: list[float] = []
    for parsed in parsed_files:
        duration = probe_duration_seconds(parsed.path)
        if duration is not None:
            durations.append(duration)

    if not durations:
        return None
    return sum(durations)


def render_progress_line(
    out_time_seconds: float,
    total_duration_seconds: float | None,
    speed: str | None,
    elapsed_seconds: float,
) -> None:
    bar_width = 30
    if total_duration_seconds and total_duration_seconds > 0:
        ratio = min(max(out_time_seconds / total_duration_seconds, 0.0), 1.0)
    else:
        ratio = 0.0

    filled = int(ratio * bar_width)
    bar = "#" * filled + "-" * (bar_width - filled)
    percent = ratio * 100.0

    line = f"\r[{bar}] {percent:6.2f}%"
    if total_duration_seconds and total_duration_seconds > 0:
        line += (
            f" {format_seconds(out_time_seconds)} / "
            f"{format_seconds(total_duration_seconds)}"
        )
    else:
        line += f" {format_seconds(out_time_seconds)}"

    line += f" elapsed {format_seconds(elapsed_seconds)}"
    if speed:
        line += f" speed {speed}"

    sys.stdout.write(line)
    sys.stdout.flush()


def parse_out_time_seconds(key: str, value: str) -> float | None:
    if key == "out_time_us":
        try:
            return float(value) / 1_000_000.0
        except ValueError:
            return None

    if key == "out_time_ms":
        try:
            return float(value) / 1_000_000.0
        except ValueError:
            return None

    if key == "out_time":
        parts = value.split(":")
        if len(parts) != 3:
            return None
        try:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
        except ValueError:
            return None
        return hours * 3600 + minutes * 60 + seconds

    return None


def merge_and_transcode(
    parsed_files: list[ParsedFile],
    output_path: Path,
    video_codec: str,
    crf: int,
    cq: int,
    preset: str = "medium",
) -> bool:
    temp_filelist = output_path.parent / "filelist.txt"
    with open(temp_filelist, "w", encoding="utf-8", newline="\n") as filelist_handle:
        for parsed in parsed_files:
            escaped_path = parsed.path.as_posix().replace("'", r"'\''")
            filelist_handle.write(f"file '{escaped_path}'\n")

    quality_label = quality_label_for_codec(video_codec, crf, cq)
    video_args = build_video_encoder_args(video_codec, crf, cq, preset)
    print(f"Transcoding with {video_codec} ({quality_label})...")
    total_duration_seconds = estimate_total_duration_seconds(parsed_files)
    if total_duration_seconds is not None:
        print(f"Estimated source duration: {format_seconds(total_duration_seconds)}")

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats_period",
        "1",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        temp_filelist.as_posix(),
        *video_args,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        output_path.as_posix(),
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    out_time_seconds = 0.0
    speed: str | None = None
    start_time = time.time()
    last_draw = 0.0

    try:
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                parsed_out_time = parse_out_time_seconds(key, value)
                if parsed_out_time is not None:
                    out_time_seconds = parsed_out_time

                    now = time.time()
                    if now - last_draw >= 0.25:
                        render_progress_line(
                            out_time_seconds=out_time_seconds,
                            total_duration_seconds=total_duration_seconds,
                            speed=speed,
                            elapsed_seconds=now - start_time,
                        )
                        last_draw = now
                    continue

                if key == "speed":
                    speed = value
                elif key == "progress":
                    now = time.time()
                    render_progress_line(
                        out_time_seconds=out_time_seconds,
                        total_duration_seconds=total_duration_seconds,
                        speed=speed,
                        elapsed_seconds=now - start_time,
                    )
                    last_draw = now
                    if value == "end":
                        break

        return_code = process.wait()
        stderr_output = ""
        if process.stderr is not None:
            stderr_output = process.stderr.read().strip()
    finally:
        temp_filelist.unlink(missing_ok=True)

    sys.stdout.write("\n")
    sys.stdout.flush()

    if return_code != 0:
        if stderr_output:
            print(f"FFmpeg failed:\n{stderr_output}")
        else:
            print("FFmpeg failed. No additional error output from ffmpeg.")
        return False

    return True
