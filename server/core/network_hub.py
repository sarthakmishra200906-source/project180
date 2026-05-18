"""Local TCP or HTTP hub for phone and ESP32 communication."""

from dataclasses import dataclass


@dataclass
class NetworkHub:
    """Placeholder network coordinator."""

    host: str = "0.0.0.0"
    port: int = 8787

    def start(self) -> None:
        """Start the server loop."""
        return None
