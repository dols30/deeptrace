#!/usr/bin/env python3
"""Generate a face video with audio and submit it to the running API."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import cv2
import requests
from skimage import data


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="deeptrace-smoke-") as raw_dir:
        work = Path(raw_dir)
        image_path = work / "face.png"
        video_path = work / "face-with-audio.mp4"
        image = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(image_path), image):
            raise RuntimeError("Could not create the smoke-test image")

        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-loop", "1", "-i", str(image_path),
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=3",
                "-t", "3", "-r", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", "-y", str(video_path),
            ],
            check=True,
            timeout=60,
        )

        with video_path.open("rb") as stream:
            response = requests.post(
                "http://127.0.0.1:8080/v1/analyze",
                files={"file": (video_path.name, stream, "video/mp4")},
                timeout=600,
            )
        response.raise_for_status()
        report = response.json()
        print(json.dumps(report, indent=2))

        by_component = {item["component"]: item for item in report["components"]}
        for name in ("video", "audio"):
            status = by_component.get(name, {}).get("status")
            if status != "functional":
                raise RuntimeError(f"{name} model did not complete successfully: {status}")


if __name__ == "__main__":
    main()
