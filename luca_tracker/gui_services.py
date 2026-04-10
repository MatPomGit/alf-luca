from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from typing import Callable

from .config_model import RunConfig
from .gui_models import CalibrationConfigDTO, CompareConfigDTO, Ros2ConfigDTO


@dataclass
class GUIServiceLayer:
    """Warstwa serwisowa uruchamiająca operacje backendowe inicjowane z GUI."""

    run_tracking_impl: Callable[[RunConfig], None]
    run_calibration_impl: Callable[[str, int, int, float, str], None]
    run_compare_impl: Callable[[str, str, str, str | None], None]
    run_ros2_impl: Callable[[Namespace], None]

    @classmethod
    def create_default(cls) -> "GUIServiceLayer":
        """Buduje domyślną konfigurację serwisów opartą o moduły aplikacji."""
        # GUI korzysta wyłącznie z interfejsu usług aplikacyjnych, bez importów niskopoziomowych modułów detekcji.
        from luca_tracking.application_services import run_calibrate, run_compare, run_ros2, run_tracking

        return cls(
            run_tracking_impl=run_tracking,
            run_calibration_impl=run_calibrate,
            run_compare_impl=run_compare,
            run_ros2_impl=run_ros2,
        )

    def run_tracking(self, config: RunConfig) -> None:
        """Uruchamia pipeline śledzenia dla dostarczonego `RunConfig`."""
        self.run_tracking_impl(config)

    def run_calibration(self, config: CalibrationConfigDTO) -> None:
        """Uruchamia kalibrację kamery na podstawie DTO zakładki Calibration."""
        self.run_calibration_impl(config.calib_dir, config.rows, config.cols, config.square_size, config.output_file)

    def run_compare(self, config: CompareConfigDTO) -> None:
        """Uruchamia porównanie CSV dla DTO zakładki Compare."""
        self.run_compare_impl(config.reference, config.candidate, config.output_csv, config.report_pdf)

    def run_ros2(self, config: Ros2ConfigDTO) -> None:
        """Uruchamia węzeł ROS2 z mapowaniem pól DTO na `Namespace`."""
        self.run_ros2_impl(Namespace(**config.values))
