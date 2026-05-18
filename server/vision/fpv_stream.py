"""FPV camera stream handling for the IP Webcam feed."""

from dataclasses import dataclass


@dataclass
class FPVStream:
    """Placeholder OpenCV stream handler."""

    source_url: str = "http://192.168.1.2:8080/video"

    def open(self) -> None:
        """Open the stream connection."""
        return None
