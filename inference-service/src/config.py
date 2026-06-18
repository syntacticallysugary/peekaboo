from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Settings
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "info"

    # Model Settings
    model_pack: str = "buffalo_l"
    models_dir: str = "/root/.insightface"
    gpu_id: int = 0
    det_size: int = 640
    max_detect_size: int = 640
    det_thresh: float = 0.35

    # Recognition Settings
    recognition_threshold: float = 0.65

    # Per-camera rotation — comma-separated camera IDs that need 180° rotation
    # e.g. ROTATE_CAMERAS=xiao-01,xiao-02
    rotate_cameras: str = ""

    # Command Module reporting
    command_module_url: str = "http://localhost:8000"

    # Person detector sidecar
    person_detector_url: str = "http://localhost:8002"

    # Data directory — persisted across container restarts via volume mount
    data_dir: str = "/app/data"

    # Recording storage
    recordings_dir: str = "/recordings"
    retention_days: int = 7

    class Config:
        env_file = ".env"


settings = Settings()
