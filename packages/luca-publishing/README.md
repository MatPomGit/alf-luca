# luca-publishing

Adapter wyjściowy do publikowania danych śledzenia do ROS2.

Algorytm rekonstrukcji świata (`rvec/tvec` + `pixel -> world` dla płaszczyzny `Z=const`)
jest współdzielony z trybem offline przez `luca_processing.world_projection` (jedno źródło prawdy).

## Public API

- `Ros2TopicContract`
- `Ros2TrackerConfig`
- `run_ros2_tracker_node`
