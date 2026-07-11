import os
import time
from pathlib import Path
import anthropic
import httpx
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

    MAX_TOKENS_CEILING = 64000

    def _call_claude(self, system: str, user_message: str, max_tokens: int = 4096) -> str:
        """Call Claude, auto-escalating max_tokens if the response gets truncated.

        Some reports (menu validation, meal-prep audits) vary a lot in length run to
        run — a fixed budget that was safe last week can still get clipped this week.
        Rather than fail and wait for a manual max_tokens bump, retry with a bigger
        budget (capped at MAX_TOKENS_CEILING) before giving up.
        """
        budget = max_tokens
        attempt = 0
        while True:
            attempt += 1
            response = self._stream_with_retry(system, user_message, budget)
            token_tracker.record(self.__class__.__name__, response.usage)
            if response.stop_reason != "max_tokens":
                return response.content[0].text

            if budget >= self.MAX_TOKENS_CEILING or attempt >= 3:
                raise RuntimeError(
                    f"{self.__class__.__name__}: la respuesta de Claude se truncó al alcanzar "
                    f"max_tokens={budget} incluso tras reintentar — el resultado habría quedado "
                    "incompleto. Reduce el contenido de entrada o revisa el prompt."
                )
            budget = min(budget * 2, self.MAX_TOKENS_CEILING)

    def _stream_with_retry(self, system: str, user_message: str, max_tokens: int, max_attempts: int = 3):
        """Open a streaming request, retrying on transient connection drops.

        Large max_tokens requests must stream (see
        https://github.com/anthropics/anthropic-sdk-python#long-requests), and a
        long-lived stream is more exposed to a mid-response network hiccup — the
        server or an intermediate proxy closing the connection before the chunked
        body finishes (httpx.RemoteProtocolError / anthropic.APIConnectionError).
        That's a transient fault, not a data problem, so retry with backoff instead
        of failing the whole run.
        """
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                with self.client.messages.stream(
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
                ) as stream:
                    return stream.get_final_message()
            except (anthropic.APIConnectionError, httpx.TransportError) as e:
                last_err = e
                if attempt < max_attempts:
                    time.sleep(2 ** attempt)  # 2s, 4s
        raise RuntimeError(
            f"{self.__class__.__name__}: se perdió la conexión con la API de Claude tras "
            f"{max_attempts} intentos ({last_err.__class__.__name__}: {last_err}). "
            "Probablemente un problema de red transitorio — intenta de nuevo."
        ) from last_err

    def _save_output(self, content: str, output_dir: str, filename: str) -> Path:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        output_path = path / filename
        output_path.write_text(content, encoding="utf-8")
        return output_path
