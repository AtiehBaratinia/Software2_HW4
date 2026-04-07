#!/usr/bin/env python3
"""
Response spectrum utility for FLAC2D 9.6 (Itasca) acceleration histories.

Typical workflow:
1) Export an acceleration history from FLAC2D to a text/CSV file.
2) Run this script to compute Sd/Sv/Sa/PSv/PSa over a period range.
3) Use the generated CSV for plotting or design checks.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


def _parse_history_lines(
    path: Path,
    time_col: int = 0,
    acc_col: int = 1,
    skip_rows: int = 0,
) -> Tuple[List[float], List[float], bool]:
    """
    Parse history file and return (time, acceleration, has_time_column).

    Accepted formats:
    - 2+ columns (CSV or whitespace): time_col and acc_col are used.
    - 1 column: only acceleration values are read (time built from --dt).
    """
    rows: List[List[float]] = []
    with path.open("r", encoding="utf-8") as f:
        for _ in range(skip_rows):
            next(f, None)
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Allow both CSV and whitespace-separated lines.
            parts = [p for p in line.replace(",", " ").split() if p]
            try:
                rows.append([float(p) for p in parts])
            except ValueError as exc:
                raise ValueError(f"Could not parse numeric values from line: {line}") from exc

    if not rows:
        raise ValueError(f"No numeric history data found in {path}")

    col_count = len(rows[0])
    if any(len(r) != col_count for r in rows):
        raise ValueError("Inconsistent number of columns in history file")

    if col_count == 1:
        times = [0.0] * len(rows)
        acc = [r[0] for r in rows]
        return times, acc, False

    if time_col >= col_count or acc_col >= col_count:
        raise ValueError(
            f"Requested columns out of range. file has {col_count} columns, "
            f"time_col={time_col}, acc_col={acc_col}"
        )

    times = [r[time_col] for r in rows]
    acc = [r[acc_col] for r in rows]
    return times, acc, True


def load_history(
    file_path: str,
    dt: float | None = None,
    time_col: int = 0,
    acc_col: int = 1,
    skip_rows: int = 0,
    accel_scale: float = 1.0,
) -> Tuple[List[float], List[float], float]:
    """
    Load acceleration history and return (time, acceleration, dt).

    accel_scale multiplies acceleration values. Use 9.80665 when input is in g.
    """
    path = Path(file_path)
    times, acc, has_time_col = _parse_history_lines(
        path=path, time_col=time_col, acc_col=acc_col, skip_rows=skip_rows
    )

    acc = [a * accel_scale for a in acc]

    if has_time_col:
        if len(times) < 2:
            raise ValueError("Need at least 2 points when time column is provided")
        dts = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        if any(x <= 0.0 for x in dts):
            raise ValueError("Time values must be strictly increasing")
        dt_avg = sum(dts) / len(dts)
        # FLAC history output is usually fixed-step; tolerate minor floating error.
        max_dev = max(abs(x - dt_avg) for x in dts)
        if dt_avg > 0 and max_dev / dt_avg > 1.0e-3:
            raise ValueError(
                "Time step is not uniform. Resample your history before using this script."
            )
        return times, acc, dt_avg

    if dt is None or dt <= 0.0:
        raise ValueError("For single-column acceleration input, provide a positive --dt")
    times = [i * dt for i in range(len(acc))]
    return times, acc, dt


def oscillator_response_newmark(
    acceleration: Sequence[float],
    dt: float,
    period: float,
    damping_ratio: float,
) -> Tuple[float, float, float]:
    """
    Return peak (Sd, Sv, Sa) for one SDOF oscillator period.

    Sd: max relative displacement
    Sv: max relative velocity
    Sa: max absolute acceleration
    """
    if period <= 0.0:
        pga = max(abs(a) for a in acceleration)
        return 0.0, 0.0, pga

    beta = 0.25
    gamma = 0.5

    w = 2.0 * math.pi / period
    m = 1.0
    k = w * w
    c = 2.0 * damping_ratio * w

    a0 = 1.0 / (beta * dt * dt)
    a1 = gamma / (beta * dt)
    a2 = 1.0 / (beta * dt)
    a3 = 1.0 / (2.0 * beta) - 1.0
    a4 = gamma / beta - 1.0
    a5 = dt * 0.5 * (gamma / beta - 2.0)
    a6 = dt * (1.0 - gamma)
    a7 = gamma * dt

    keff = k + a0 * m + a1 * c

    u = 0.0
    v = 0.0
    rel_acc = -acceleration[0]  # from m*u'' + c*u' + k*u = -m*ag

    sd = abs(u)
    sv = abs(v)
    sa = abs(rel_acc + acceleration[0])

    for i in range(len(acceleration) - 1):
        p_next = -acceleration[i + 1]
        p_eff = (
            p_next
            + m * (a0 * u + a2 * v + a3 * rel_acc)
            + c * (a1 * u + a4 * v + a5 * rel_acc)
        )

        u_next = p_eff / keff
        rel_acc_next = a0 * (u_next - u) - a2 * v - a3 * rel_acc
        v_next = v + a6 * rel_acc + a7 * rel_acc_next

        abs_acc = rel_acc_next + acceleration[i + 1]

        sd = max(sd, abs(u_next))
        sv = max(sv, abs(v_next))
        sa = max(sa, abs(abs_acc))

        u, v, rel_acc = u_next, v_next, rel_acc_next

    return sd, sv, sa


def build_periods(
    t_min: float,
    t_max: float,
    count: int,
    spacing: str = "log",
) -> List[float]:
    if count < 2:
        raise ValueError("count must be >= 2")
    if t_min <= 0.0 or t_max <= 0.0 or t_max <= t_min:
        raise ValueError("Require 0 < t_min < t_max")

    if spacing == "linear":
        step = (t_max - t_min) / (count - 1)
        return [t_min + i * step for i in range(count)]

    # default: logarithmic spacing
    lmin = math.log10(t_min)
    lmax = math.log10(t_max)
    step = (lmax - lmin) / (count - 1)
    return [10.0 ** (lmin + i * step) for i in range(count)]


def compute_response_spectrum(
    acceleration: Sequence[float],
    dt: float,
    periods: Iterable[float],
    damping_ratio: float = 0.05,
) -> List[Tuple[float, float, float, float, float, float]]:
    """
    Compute spectrum rows as:
    (Period, Sd, Sv, Sa, PSv, PSa)
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    if not (0.0 <= damping_ratio < 1.0):
        raise ValueError("damping_ratio must be in [0, 1)")
    if len(acceleration) < 2:
        raise ValueError("Need at least 2 acceleration points")

    rows: List[Tuple[float, float, float, float, float, float]] = []
    for t in periods:
        sd, sv, sa = oscillator_response_newmark(
            acceleration=acceleration, dt=dt, period=t, damping_ratio=damping_ratio
        )
        w = 0.0 if t <= 0.0 else 2.0 * math.pi / t
        psv = w * sd
        psa = w * w * sd
        rows.append((t, sd, sv, sa, psv, psa))
    return rows


