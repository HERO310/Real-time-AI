from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class ModeConfig:
    window_sec: float
    step_sec: float
    sample_frames: int
    vote_horizon_windows: int
    trigger_ratio: float
    release_ratio: float
    cooldown_windows: int
    min_alert_gap_sec: float
    instant_alert_ratio: float
    severity_alert_ratio: float


@dataclass(frozen=True)
class CrimeProfile:
    key: str
    display_name: str
    prompt_focus: str
    keywords: Tuple[str, ...]
    event_tags: Tuple[str, ...]


MODE_PRESETS: Dict[str, ModeConfig] = {
    "fast": ModeConfig(
        window_sec=3.0,
        step_sec=1.0,
        sample_frames=12,
        vote_horizon_windows=1,
        trigger_ratio=0.46,
        release_ratio=0.28,
        cooldown_windows=0,
        min_alert_gap_sec=0.0,
        instant_alert_ratio=0.60,
        severity_alert_ratio=0.72,
    ),
    "high_accuracy": ModeConfig(
        window_sec=10.0,
        step_sec=5.0,
        sample_frames=18,
        vote_horizon_windows=3,
        trigger_ratio=0.58,
        release_ratio=0.36,
        cooldown_windows=2,
        min_alert_gap_sec=5.0,
        instant_alert_ratio=0.70,
        severity_alert_ratio=0.82,
    ),
}


CRIME_PROFILES: Dict[str, CrimeProfile] = {
    "all": CrimeProfile(
        key="all",
        display_name="all crimes",
        prompt_focus="any suspicious or harmful event",
        keywords=(
            "crime", "suspicious", "harmful", "violence", "theft", "intrusion", "fire",
            "accident", "fall", "vandalism", "weapon", "assault", "fight", "robbery",
        ),
        event_tags=(
            "violence", "theft", "intrusion", "fire", "crash", "fall", "medical", "vandalism", "other",
        ),
    ),
    "stealing": CrimeProfile(
        key="stealing",
        display_name="stealing/theft",
        prompt_focus="stealing, theft, shoplifting, robbery, burglary, pickpocketing, or snatching",
        keywords=("theft", "steal", "stealing", "shoplifting", "robbery", "burglary", "pickpocket", "snatching", "loot", "looting"),
        event_tags=("theft", "intrusion", "other"),
    ),
    "assault": CrimeProfile(
        key="assault",
        display_name="assault/fight",
        prompt_focus="assault, fight, attack, brawl, violence, or physical confrontation",
        keywords=("assault", "fight", "attack", "brawl", "violence", "battery", "clash"),
        event_tags=("violence", "other"),
    ),
    "fire": CrimeProfile(
        key="fire",
        display_name="fire/arson",
        prompt_focus="fire, smoke, flame, burning, ignition, or arson",
        keywords=("fire", "smoke", "flame", "burn", "arson", "ignition", "ember"),
        event_tags=("fire", "other"),
    ),
    "intrusion": CrimeProfile(
        key="intrusion",
        display_name="intrusion/trespassing",
        prompt_focus="intrusion, trespassing, break-in, unauthorized entry, or forced entry",
        keywords=("intrusion", "trespass", "trespassing", "break-in", "unauthorized", "forced entry", "intruder"),
        event_tags=("intrusion", "other"),
    ),
    "accident": CrimeProfile(
        key="accident",
        display_name="accident/crash",
        prompt_focus="accident, crash, collision, severe fall, or injury",
        keywords=("accident", "crash", "collision", "fall", "injury", "impact"),
        event_tags=("crash", "fall", "medical", "other"),
    ),
    "vandalism": CrimeProfile(
        key="vandalism",
        display_name="vandalism/damage",
        prompt_focus="vandalism, damage, destruction, graffiti, or property damage",
        keywords=("vandalism", "damage", "destruction", "graffiti", "smash", "break"),
        event_tags=("vandalism", "other"),
    ),
    "robbery": CrimeProfile(
        key="robbery",
        display_name="robbery",
        prompt_focus="robbery, theft with force, or theft involving threat or weapon",
        keywords=("robbery", "theft", "weapon", "threat", "snatching", "armed"),
        event_tags=("theft", "violence", "other"),
    ),
}


CRIME_ALIASES = {
    "theft": "stealing",
    "steal": "stealing",
    "shoplifting": "stealing",
    "stealing": "stealing",
    "assaults": "assault",
    "fight": "assault",
    "fighting": "assault",
    "violence": "assault",
    "violent": "assault",
    "arson": "fire",
    "intrude": "intrusion",
    "trespass": "intrusion",
    "trespassing": "intrusion",
    "crash": "accident",
    "collision": "accident",
    "fall": "accident",
    "injury": "accident",
    "medical": "accident",
    "medical_distress": "accident",
    "damage": "vandalism",
    "robber": "robbery",
    "robbery": "robbery",
}


def normalize_crime_target(value: str) -> str:
    key = str(value or "all").strip().lower().replace(" ", "_").replace("-", "_")
    return CRIME_ALIASES.get(key, key)


def resolve_crime_target(value: str) -> CrimeProfile:
    key = normalize_crime_target(value)
    if key not in CRIME_PROFILES:
        raise ValueError(
            f"Unknown crime target: {value}. Choose one of: {', '.join(sorted(CRIME_PROFILES.keys()))}"
        )
    return CRIME_PROFILES[key]


def validate_config(cfg: ModeConfig) -> None:
    if cfg.window_sec <= 0 or cfg.step_sec <= 0:
        raise ValueError("window_sec and step_sec must be > 0")
    if cfg.sample_frames <= 0:
        raise ValueError("sample_frames must be > 0")
    if not (0.0 <= cfg.trigger_ratio <= 1.0 and 0.0 <= cfg.release_ratio <= 1.0):
        raise ValueError("trigger_ratio/release_ratio must be in [0,1]")
    if cfg.trigger_ratio <= cfg.release_ratio:
        raise ValueError("trigger_ratio must be greater than release_ratio")
    if not (0.0 <= cfg.instant_alert_ratio <= 1.0):
        raise ValueError("instant_alert_ratio must be in [0,1]")
    if not (0.0 <= cfg.severity_alert_ratio <= 1.0):
        raise ValueError("severity_alert_ratio must be in [0,1]")


def apply_overrides(base: ModeConfig, args) -> ModeConfig:
    """Apply optional CLI overrides to a mode config."""
    cfg = ModeConfig(**base.__dict__)
    for field in cfg.__dict__.keys():
        v = getattr(args, field, None)
        if v is not None:
            setattr(cfg, field, v)
    validate_config(cfg)
    return cfg
