import sys
from pathlib import Path
from typing import Literal

import typer

from . import __version__
from .merger import (
    create_output_folder_name,
    create_output_folder_name_from_template,
    detect_available_hevc_encoders,
    detect_group_resolution_label,
    group_files_by_source_and_date,
    merge_and_transcode,
    quality_label_for_codec,
    resolve_encoder_choice,
    scan_and_sort_media_files,
)
from .thumbnailer import Thumbnailer, ThumbnailerParams

ASCII_LOGO = r"""
   _____                                 _
  / ____|                               | |
 | (___   ___  __ _ _ __ ___   ___ _ __ | |_ __ _
  \___ \ / _ \/ _` | '_ ` _ \ / _ \ '_ \| __/ _` |
  ____) |  __/ (_| | | | | | |  __/ | | | || (_| |
 |_____/ \___|\__, |_| |_| |_|\___|_| |_|\__\__,_|
               __/ |
              |___/
"""


app = typer.Typer(
    help="Turn messy stream segments into a polished personal archive.",
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)


SOURCE_LABEL_MAP = {
    "platform": "Platform",
    "twitch": "Twitch",
    "youtube-live": "YouTube Live",
    "kick": "Kick",
    "tiktok-live": "TikTok Live",
    "facebook-gaming": "Facebook Gaming",
    "facebook-live": "Facebook Live",
    "instagram-live": "Instagram Live",
    "trovo": "Trovo",
    "rumble": "Rumble",
    "caffeine": "Caffeine",
    "picarto": "Picarto",
    "dlive": "DLive",
    "bigo-live": "Bigo Live",
    "vimeo-livestream": "Vimeo Livestream",
    "streamyard": "StreamYard",
    "chaturbate": "Chaturbate",
    "stripchat": "Stripchat",
    "jerkmate": "Jerkmate",
    "camsoda": "CamSoda",
    "livejasmin": "LiveJasmin",
    "bongacams": "BongaCams",
    "myfreecams": "MyFreeCams",
    "flirt4free": "Flirt4Free",
    "cams-com": "Cams.com",
    "imlive": "ImLive",
    "streamate": "Streamate",
    "luckycrush": "LuckyCrush",
    "cam4": "CAM4",
    "custom": "Custom",
}

SourceOption = Literal[
    "platform",
    "twitch",
    "youtube-live",
    "kick",
    "tiktok-live",
    "facebook-gaming",
    "facebook-live",
    "instagram-live",
    "trovo",
    "rumble",
    "caffeine",
    "picarto",
    "dlive",
    "bigo-live",
    "vimeo-livestream",
    "streamyard",
    "chaturbate",
    "stripchat",
    "jerkmate",
    "camsoda",
    "livejasmin",
    "bongacams",
    "myfreecams",
    "flirt4free",
    "cams-com",
    "imlive",
    "streamate",
    "luckycrush",
    "cam4",
    "custom",
]

EncoderOption = Literal["gpu", "auto", "cpu", "nvenc", "qsv", "amf"]
OnExistsOption = Literal["prompt", "skip", "overwrite", "rename"]
PresetOption = Literal[
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
    "placebo",
]


def print_encoder_inventory(available_encoders: set[str]) -> None:
    print(ASCII_LOGO)
    ordered = ["hevc_nvenc", "hevc_qsv", "hevc_amf", "libx265"]
    typer.echo("Detected HEVC encoders:")
    for encoder_name in ordered:
        status = "yes" if encoder_name in available_encoders else "no"
        typer.echo(f"- {encoder_name}: {status}")

    try:
        auto_selected, auto_fallback = resolve_encoder_choice("gpu", available_encoders)
        typer.echo(
            "Auto/gpu selection order: hevc_nvenc -> hevc_qsv -> hevc_amf -> libx265"
        )
        if auto_fallback:
            typer.echo(f"Current auto/gpu choice: {auto_selected} (CPU fallback)")
        else:
            typer.echo(f"Current auto/gpu choice: {auto_selected}")
    except ValueError as exc:
        typer.echo(f"Current auto/gpu choice: unavailable ({exc})")


def print_template_variables() -> None:
    typer.echo("Available --name-template variables:")
    typer.echo("- {source_label} -> source/platform label")
    typer.echo("- {source} -> source/channel identifier from filename")
    typer.echo("- {show} -> show/session label")
    typer.echo("- {month_abbr} -> month abbreviation, e.g. Dec")
    typer.echo("- {day} -> day of month, e.g. 14")
    typer.echo("- {year} -> year, e.g. 2025")
    typer.echo("- {date_iso} -> ISO date, e.g. 2025-12-14")
    typer.echo("- {resolution} -> detected height label, e.g. 1080p")
    typer.echo(
        "Example template: "
        "[{source_label}] {source} {show} - {month_abbr} {day} {year} [{resolution}]"
    )


