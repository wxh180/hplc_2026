#!/usr/bin/env python3
"""Extract and plot a selected HPLC/SEC trace from a LabSolutions text export.

The script can run fully interactively, or accept command-line flags when
automation is preferred. It discovers available chromatogram channels from the
input file, lets the user choose one, converts retention time to elution volume
using the supplied flow rate, and saves both a TSV and publication-ready plots.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SECTION_RE = re.compile(r"^\[LC Chromatogram\((.+)\)\]$")
ABSORBANCE_RE = re.compile(r"Absorbance \(([^)]+)\)")


def sanitize_slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return slug.strip("._-") or "hplc_trace"


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def parse_sample_name(lines: list[str], fallback: str) -> str:
    for line in lines:
        if line.startswith("Sample Name\t"):
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
    return fallback


def find_chromatogram_sections(lines: list[str]) -> list[str]:
    sections: list[str] = []
    for line in lines:
        match = SECTION_RE.match(line.strip())
        if match:
            sections.append(match.group(1))
    if not sections:
        raise ValueError("No '[LC Chromatogram(...)]' sections found in the file.")
    return sections


def extract_section(lines: list[str], section_name: str) -> list[str]:
    header = f"[LC Chromatogram({section_name})]"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        raise ValueError(f"Chromatogram section not found: {section_name}")

    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = j
            break
    return lines[start:end]


def describe_section(section: list[str], section_name: str) -> dict[str, str]:
    info = {
        "section_name": section_name,
        "display_name": section_name,
        "intensity_units": "signal units",
    }
    ex_wavelength = None
    em_wavelength = None

    for line in section:
        if line.startswith("Intensity Units\t"):
            info["intensity_units"] = line.split("\t", 1)[1].strip()
        elif line.startswith("AdditionalDataInfo\t"):
            value = line.split("\t", 1)[1].strip()
            match = ABSORBANCE_RE.search(value)
            if match:
                info["display_name"] = match.group(1)
        elif line.startswith("Ex. Wavelength(nm)\t"):
            ex_wavelength = line.split("\t", 1)[1].strip()
        elif line.startswith("Em. Wavelength(nm)\t"):
            em_wavelength = line.split("\t", 1)[1].strip()

    if info["display_name"] == section_name:
        if ex_wavelength and em_wavelength:
            info["display_name"] = f"Ex {ex_wavelength} nm / Em {em_wavelength} nm"
        elif ex_wavelength:
            info["display_name"] = f"{ex_wavelength} nm"

    return info


def get_section_options(lines: list[str]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for section_name in find_chromatogram_sections(lines):
        section = extract_section(lines, section_name)
        info = describe_section(section, section_name)
        options.append(info)
    return options


def parse_chromatogram(lines: list[str], section_name: str, flow_rate: float) -> tuple[list[dict[str, float]], dict[str, str]]:
    section = extract_section(lines, section_name)
    section_info = describe_section(section, section_name)
    multiplier = 1.0
    data_start = None

    for i, line in enumerate(section):
        if line.startswith("Intensity Multiplier\t"):
            parts = line.split("\t", 1)
            multiplier = float(parts[1])
        if line.startswith("R.Time (min)") and "Intensity" in line:
            data_start = i + 1
            break

    if data_start is None:
        raise ValueError(f"Trace data header not found in section: {section_name}")

    rows: list[dict[str, float]] = []
    for line in section[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("["):
            break
        parts = line.split("\t")
        if len(parts) < 2:
            parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            time_min = float(parts[0])
            intensity = float(parts[1]) * multiplier
        except ValueError:
            continue
        rows.append(
            {
                "time_min": time_min,
                "intensity": intensity,
                "volume_ml": time_min * flow_rate,
            }
        )

    if not rows:
        raise ValueError(f"No numeric chromatogram rows found in section: {section_name}")
    return rows, section_info


def prompt_text(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def prompt_float(prompt: str, default: float | None = None) -> float:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return float(default)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number.")


def prompt_range(default_min: float, default_max: float) -> tuple[float, float]:
    print(f"Available elution volume range: {default_min:.3f} to {default_max:.3f} mL")
    xmin = prompt_float("Elution volume min (mL)", default_min)
    xmax = prompt_float("Elution volume max (mL)", default_max)
    if xmax <= xmin:
        raise ValueError("Elution volume max must be larger than min.")
    return xmin, xmax


def prompt_channel(options: list[dict[str, str]], default: str | None = None) -> str:
    print("Available chromatogram channels:")
    for idx, option in enumerate(options, start=1):
        print(f"  {idx}. {option['display_name']} [{option['section_name']}]")

    while True:
        raw = input(f"Choose channel by number or name{f' [{default}]' if default else ''}: ").strip()
        if not raw and default:
            return default
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]["section_name"]
        if raw in {option["section_name"] for option in options}:
            return raw
        for option in options:
            if raw == option["display_name"]:
                return option["section_name"]
        print("Please choose one of the listed channels.")


def filter_rows(rows: list[dict[str, float]], xmin: float, xmax: float) -> list[dict[str, float]]:
    filtered = [row for row in rows if xmin <= row["volume_ml"] <= xmax]
    if not filtered:
        raise ValueError("No trace points fall inside the requested elution-volume window.")
    return filtered


def write_tsv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["time_min", "volume_ml", "intensity"])
        writer.writeheader()
        writer.writerows(rows)


def write_metadata(
    path: Path,
    *,
    input_path: Path,
    sample_name: str,
    channel: str,
    channel_display: str,
    intensity_units: str,
    flow_rate: float,
    column_type: str,
    xmin: float,
    xmax: float,
    total_points: int,
    plotted_points: int,
) -> None:
    text = (
        f"input_file\t{input_path}\n"
        f"sample_name\t{sample_name}\n"
        f"channel\t{channel}\n"
        f"channel_display\t{channel_display}\n"
        f"intensity_units\t{intensity_units}\n"
        f"flow_rate_ml_per_min\t{flow_rate}\n"
        f"column_type\t{column_type}\n"
        f"elution_volume_min_ml\t{xmin}\n"
        f"elution_volume_max_ml\t{xmax}\n"
        f"total_points\t{total_points}\n"
        f"plotted_points\t{plotted_points}\n"
    )
    path.write_text(text, encoding="utf-8")


def make_plot(
    rows: list[dict[str, float]],
    *,
    sample_name: str,
    channel_display: str,
    intensity_units: str,
    flow_rate: float,
    column_type: str,
    xmin: float,
    xmax: float,
    output_png: Path,
) -> None:
    x = [row["volume_ml"] for row in rows]
    y = [row["intensity"] for row in rows]

    fig, ax = plt.subplots(figsize=(8.4, 4.8), dpi=300)
    ax.plot(x, y, color="#1f5aa6", lw=1.8)
    ax.set_xlim(xmin, xmax)
    ax.set_xlabel("Elution volume (mL)")
    ax.set_ylabel(f"Signal intensity ({intensity_units})")
    ax.set_title(f"{sample_name} | {channel_display}")
    ax.text(
        0.99,
        0.97,
        f"Column: {column_type}\nFlow rate: {flow_rate:g} mL/min",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#b0b0b0", "alpha": 0.92},
    )
    ax.grid(True, alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_png)
    fig.savefig(output_png.with_suffix(".pdf"))
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="LabSolutions text export")
    parser.add_argument("--channel", help="Chromatogram channel, e.g. 'MWD-Ch1'")
    parser.add_argument("--flow-rate", type=float, help="Flow rate in mL/min")
    parser.add_argument("--xmin", type=float, help="Elution volume lower bound in mL")
    parser.add_argument("--xmax", type=float, help="Elution volume upper bound in mL")
    parser.add_argument("--column-type", help="Column type to show in the plot")
    parser.add_argument("--outdir", help="Output directory")
    parser.add_argument("--prefix", help="Output filename prefix")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_path = Path(args.input) if args.input else Path(prompt_text("Path to LabSolutions .txt export"))
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    lines = read_lines(input_path)
    sample_name = parse_sample_name(lines, input_path.stem)
    section_options = get_section_options(lines)
    sections = [option["section_name"] for option in section_options]
    channel = args.channel or prompt_channel(section_options, default=sections[0])
    if channel not in sections:
        raise SystemExit(f"Channel '{channel}' not found. Available: {', '.join(sections)}")

    flow_rate = args.flow_rate if args.flow_rate is not None else prompt_float("Flow rate (mL/min)", 0.2)
    if flow_rate <= 0:
        raise SystemExit("Flow rate must be positive.")

    all_rows, section_info = parse_chromatogram(lines, channel, flow_rate)
    full_min = min(row["volume_ml"] for row in all_rows)
    full_max = max(row["volume_ml"] for row in all_rows)

    if args.xmin is not None or args.xmax is not None:
        if args.xmin is None or args.xmax is None:
            raise SystemExit("Provide both --xmin and --xmax, or neither.")
        xmin, xmax = args.xmin, args.xmax
        if xmax <= xmin:
            raise SystemExit("--xmax must be larger than --xmin.")
    else:
        xmin, xmax = prompt_range(full_min, full_max)

    column_type = args.column_type or prompt_text("Column type", "Superdex 200 Increase 10/300 GL")
    outdir = Path(args.outdir).expanduser().resolve() if args.outdir else input_path.parent / f"{sanitize_slug(sample_name)}_interactive_trace"
    prefix = args.prefix or f"{sanitize_slug(sample_name)}_{sanitize_slug(channel)}"
    outdir.mkdir(parents=True, exist_ok=True)

    plotted_rows = filter_rows(all_rows, xmin, xmax)
    tsv_path = outdir / f"{prefix}.tsv"
    png_path = outdir / f"{prefix}.png"
    meta_path = outdir / f"{prefix}_metadata.txt"

    write_tsv(tsv_path, plotted_rows)
    make_plot(
        plotted_rows,
        sample_name=sample_name,
        channel_display=section_info["display_name"],
        intensity_units=section_info["intensity_units"],
        flow_rate=flow_rate,
        column_type=column_type,
        xmin=xmin,
        xmax=xmax,
        output_png=png_path,
    )
    write_metadata(
        meta_path,
        input_path=input_path,
        sample_name=sample_name,
        channel=channel,
        channel_display=section_info["display_name"],
        intensity_units=section_info["intensity_units"],
        flow_rate=flow_rate,
        column_type=column_type,
        xmin=xmin,
        xmax=xmax,
        total_points=len(all_rows),
        plotted_points=len(plotted_rows),
    )

    print(f"Sample: {sample_name}")
    print(f"Channel: {section_info['display_name']} [{channel}]")
    print(f"Output directory: {outdir}")
    print(f"TSV: {tsv_path}")
    print(f"PNG: {png_path}")
    print(f"PDF: {png_path.with_suffix('.pdf')}")
    print(f"Metadata: {meta_path}")


if __name__ == "__main__":
    main()
