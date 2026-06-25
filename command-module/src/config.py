from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    host: str = "0.0.0.0"  # nosec B104 — intentional: LAN-only service
    port: int = 8081
    log_level: str = "info"

    # Inference Node
    inference_node_url: str = "http://localhost:8001"
    inference_timeout_s: float = 10.0
    inference_offline_threshold_s: float = 60.0

    # Database
    database_url: str = "postgresql+asyncpg://peekaboo:peekaboo@localhost/peekaboo"

    # Storage — "local" or "s3"
    storage_backend: str = "local"
    recordings_path: str = "/data/recordings"
    # S3 (only used when storage_backend=s3)
    s3_bucket: str = ""
    s3_prefix: str = "recordings"
    aws_region: str = "us-east-1"

    # MQTT control channel (camera reboot/diagnostics)
    mqtt_broker_url: str = "mqtt://localhost:1883"  # legacy; superseded by host/port below
    mqtt_broker_host: str = "127.0.0.1"
    mqtt_broker_port: int = 1883
    mqtt_username: str = "command-module"
    mqtt_password: str = ""
    mqtt_cmd_prefix: str = "peekaboo/cmd"
    mqtt_status_prefix: str = "peekaboo/status"

    # Camera health
    camera_heartbeat_timeout_s: float = 30.0

    # Recording retention
    recording_retention_days: int = 30
    recording_min_free_gb: float = 5.0

    # Face recognition cooldown for known persons across all cameras (seconds)
    known_person_cooldown_s: int = 900

    # Webhooks
    webhook_timeout_s: float = 5.0

    # API Authentication
    api_key: str = "change-me-in-production"  # Override via .env: API_KEY=...


settings = Settings()
