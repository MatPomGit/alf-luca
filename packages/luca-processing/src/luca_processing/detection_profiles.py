from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class DetectionProfile:
    """Opisuje gotowy profil parametrów detekcji dla konkretnego trybu."""

    name: str
    track_mode: str
    overrides: Dict[str, Any]
    experimental: bool = False
    description: str = ""


# Profile są opcjonalne i nadpisują tylko część pól, reszta pozostaje z konfiguracji użytkownika.
DETECTION_PROFILES: dict[str, DetectionProfile] = {
    "bright_default": DetectionProfile(
        name="bright_default",
        track_mode="brightness",
        overrides={"threshold_mode": "fixed", "threshold": 200, "blur": 11},
        description="Stabilny profil bazowy dla jasnej plamki i kontrolowanego oświetlenia.",
    ),
    "bright_low_light_exp": DetectionProfile(
        name="bright_low_light_exp",
        track_mode="brightness",
        overrides={
            "threshold_mode": "adaptive",
            "adaptive_block_size": 41,
            "adaptive_c": 4.0,
            "use_clahe": True,
            "blur": 9,
            "opening_kernel": 3,
            "closing_kernel": 3,
        },
        experimental=True,
        description="Profil eksperymentalny do scen z nierównym światłem i lokalnym migotaniem.",
    ),
    "color_robust_exp": DetectionProfile(
        name="color_robust_exp",
        track_mode="color",
        overrides={
            "color_name": "red",
            "blur": 7,
            "opening_kernel": 3,
            "closing_kernel": 3,
            "min_detection_confidence": 0.2,
        },
        experimental=True,
        description="Profil eksperymentalny zwiększający odporność na szum dla detekcji kolorowej.",
    ),
}


def available_detection_profiles(track_mode: str | None = None, include_experimental: bool = True) -> list[str]:
    """Zwraca listę nazw dostępnych profili detekcji (opcjonalnie filtrowaną)."""
    names: list[str] = []
    for profile in DETECTION_PROFILES.values():
        if track_mode and profile.track_mode != track_mode:
            continue
        if not include_experimental and profile.experimental:
            continue
        names.append(profile.name)
    return sorted(names)


def resolve_detection_profile(
    profile_name: str | None,
    track_mode: str,
    *,
    allow_experimental: bool,
) -> DetectionProfile | None:
    """Rozwiązuje profil detekcji z walidacją zgodności trybu i statusu eksperymentalnego."""
    if not profile_name:
        return None
    profile = DETECTION_PROFILES.get(profile_name)
    if profile is None:
        available = ", ".join(available_detection_profiles(track_mode=None, include_experimental=True))
        raise ValueError(f"Nieznany detector_profile `{profile_name}`. Dostępne: {available}")
    if profile.track_mode != track_mode:
        raise ValueError(
            f"Profil `{profile_name}` wspiera tylko track_mode={profile.track_mode}, "
            f"ale uruchomiono track_mode={track_mode}."
        )
    if profile.experimental and not allow_experimental:
        raise ValueError(
            f"Profil `{profile_name}` jest eksperymentalny. Ustaw `enable_experimental_profiles=true`, "
            "aby użyć tego profilu."
        )
    return profile