def write_spectrum_csv(
    output_path: str,
    spectrum_rows: Sequence[Tuple[float, float, float, float, float, float]],
) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Period", "Sd", "Sv", "Sa", "PSv", "PSa"])
        writer.writerows(spectrum_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute response spectrum from FLAC2D acceleration history."
    )
    parser.add_argument(
        "input_file",
        help="Path to history file. Supports CSV or whitespace-separated text.",
    )
    parser.add_argument(
        "--output",
        default="response_spectrum.csv",
        help="Output CSV path (default: response_spectrum.csv)",
    )
    parser.add_argument(
        "--dt",
        type=float,
        default=None,
        help="Time step for single-column acceleration input.",
    )
    parser.add_argument(
        "--time-col",
        type=int,
        default=0,
        help="Time column index for multi-column input (default: 0).",
    )
    parser.add_argument(
        "--acc-col",
        type=int,
        default=1,
        help="Acceleration column index for multi-column input (default: 1).",
    )
    parser.add_argument(
        "--skip-rows",
        type=int,
        default=0,
        help="Number of initial rows to skip.",
    )
    parser.add_argument(
        "--accel-scale",
        type=float,
        default=1.0,
        help="Scale factor for acceleration values (use 9.80665 when input is in g).",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=0.05,
        help="Damping ratio, e.g., 0.05 for 5%% (default: 0.05).",
    )
    parser.add_argument(
        "--t-min", type=float, default=0.01, help="Minimum period (s), default 0.01."
    )
    parser.add_argument(
        "--t-max", type=float, default=5.0, help="Maximum period (s), default 5.0."
    )
    parser.add_argument(
        "--n-periods", type=int, default=200, help="Number of periods, default 200."
    )
    parser.add_argument(
        "--spacing",
        choices=("linear", "log"),
        default="log",
        help="Period spacing (linear or log), default log.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    _, acc, dt = load_history(
        file_path=args.input_file,
        dt=args.dt,
        time_col=args.time_col,
        acc_col=args.acc_col,
        skip_rows=args.skip_rows,
        accel_scale=args.accel_scale,
    )
    periods = build_periods(
        t_min=args.t_min, t_max=args.t_max, count=args.n_periods, spacing=args.spacing
    )
    spectrum = compute_response_spectrum(
        acceleration=acc, dt=dt, periods=periods, damping_ratio=args.damping
    )
    write_spectrum_csv(args.output, spectrum)

    print(f"Wrote {len(spectrum)} spectrum points to {args.output}")
    print(f"Estimated dt = {dt:.8g} s, damping = {args.damping:.4g}")


if __name__ == "__main__":
    main()
