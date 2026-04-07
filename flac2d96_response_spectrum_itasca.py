#!/usr/bin/env python3
"""
Response spectrum utility for FLAC2D 9.6 using the Itasca Python API.

This script is intended to run from inside FLAC2D's Python environment:
    import itasca as it

Typical use:
1) Create histories in FLAC2D (example):
      model history name 'dyn_time' dynamic time-total
      zone history name 'agx' acceleration-x position (0,0)
2) Run this script:
      python flac2d96_response_spectrum_itasca.py --acc-history agx --time-history dyn_time
3) The script writes Period, Sd, Sv, Sa, PSv, PSa to a CSV file.
"""

from __future__ import annotations

import argparse
import csv
import math
from typing import Iterable, List, Sequence, Tuple

try:
    import itasca as it  # type: ignore
except ModuleNotFoundError:
    it = None


def _assert_valid_itasca_api() -> None:
    """
    Validate that we are using the FLAC2D embedded itasca API.

    A PyPI package named `itasca` exists but does not expose FLAC2D objects
    like `history`. Users may accidentally install that package and see
    AttributeError errors.
    """
    if it is None:
        raise RuntimeError(
            "Could not import `itasca`.\n"
            "Run this script from FLAC2D 9.6 Python (Program -> Python), "
            "not from a normal system shell."
        )

    if not hasattr(it, "history") or not hasattr(it.history, "get"):
        it_mod_path = getattr(it, "__file__", "<embedded>")
        raise RuntimeError(
            "Loaded an `itasca` module without FLAC2D history API.\n"
            f"Module path: {it_mod_path}\n"
            "This usually means the PyPI package `itasca` was installed "
            "(pip install itasca), which is not the FLAC2D embedded API.\n"
            "Use FLAC2D's built-in Python to run this script, or use the "
            "file-based script `flac2d96_response_spectrum.py` instead."
        )


def _is_monotonic_non_decreasing(values: Sequence[float]) -> bool:
    return all(values[i + 1] >= values[i] for i in range(len(values) - 1))


def _history_to_series(raw_data: object) -> List[float]:
    """
    Convert possible `it.history.get` return shapes into a 1D float series.

    `it.history.get` may return a simple vector or paired x-y data depending
    on context/version. This function handles common forms robustly.
    """
    if hasattr(raw_data, "tolist"):
        raw_data = raw_data.tolist()

    if isinstance(raw_data, (int, float)):
        return [float(raw_data)]

    if not isinstance(raw_data, (list, tuple)):
        raise ValueError(f"Unsupported history container type: {type(raw_data)}")
    if len(raw_data) == 0:
        return []

    first = raw_data[0]
    if not isinstance(first, (list, tuple)):
        return [float(x) for x in raw_data]

    # Case A: matrix-like (N x M)
    if len(first) >= 2 and len(raw_data) >= 2:
        col0 = [float(row[0]) for row in raw_data]
        col1 = [float(row[1]) for row in raw_data]
        if _is_monotonic_non_decreasing(col0) and not _is_monotonic_non_decreasing(col1):
            return col1
        if _is_monotonic_non_decreasing(col1) and not _is_monotonic_non_decreasing(col0):
            return col0
        # Default assumption for paired history output is [x, y].
        return col1

    # Case B: transposed pair (2 x N)
    if len(raw_data) == 2 and isinstance(raw_data[1], (list, tuple)):
        row0 = [float(v) for v in raw_data[0]]
        row1 = [float(v) for v in raw_data[1]]
        if _is_monotonic_non_decreasing(row0) and not _is_monotonic_non_decreasing(row1):
            return row1
        if _is_monotonic_non_decreasing(row1) and not _is_monotonic_non_decreasing(row0):
            return row0
        return row1

    raise ValueError("Unsupported nested history data shape from it.history.get")


def _get_history_values(history_name: str) -> List[float]:
    _assert_valid_itasca_api()
    raw = it.history.get(history_name)
    values = _history_to_series(raw)
    if len(values) < 2:
        raise ValueError(f"History '{history_name}' has fewer than 2 points")
    return values


def _estimate_uniform_dt(time_series: Sequence[float]) -> float:
    dts = [time_series[i + 1] - time_series[i] for i in range(len(time_series) - 1)]
    if any(dt <= 0.0 for dt in dts):
        raise ValueError("Time history must be strictly increasing")
    dt_avg = sum(dts) / len(dts)
    max_dev = max(abs(dt - dt_avg) for dt in dts)
    if dt_avg > 0.0 and (max_dev / dt_avg) > 1.0e-3:
        raise ValueError("Time history is not uniform; resample before spectrum analysis")
    return dt_avg


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
    rel_acc = -acceleration[0]  # m*u'' + c*u' + k*u = -m*ag

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


def build_periods(t_min: float, t_max: float, count: int, spacing: str = "log") -> List[float]:
    if count < 2:
        raise ValueError("count must be >= 2")
    if t_min <= 0.0 or t_max <= 0.0 or t_max <= t_min:
        raise ValueError("Require 0 < t_min < t_max")

    if spacing == "linear":
        step = (t_max - t_min) / (count - 1)
        return [t_min + i * step for i in range(count)]

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
        description="Compute response spectrum from FLAC2D histories using import itasca."
    )
    parser.add_argument(
        "--acc-history",
        required=True,
        help="Acceleration history name/id defined in FLAC2D (e.g. agx).",
    )
    parser.add_argument(
        "--time-history",
        default=None,
        help=(
            "Optional time history name/id (recommended, e.g. dynamic time-total). "
            "If omitted, provide --dt."
        ),
    )
    parser.add_argument(
        "--dt",
        type=float,
        default=None,
        help="Time step if --time-history is not provided.",
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
        help="Damping ratio, e.g., 0.05 for 5%%.",
    )
    parser.add_argument("--t-min", type=float, default=0.01, help="Minimum period (s).")
    parser.add_argument("--t-max", type=float, default=5.0, help="Maximum period (s).")
    parser.add_argument(
        "--n-periods", type=int, default=200, help="Number of oscillator periods."
    )
    parser.add_argument(
        "--spacing",
        choices=("linear", "log"),
        default="log",
        help="Period spacing (linear or log).",
    )
    parser.add_argument(
        "--output",
        default="response_spectrum.csv",
        help="Output CSV path (default: response_spectrum.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    acc = _get_history_values(args.acc_history)
    acc = [a * args.accel_scale for a in acc]

    if args.time_history:
        time_values = _get_history_values(args.time_history)
        if len(time_values) != len(acc):
            raise ValueError(
                f"Length mismatch: acc-history has {len(acc)} points, "
                f"time-history has {len(time_values)} points."
            )
        dt = _estimate_uniform_dt(time_values)
    else:
        if args.dt is None or args.dt <= 0.0:
            raise ValueError("Provide --time-history or a positive --dt")
        dt = args.dt

    periods = build_periods(
        t_min=args.t_min, t_max=args.t_max, count=args.n_periods, spacing=args.spacing
    )
    spectrum = compute_response_spectrum(
        acceleration=acc, dt=dt, periods=periods, damping_ratio=args.damping
    )
    write_spectrum_csv(args.output, spectrum)

    print(f"Computed spectrum from history '{args.acc_history}'")
    print(f"Wrote {len(spectrum)} points to {args.output}")
    print(f"Estimated dt = {dt:.8g} s, damping = {args.damping:.4g}")


if __name__ == "__main__":
    main()
