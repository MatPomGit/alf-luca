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
            "CalibrationStatus("
            f"intrinsics_loaded={self.intrinsics_loaded}, "
            f"pnp_points_loaded={self.pnp_points_loaded}, "
            f"pnp_solved={self.pnp_solved}, "
            f"world_projection_enabled={self.world_projection_enabled}, "
            f"intrinsics_status_code={self.intrinsics_status_code}, "
            f"pnp_points_status_code={self.pnp_points_status_code}, "
            f"solvepnp_status_code={self.solvepnp_status_code}, "
            f"ray_plane_status_code={self.ray_plane_status_code}, "
            f"world_projection_reason='{self.world_projection_reason}'"
            ")"
        )

    def to_dict(self) -> dict[str, bool | str]:
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
        }
