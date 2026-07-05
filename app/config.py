# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Configuration (pydantic-settings). Nothing here is persisted; read once at startup."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR.parent / "config"
SKILLS_DIR = BASE_DIR.parent / "skills"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CN_", extra="ignore")
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 500
    llm_temperature: float = 0.2
    # provider: "anthropic" | "openai_compatible" | "ollama"
    llm_provider: str = "anthropic"
    token_target: int = 800
    token_hard_cap: int = 2000
    # data source mode: "sim" (default, no config needed) | "prometheus" | "datadog"
    data_mode: str = "sim"
    customer_name: str = "DemoCorp"
    zdr_mode: bool = True
    # Security default: bind loopback only. A zero-data-retention tool should not listen on
    # the LAN unless the operator explicitly opts in with CN_HOST=0.0.0.0.
    host: str = "127.0.0.1"
    port: int = 8000

    # BYO-model: OpenAI-compatible endpoint (vLLM, LiteLLM, OpenAI itself, Azure-OpenAI-compatible proxy, etc.)
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # BYO-model: local Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # Slack Incoming Webhook (optional; empty = disabled)
    slack_webhook_url: str = ""

    # --- Prometheus (real metrics connector; optional) ---
    prometheus_url: str = ""
    prometheus_token: str = ""
    prometheus_timeout: float = 3.0

    # --- Datadog (real metrics+logs connector; optional) ---
    datadog_api_key: str = ""
    datadog_app_key: str = ""
    datadog_site: str = "datadoghq.com"
    datadog_timeout: float = 3.0

    # --- Kubernetes (real cluster connector; optional) ---
    kubeconfig: str = ""
    k8s_timeout: float = 5.0

    # --- GitHub (recent changes connector; optional) ---
    github_token: str = ""
    github_repo: str = ""           # owner/name
    github_timeout: float = 5.0

    # --- API token (optional; when set, all write endpoints require Bearer auth) ---
    api_token: str = ""

    @property
    def prometheus_enabled(self) -> bool:
        """True only when the env needed to reach Prometheus is actually set."""
        return bool(self.prometheus_url)

    @property
    def datadog_enabled(self) -> bool:
        """True only when both Datadog API and application keys are set."""
        return bool(self.datadog_api_key) and bool(self.datadog_app_key)

    @property
    def k8s_enabled(self) -> bool:
        """True when a kubeconfig is set or we are running in-cluster."""
        if self.kubeconfig:
            return True
        return Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists()

    @property
    def github_enabled(self) -> bool:
        """True only when both GitHub token and repo are set."""
        return bool(self.github_token) and bool(self.github_repo)

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai_compatible":
            return bool(self.openai_base_url) and bool(self.openai_api_key)
        if self.llm_provider == "ollama":
            return bool(self.ollama_base_url)
        return False

    @property
    def active_provider(self) -> str:
        """Name of the provider actually in use, else 'deterministic'."""
        return self.llm_provider if self.llm_enabled else "deterministic"


@lru_cache
def get_settings() -> "Settings":
    return Settings()


@lru_cache
def load_patterns() -> dict:
    with open(CONFIG_DIR / "patterns.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["patterns"]


@lru_cache
def load_skill_md() -> str:
    """Prefer the richer specialized.md (per-customer investigation logic); fall back to
    the legacy customer.skill.md; else empty string. Never instructions -- always DATA."""
    specialized = SKILLS_DIR / "specialized.md"
    if specialized.exists():
        return specialized.read_text(encoding="utf-8")
    legacy = SKILLS_DIR / "customer.skill.md"
    return legacy.read_text(encoding="utf-8") if legacy.exists() else ""