def resolve_source_label(source: SourceOption, source_label: str | None) -> str:
    if source_label is not None:
        cleaned = source_label.strip()
        if not cleaned:
            raise ValueError("--source-label cannot be empty")
        return cleaned

    if source == "custom":
        raise ValueError("--source custom requires --source-label")

    return SOURCE_LABEL_MAP[source]


def version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(f"segmenta {__version__}")
    raise typer.Exit()


def choose_output_folder(
    base_output_dir: Path,
    folder_name: str,
    on_exists: OnExistsOption,
) -> Path | None:
    target_dir = base_output_dir / folder_name
    if not target_dir.exists():
        typer.echo(f"\nOutput folder: {target_dir}")
        return target_dir

    typer.echo(f"\nOutput folder already exists: {target_dir}")
    if on_exists == "skip":
        typer.echo("Skipping...")
        return None
    if on_exists == "overwrite":
        return target_dir
    if on_exists == "rename":
        counter = 1
        while target_dir.exists():
            target_dir = base_output_dir / f"{folder_name} ({counter})"
            counter += 1
        typer.echo(f"Using new folder: {target_dir.name}")
        return target_dir

    response = typer.prompt(
        "\nOptions: [s]kip, [o]verwrite, [r]ename\nChoose action",
        default="s",
    ).lower()
    if response == "s":
        typer.echo("Skipping...")
        return None
    if response == "o":
        return target_dir
    if response == "r":
        counter = 1
        while target_dir.exists():
            target_dir = base_output_dir / f"{folder_name} ({counter})"
            counter += 1
        typer.echo(f"Using new folder: {target_dir.name}")
        return target_dir

    typer.echo("Invalid option, skipping")
    return None


