from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationStatus:
    """Wspólny status gotowości geometrii kamery dla trackingu i publikacji ROS2."""

    intrinsics_loaded: bool
    pnp_points_loaded: bool
    pnp_solved: bool
    world_projection_enabled: bool
    intrinsics_status_code: str = "INTRINSICS_UNKNOWN"
    pnp_points_status_code: str = "PNP_POINTS_UNKNOWN"
    solvepnp_status_code: str = "SOLVEPNP_UNKNOWN"
    ray_plane_status_code: str = "RAY_PLANE_UNKNOWN"
    world_projection_reason: str = ""

    def error_cause_codes(self) -> dict[str, str | None]:
        """Zwraca kody przyczyn błędów dla etapów geometrii świata."""
        return {
            "intrinsics": None if self.intrinsics_status_code == "INTRINSICS_OK" else self.intrinsics_status_code,
            "pnp_points": None if self.pnp_points_status_code in {"PNP_POINTS_OK", "PNP_POINTS_UNKNOWN"} else self.pnp_points_status_code,
            "solvepnp": None if self.solvepnp_status_code in {"SOLVEPNP_OK", "SOLVEPNP_UNKNOWN"} else self.solvepnp_status_code,
            "ray_plane": None if self.ray_plane_status_code in {"RAY_PLANE_OK", "RAY_PLANE_UNKNOWN"} else self.ray_plane_status_code,
        }

    @classmethod
    def build(
        cls,
        *,
        intrinsics_loaded: bool,
        pnp_object_points_raw: str | None,
        pnp_image_points_raw: str | None,
        pnp_solved: bool,
        intrinsics_status_code: str = "INTRINSICS_UNKNOWN",
        pnp_points_status_code: str = "PNP_POINTS_UNKNOWN",
        solvepnp_status_code: str = "SOLVEPNP_UNKNOWN",
        ray_plane_status_code: str = "RAY_PLANE_UNKNOWN",
        world_projection_reason: str = "",
    ) -> "CalibrationStatus":
        """Buduje spójny status kalibracji na bazie surowych wejść i wyniku estymacji PnP."""
        # Punkty PnP uznajemy za dostępne tylko przy kompletnym zestawie wejściowym.
        pnp_points_loaded = bool(pnp_object_points_raw and pnp_image_points_raw)
        # Rekonstrukcja świata jest aktywna wyłącznie, gdy jest pełny tor intrinsics + PnP.
        world_projection_enabled = intrinsics_loaded and pnp_points_loaded and pnp_solved
        return cls(
            intrinsics_loaded=bool(intrinsics_loaded),
            pnp_points_loaded=pnp_points_loaded,
            pnp_solved=bool(pnp_solved),
            world_projection_enabled=world_projection_enabled,
            intrinsics_status_code=intrinsics_status_code,
            pnp_points_status_code=pnp_points_status_code,
            solvepnp_status_code=solvepnp_status_code,
            ray_plane_status_code=ray_plane_status_code,
            world_projection_reason=world_projection_reason,
        )

    def to_log_message(self) -> str:
        """Formatuje status do czytelnej linii logu CLI/GUI."""
        return (
            "XYZ diagnostics | "
            f"intrinsics_loaded={self.intrinsics_loaded}, pnp_points_loaded={self.pnp_points_loaded}, "
            f"pnp_solved={self.pnp_solved}, world_projection_enabled={self.world_projection_enabled}, "
            f"intrinsics={self.intrinsics_status_code}, pnp_points={self.pnp_points_status_code}, "
            f"solvepnp={self.solvepnp_status_code}, ray_plane={self.ray_plane_status_code}, "
            f"causes={self.error_cause_codes()}, reason='{self.world_projection_reason}'"
        )

    def to_dict(self) -> dict[str, bool | str | dict[str, str | None]]:
        """Konwertuje status do słownika diagnostycznego gotowego do serializacji JSON."""
        return {
            "intrinsics_loaded": self.intrinsics_loaded,
            "pnp_points_loaded": self.pnp_points_loaded,
            "pnp_solved": self.pnp_solved,
            "world_projection_enabled": self.world_projection_enabled,
            "intrinsics_status_code": self.intrinsics_status_code,
            "pnp_points_status_code": self.pnp_points_status_code,
            "solvepnp_status_code": self.solvepnp_status_code,
            "ray_plane_status_code": self.ray_plane_status_code,
            "world_projection_reason": self.world_projection_reason,
            "error_cause_codes": self.error_cause_codes(),
        }
