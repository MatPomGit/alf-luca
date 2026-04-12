# luca-tracking

Orkiestrator use-case spinający przepływ od wejścia do adapterów wyjściowych.

Rekonstrukcja `XYZ` używana przez pipeline offline/live korzysta ze współdzielonego modułu
`luca_processing.world_projection`, dzięki czemu tryb tracking i ROS2 używają dokładnie tego samego kodu geometrii.

## Public API

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
