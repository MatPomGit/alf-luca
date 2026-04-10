from __future__ import annotations

import sys

from luca_input import RuntimePathResolver
from luca_tracking import run_calibrate, run_compare, run_ros2, run_tracking

from .parser import build_parser


def main() -> None:
    """Uruchamia adapter CLI i deleguje wykonanie do usług aplikacyjnych."""
    # Utrzymujemy pojedynczy resolver runtime, aby wszystkie artefakty trafiały do jednego runu.
    RuntimePathResolver.for_current_process().ensure_output_dir()
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])

    if args.command == "calibrate":
        run_calibrate(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file)
    elif args.command == "track":
        try:
            run_tracking(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "compare":
        run_compare(args.reference, args.candidate, args.output_csv, args.report_pdf)
    elif args.command == "ros2":
        run_ros2(args)
    else:
        parser.error(f"Nieobsługiwane polecenie: {args.command}")
