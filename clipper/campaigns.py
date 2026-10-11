"""Per-creator campaign settings, loaded from campaigns/<slug>.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from clipper import shell
from clipper.pacing import Pacing

AUTO = "auto"                   # a credit handle or hashtag filled in from the video's creator
TEMPLATES = {"example"}         # campaign files that are templates to copy, never used for a job


class CampaignError(Exception):
    pass


@dataclass(frozen=True)
class Campaign:
    name: str
    slug: str
    min_len: float
    max_len: float
    credit_enabled: bool = False
    credit_handle: str | None = None
    credit_position: str = "below_headline"
    required_hashtags: list[str] = field(default_factory=list)
    vocabulary: list[str] = field(default_factory=list)
    headline_enabled: bool = True
    music_allowed: bool = False
    music_folder: Path | None = None
    music_volume_db: float = -22.0
    accent_color: str = "#FFE500"
    uppercase: bool = False
    pacing: Pacing = field(default_factory=Pacing)


def load_campaign(slug: str, root: Path) -> Campaign:
    path = Path(root) / f"{slug}.yaml"
    if not path.exists():
        raise CampaignError(f"Campaign file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise CampaignError(f"{path.name} is not valid YAML: {exc}") from exc

    def block(key: str) -> dict:
        value = raw.get(key) or {}
        if not isinstance(value, dict):
            raise CampaignError(f"{path.name}: '{key}' must be a mapping")
        return value

    name = raw.get("name")
    if not name:
        raise CampaignError(f"{path.name}: 'name' is required")

    length = block("clip_length")
    min_len, max_len = float(length.get("min", 15)), float(length.get("max", 60))
    if min_len <= 0 or max_len <= min_len:
        raise CampaignError(f"{path.name}: clip_length min must be > 0 and less than max")

    credit = block("credit")
    credit_enabled = bool(credit.get("enabled", False))
    handle, logo = credit.get("handle"), credit.get("logo")
    if credit_enabled and not handle and not logo:
        raise CampaignError(f"{path.name}: credit.enabled needs a handle or a logo")
    if credit_enabled and logo and not handle:
        # Rendering a logo overlay is not built yet; failing here beats shipping
        # clips with no credit at all.
        raise CampaignError(
            f"{path.name}: credit.logo is not supported yet — set credit.handle instead"
        )
    position = credit.get("position", "below_headline")
    if position not in {"below_headline", "top_left"}:
        raise CampaignError(f"{path.name}: credit.position must be below_headline or top_left")

    music = block("music")
    music_allowed = bool(music.get("allowed", False))
    folder = music.get("folder")
    if music_allowed and not folder:
        raise CampaignError(f"{path.name}: music.allowed needs a folder")

    captions = block("captions")
    color = captions.get("accent_color", "#FFE500")
    if not (isinstance(color, str) and color.startswith("#") and len(color) == 7):
        raise CampaignError(f"{path.name}: captions.accent_color must look like #RRGGBB")

    pacing_raw = block("pacing")
    pacing = Pacing(
        cut_pauses=bool(pacing_raw.get("cut_pauses", True)),
        max_pause=float(pacing_raw.get("max_pause", 0.3)),
        speed=float(pacing_raw.get("speed", 1.1)),
    )
    if not 1.0 <= pacing.speed <= 1.5:
        raise CampaignError(f"{path.name}: pacing.speed must be between 1.0 and 1.5")
    if not 0.15 <= pacing.max_pause <= 2.0:
        raise CampaignError(f"{path.name}: pacing.max_pause must be between 0.15 and 2.0 s")

    return Campaign(
        name=str(name),
        slug=slug,
        min_len=min_len,
        max_len=max_len,
        credit_enabled=credit_enabled,
        credit_handle=handle,
        credit_position=position,
        required_hashtags=list(raw.get("required_hashtags") or []),
        vocabulary=list(raw.get("vocabulary") or []),
        headline_enabled=bool(block("headline").get("enabled", True)),
        music_allowed=music_allowed,
        music_folder=Path(folder) if folder else None,
        music_volume_db=float(music.get("volume_db", -22.0)),
        accent_color=color,
        uppercase=bool(captions.get("uppercase", False)),
        pacing=pacing,
    )


def list_campaigns(root: Path) -> list[dict]:
    """Every campaign file, valid or not, so the UI can say why one is unusable."""
    listing = []
    for path in sorted(Path(root).glob("*.yaml")):
        slug = path.stem
        if slug in TEMPLATES:
            continue
        try:
            campaign = load_campaign(slug, root)
            listing.append({"slug": slug, "name": campaign.name, "valid": True, "error": None})
        except CampaignError as exc:
            listing.append({"slug": slug, "name": None, "valid": False, "error": str(exc)})
    return listing


def clean_handle(text: str | None) -> str | None:
    """What someone typed for the creator ("@Jane.Doe", "jane doe ", "") as an @handle, or None."""
    name = re.sub(r"[^A-Za-z0-9._]", "", text or "")[:30]
    return f"@{name}" if name else None


def creator_tag(meta) -> str | None:
    """#channelname: the creator's channel name, lower-case, letters and digits only."""
    name = re.sub(r"[^a-z0-9]", "", (getattr(meta, "channel", "") or "").lower())
    return f"#{name}" if name else None


def creator_handle(meta) -> str | None:
    """The channel's @handle, or @ChannelName (letters, digits, . and _) when there isn't one."""
    handle = getattr(meta, "channel_handle", "") or ""
    if handle.startswith("@"):
        return handle
    name = re.sub(r"[^A-Za-z0-9._]", "", getattr(meta, "channel", "") or "")
    return f"@{name}" if name else None


def for_video(campaign: Campaign, meta) -> Campaign:
    """The campaign as it applies to one video: "auto" filled in from the creator, and the
    creator's tag always among the required hashtags (once, whatever its case)."""
    handle, enabled = campaign.credit_handle, campaign.credit_enabled
    if handle == AUTO:
        handle = creator_handle(meta)
        enabled = enabled and handle is not None
    tag = creator_tag(meta)
    tags: list[str] = []
    for t in campaign.required_hashtags + ([tag] if tag else []):
        t = tag if t == AUTO else t
        if t and t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    return replace(campaign, credit_handle=handle, credit_enabled=enabled, required_hashtags=tags)


def music_dir(campaign: Campaign) -> Path | None:
    """The campaign's music folder; relative paths are relative to the project."""
    if not (campaign.music_allowed and campaign.music_folder):
        return None
    folder = Path(campaign.music_folder).expanduser()
    return folder if folder.is_absolute() else shell.project_home() / folder


def music_tracks(campaign: Campaign) -> list[str]:
    folder = music_dir(campaign)
    if folder is None or not folder.is_dir():
        return []
    return sorted(str(p.resolve()) for p in folder.glob("*.mp3"))