@app.command(
    help="Turn messy stream segments into a polished personal archive.",
)
def main(
    input_folder: Path | None = typer.Argument(None),
    output_dir: Path | None = typer.Option(None, "--output-dir", "-o"),
    source: SourceOption = typer.Option("platform", "--source"),
    source_label: str | None = typer.Option(None, "--source-label"),
    show_label: str = typer.Option("Session", "--show-label"),
    name_template: str | None = typer.Option(None, "--name-template"),
    encoder: EncoderOption = typer.Option("gpu", "--encoder"),
    crf: int = typer.Option(22, "--crf"),
    cq: int = typer.Option(22, "--cq"),
    keep_source_files: bool = typer.Option(False, "--keep-source-files"),
    delete_original: bool = typer.Option(
        False,
        "--delete-original",
        help="Delete processed source segment files (.ts/.mp4) after successful run.",
    ),
    thumbnail: bool = typer.Option(
        True,
        "--thumbnail/--no-thumbnail",
        help="Generate a preview thumbnail sheet after each successful output.",
    ),
    preset: PresetOption = typer.Option("medium", "--preset"),
    on_exists: OnExistsOption = typer.Option("prompt", "--on-exists"),
    list_encoders: bool = typer.Option(False, "--list-encoders"),
    print_template_vars: bool = typer.Option(False, "--print-template-vars"),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show Segmenta version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Turn messy stream segments into a polished personal archive."""
    if crf < 0 or crf > 51:
        typer.echo("CRF must be between 0 and 51")
        raise typer.Exit(code=1)
    if cq < 0 or cq > 51:
        typer.echo("CQ must be between 0 and 51")
        raise typer.Exit(code=1)

    try:
        available_encoders = detect_available_hevc_encoders()
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if list_encoders:
        print_encoder_inventory(available_encoders)
        raise typer.Exit(code=0)
    if print_template_vars:
        print(ASCII_LOGO)
        print_template_variables()
        raise typer.Exit(code=0)

    if input_folder is None:
        typer.echo(
            "Missing INPUT_FOLDER. Or use --list-encoders/--print-template-vars."
        )
        raise typer.Exit(code=1)

    try:
        resolved_source_label = resolve_source_label(source, source_label)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if not input_folder.exists() or not input_folder.is_dir():
        typer.echo(f"Input folder does not exist: {input_folder}")
        raise typer.Exit(code=1)

    input_folder = input_folder.resolve()
    if output_dir is None:
        output_dir = input_folder
    else:
        output_dir = output_dir.resolve()

    try:
        video_codec, fell_back_to_cpu = resolve_encoder_choice(
            encoder, available_encoders
        )
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if fell_back_to_cpu:
        typer.echo("No supported GPU HEVC encoder found, using CPU encoder libx265.")
    if video_codec != "libx265" and preset != "medium":
        typer.echo(
            "Note: --preset applies only to CPU/libx265 and is ignored for GPU modes."
        )

    parsed_files = scan_and_sort_media_files(input_folder)
    if not parsed_files:
        typer.echo(f"No valid source segment files (.ts/.mp4) found in {input_folder}")
        raise typer.Exit(code=1)

    grouped = group_files_by_source_and_date(parsed_files)
    sorted_group_keys = sorted(grouped.keys(), key=lambda key: (key[1], key[0]))
    print(ASCII_LOGO)
    typer.echo(f"Found {len(sorted_group_keys)} output group(s).")
    typer.echo(
        f"Selected encoder: {video_codec} ({quality_label_for_codec(video_codec, crf, cq)})"
    )

    success_count = 0
    skipped_count = 0
    failed_count = 0
    processed_source_files: set[Path] = set()
    output_paths: list[Path] = []
    preview_paths: list[Path] = []

    thumbnailer: Thumbnailer | None = None
    if thumbnail:
        thumbnailer = Thumbnailer(
            ThumbnailerParams(
                columns=3,
                rows=9,
                tile_width=400,
                background_color="black",
                header_font_color="white",
            )
        )

    for source_name, scene_date in sorted_group_keys:
        group_files = grouped[(source_name, scene_date)]
        resolution_label = detect_group_resolution_label(group_files)
        try:
            if name_template:
                folder_name = create_output_folder_name_from_template(
                    source=source_name,
                    scene_date=scene_date,
                    resolution_label=resolution_label,
                    source_label=resolved_source_label,
                    show_label=show_label,
                    name_template=name_template,
                )
            else:
                folder_name = create_output_folder_name(
                    source=source_name,
                    scene_date=scene_date,
                    resolution_label=resolution_label,
                    source_label=resolved_source_label,
                    show_label=show_label,
                )
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1)

        target_dir = choose_output_folder(output_dir, folder_name, on_exists)
        if target_dir is None:
            skipped_count += 1
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        output_file = target_dir / f"{target_dir.name}.mp4"

        typer.echo(f"\nGroup: {source_name} {scene_date.isoformat()}")
        typer.echo(f"Files to merge: {len(group_files)}")
        typer.echo(f"First timestamp: {group_files[0].timestamp}")
        typer.echo(f"Last timestamp: {group_files[-1].timestamp}")
        typer.echo(f"Output file: {output_file.name}")

        success = merge_and_transcode(
            parsed_files=group_files,
            output_path=output_file,
            video_codec=video_codec,
            crf=crf,
            cq=cq,
            preset=preset,
        )

        if not success:
            failed_count += 1
            if output_file.exists():
                output_file.unlink(missing_ok=True)
            typer.echo("Transcoding failed for this group.")
            continue

        success_count += 1
        output_paths.append(output_file)
        processed_source_files.update(parsed.path for parsed in group_files)

        typer.echo(f"Successfully created: {output_file}")
        typer.echo(f"File size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")

        if thumbnail and thumbnailer is not None:
            preview_source = output_file.resolve()
            if not preview_source.exists():
                typer.secho(
                    f"Warning: preview source file not found: {preview_source}",
                    fg=typer.colors.YELLOW,
                )
                continue
            preview_file = target_dir / f"{target_dir.name}_preview.jpg"
            typer.echo(f"Generating preview from: {preview_source.name}")

            def preview_progress(done: int, total: int) -> None:
                if total <= 0:
                    return
                bar_width = 30
                ratio = min(max(done / total, 0.0), 1.0)
                filled = int(ratio * bar_width)
                bar = "#" * filled + "-" * (bar_width - filled)
                line = f"\r[{bar}] {done:2d}/{total:2d} frames"
                if done >= total:
                    line += "\n"
                sys.stdout.write(line)
                sys.stdout.flush()

            try:
                thumbnailer.create_and_save_preview_thumbnails_for(
                    preview_source,
                    preview_file,
                    progress_callback=preview_progress,
                )
                preview_paths.append(preview_file)
                typer.echo(f"Preview created: {preview_file}")
            except Exception as exc:
                typer.secho(
                    f"Warning: preview generation failed for {output_file.name}: {exc}",
                    fg=typer.colors.YELLOW,
                )

    typer.echo("\nRun summary:")
    typer.echo(f"- groups total: {len(sorted_group_keys)}")
    typer.echo(f"- groups succeeded: {success_count}")
    typer.echo(f"- groups skipped: {skipped_count}")
    typer.echo(f"- groups failed: {failed_count}")
    for output_path in output_paths:
        typer.echo(f"- output: {output_path}")
    for preview_path in preview_paths:
        typer.echo(f"- preview: {preview_path}")

    if processed_source_files and delete_original and not keep_source_files:
        for source_file in sorted(processed_source_files):
            if source_file.exists():
                source_file.unlink()
        typer.echo("Deleted original processed source segment files (.ts/.mp4)")
    elif delete_original and keep_source_files:
        typer.echo(
            "--keep-source-files is set; source segment files (.ts/.mp4) were preserved."
        )


if __name__ == "__main__":
    app()


def run() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(ASCII_LOGO)
    app()
