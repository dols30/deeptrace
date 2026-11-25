from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPTRACE_", env_file=".env")

    frontend_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    app_name: str = "DeepTrace PoC"
    max_upload_mb: int = 100
    ffprobe_path: str = "ffprobe"
    keep_uploads: bool = False
    upload_dir: Path = Path("uploads")
    report_db_path: Path = Path("data/deeptrace.db")
    ffmpeg_path: str = "ffmpeg"
    frame_interval_seconds: float = 1.0
    max_frames: int = 120
    video_model: Literal["efficientnetb4", "effort"] = "efficientnetb4"
    audio_model: Literal["aasist", "aasist-l", "nes2net"] = "aasist"
    efficientnet_command: str | None = None
    efficientnet_decision_rule: Literal["default_0_5", "ffpp_c23_kaggle_v1"] = "default_0_5"
    explain: bool = False
    aasist_command: str | None = None
    effort_command: str | None = None
    nes2net_command: str | None = None
    scene_command: str | None = None
    gan_artifact_command: str | None = None
    vocoder_artifact_command: str | None = None
    micro_expression_command: str | None = None
    review_signals_command: str | None = None
    review_signals_timeout_seconds: int = 300
    # Orchestration. Both default to the previous behaviour: one-shot runner subprocesses, run one at a time.
    # model_workers keeps each runner's model loaded in a long-lived worker process (analyzers/runner.py).
    model_workers: bool = False
    # Independent detectors run concurrently, up to this many at once. Each concurrent runner holds its own
    # model in memory (RAM on CPU, VRAM on GPU), so raise this only as far as the host's memory allows.
    max_parallel_runners: int = 1
    aasist_window_mode: Literal["first", "full"] = "first"
    deployment_mode: Literal["local", "sandbox"] = "local"
    visual_weight: float = 0.5
    auth_enabled: bool = False
    local_auto_login: bool = False
    auth_mode: Literal["employee", "cognito"] = "employee"
    employee_username: str | None = None
    employee_password: str | None = None
    supervisor_username: str | None = None
    supervisor_password: str | None = None
    jwt_secret: str | None = None
    token_minutes: int = 480
    report_media_dir: Path = Path("data/report-media")
    database_url: str = "sqlite:///data/workflow.db"
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    s3_prefix: str = "deeptrace"
    use_mock_detectors: bool = False
    assistant_provider: Literal["rules", "gemini", "bedrock"] = "rules"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Bedrock assistant: the answer model reads the case record and the video model's observations.
    # IDs are cross-region inference profiles; confirm they are enabled for the account in the Bedrock console.
    bedrock_region: str | None = None
    bedrock_answer_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_video_model: str = "us.amazon.nova-lite-v1:0"
    decision_threshold: float = 0.5
    reviewer_username: str | None = None
    reviewer_password: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None
    aws_region: str | None = None
    cognito_user_pool_id: str | None = None
    cognito_app_client_id: str | None = None
    cognito_domain: str | None = None
    cognito_redirect_uri: str | None = None

    @property
    def cognito_issuer(self) -> str | None:
        if not self.aws_region or not self.cognito_user_pool_id:
            return None
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}"

    def model_post_init(self, __context: object) -> None:
        if self.local_auto_login and (self.deployment_mode != 'local' or self.auth_mode != 'employee'
                or not self.auth_enabled or not self.employee_username or not self.employee_password
                or not self.jwt_secret or len(self.jwt_secret) < 32):
            raise ValueError('Local automatic login requires local employee authentication and configured credentials/JWT secret')
        if not 0 <= self.visual_weight <= 1:
            raise ValueError("DEEPTRACE_VISUAL_WEIGHT must be between 0 and 1")
        if not 0 < self.decision_threshold < 1:
            raise ValueError("DEEPTRACE_DECISION_THRESHOLD must be between 0 and 1")
        if self.efficientnet_decision_rule == "ffpp_c23_kaggle_v1" and (self.frame_interval_seconds != 1.0 or self.max_frames != 120):
            raise ValueError("The FF++ c23 PoC rule requires the benchmark's 1-second interval and 120-frame cap")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("DEEPTRACE_S3_BUCKET is required when DEEPTRACE_STORAGE_BACKEND=s3")
        if self.review_signals_timeout_seconds < 1:
            raise ValueError("Review signal timeout must be positive")
        if not 1 <= self.max_parallel_runners <= 16:
            raise ValueError("DEEPTRACE_MAX_PARALLEL_RUNNERS must be between 1 and 16")
        if self.deployment_mode == "sandbox":
            if not self.auth_enabled:
                raise ValueError("Sandbox mode requires authentication")
            if self.auth_mode == "employee" and (not self.employee_username or not self.employee_password or not self.jwt_secret or len(self.jwt_secret) < 32):
                raise ValueError("Sandbox employee access requires credentials and a JWT secret of at least 32 characters")
            if self.auth_mode == "cognito" and (not self.cognito_issuer or not self.cognito_app_client_id):
                raise ValueError("Sandbox Cognito access requires a pool, region, and application client")
            if "*" in self.frontend_origins:
                raise ValueError("Sandbox mode requires explicit frontend origins")
            # Bedrock runs inside the deployment's own AWS account; Gemini would send media to an outside provider.
            if self.assistant_provider not in ("rules", "bedrock"):
                raise ValueError("Sandbox mode keeps media inside the AWS account; use the rules or bedrock assistant")


settings = Settings()
