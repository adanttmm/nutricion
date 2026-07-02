import os
from pathlib import Path
import yaml
from anthropic import Anthropic
from dotenv import load_dotenv
from . import token_tracker

load_dotenv()


class BaseSkill:
    MODEL = "claude-sonnet-4-6"

    def __init__(self, config_dir: str = "config"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY no encontrada.\n"
                "Copia .env.example → .env y agrega tu clave de https://console.anthropic.com/settings/keys"
            )
        self.client = Anthropic(api_key=api_key)
        self.config_dir = Path(config_dir)
        self.user_profile = self._load_yaml("user_profile.yaml")

    def _load_yaml(self, filename: str) -> dict:
        with open(self.config_dir / filename, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _call_claude(self, system: str, user_message: str, max_tokens: int = 4096) -> str:
        response = self.client.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        token_tracker.record(self.__class__.__name__, response.usage)
        return response.content[0].text

    def _save_output(self, content: str, output_dir: str, filename: str) -> Path:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        output_path = path / filename
        output_path.write_text(content, encoding="utf-8")
        return output_path
