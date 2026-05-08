import os
import sys


def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    term = os.environ.get("TERM", "")
    return term not in ("", "dumb")


class Palette:
    def __init__(self):
        if supports_color():
            self.red = "\033[91m"
            self.orange = "\033[38;5;208m"
            self.yellow = "\033[93m"
            self.green = "\033[92m"
            self.blue = "\033[94m"
            self.reset = "\033[0m"
        else:
            self.red = ""
            self.orange = ""
            self.yellow = ""
            self.green = ""
            self.blue = ""
            self.reset = ""


def severity_bucket(smoothed_score: float) -> str:
    if smoothed_score >= 0.75:
        return "HIGH"
    if smoothed_score >= 0.50:
        return "MEDIUM"
    if smoothed_score >= 0.30:
        return "LOW"
    return "NORMAL"


def color_for_bucket(bucket: str, palette: Palette) -> str:
    if bucket == "HIGH":
        return palette.red
    if bucket == "MEDIUM":
        return palette.orange
    if bucket == "LOW":
        return palette.yellow
    return palette.green
