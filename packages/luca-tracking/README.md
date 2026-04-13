# luca-tracking

Orkiestrator use-case spinający przepływ od wejścia do adapterów wyjściowych.

Rekonstrukcja `XYZ` używana przez pipeline offline/live korzysta ze współdzielonego modułu
`luca_processing.world_projection`, dzięki czemu tryb tracking i ROS2 używają dokładnie tego samego kodu geometrii.

## Public API

Sekcja odzwierciedla eksporty deklarowane w module inicjalizującym pakiet.

- `run_calibrate`
- `run_compare`
- `run_ros2`
- `run_tracking`
- `PipelineConfig`
- `track_video`
- `TrackerConfig`
- `SimpleMultiTracker`
- `SingleObjectEKFTracker`
- `choose_main_track`
- `run_tracker_with_config`

## Przełączniki eksperymentalne use-case

Warstwa use-case wspiera dwa przełączniki eksperymentalne:

- `experimental_mode` — aktywuje bezpieczne strojenie heurystyk toru (bardziej konserwatywny start, większa ochrona przed jitterem),
- `experimental_adaptive_association` — dodatkowo zaostrza reguły parowania detekcji do torów.

### Ograniczenia

- Przełączniki wpływają na runtime pipeline i nie zmieniają kontraktu danych wyjściowych.
- Tryb eksperymentalny może poprawić stabilność w trudnych scenach, ale bywa bardziej restrykcyjny (ryzyko wzrostu `lost_frames`).
- Każda zmiana tych flag powinna przejść benchmark porównawczy względem baseline.
