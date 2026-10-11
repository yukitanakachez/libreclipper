from pathlib import Path

import pytest

from clipper.campaigns import CampaignError, load_campaign


def write(tmp_path: Path, name: str, body: str) -> Path:
    root = tmp_path / "campaigns"
    root.mkdir(exist_ok=True)
    (root / f"{name}.yaml").write_text(body)
    return root


VALID = """
name: Example Podcast
credit: { enabled: true, handle: "@examplepod", position: below_headline }
clip_length: { min: 20, max: 60 }
required_hashtags: ["#examplepod"]
vocabulary: ["Jane Doe"]
headline: { enabled: true }
music: { allowed: true, folder: music/example, volume_db: -22 }
captions: { accent_color: "#FFE500", uppercase: false }
"""


def test_loads_valid_campaign(tmp_path):
    root = write(tmp_path, "example", VALID)
    c = load_campaign("example", root)
    assert c.name == "Example Podcast"
    assert c.slug == "example"
    assert (c.min_len, c.max_len) == (20.0, 60.0)
    assert c.credit_handle == "@examplepod"
    assert c.required_hashtags == ["#examplepod"]
    assert c.music_allowed is True


def test_missing_campaign_names_the_file(tmp_path):
    root = write(tmp_path, "example", VALID)
    with pytest.raises(CampaignError, match="nope.yaml"):
        load_campaign("nope", root)


def test_rejects_min_longer_than_max(tmp_path):
    root = write(tmp_path, "bad", VALID.replace("min: 20, max: 60", "min: 90, max: 60"))
    with pytest.raises(CampaignError, match="clip_length"):
        load_campaign("bad", root)


def test_rejects_credit_enabled_without_handle_or_logo(tmp_path):
    body = VALID.replace('handle: "@examplepod", ', "")
    root = write(tmp_path, "bad2", body)
    with pytest.raises(CampaignError, match="credit"):
        load_campaign("bad2", root)


def test_rejects_music_allowed_without_folder(tmp_path):
    body = VALID.replace("allowed: true, folder: music/example, ", "allowed: true, ")
    root = write(tmp_path, "bad3", body)
    with pytest.raises(CampaignError, match="music"):
        load_campaign("bad3", root)


def test_defaults_applied_for_optional_blocks(tmp_path):
    root = write(tmp_path, "min", "name: Minimal\nclip_length: { min: 15, max: 45 }\n")
    c = load_campaign("min", root)
    assert c.credit_enabled is False
    assert c.headline_enabled is True
    assert c.music_allowed is False
    assert c.accent_color == "#FFE500"
    assert c.uppercase is False
    assert c.vocabulary == []


def test_logo_only_credit_is_rejected_until_it_is_supported(tmp_path):
    body = VALID.replace('handle: "@examplepod"', 'logo: assets/logos/pod.png')
    root = write(tmp_path, "logo", body)
    with pytest.raises(CampaignError, match="logo"):
        load_campaign("logo", root)


def test_pacing_defaults(tmp_path):
    root = write(tmp_path, "min", "name: Minimal\nclip_length: { min: 15, max: 45 }\n")
    p = load_campaign("min", root).pacing
    assert (p.cut_pauses, p.max_pause, p.speed) == (True, 0.3, 1.1)


def test_pacing_can_be_turned_off_per_campaign(tmp_path):
    root = write(tmp_path, "raw", "name: Raw\nclip_length: { min: 15, max: 45 }\n"
                                  "pacing: { cut_pauses: false, speed: 1.0 }\n")
    p = load_campaign("raw", root).pacing
    assert (p.cut_pauses, p.speed) == (False, 1.0)


@pytest.mark.parametrize("bad", ["speed: 0.9", "speed: 1.8", "max_pause: 0.05"])
def test_pacing_rejects_out_of_range_values(tmp_path, bad):
    root = write(tmp_path, "bad", f"name: Bad\nclip_length: {{ min: 15, max: 45 }}\n"
                                  f"pacing: {{ {bad} }}\n")
    with pytest.raises(CampaignError, match="pacing"):
        load_campaign("bad", root)


# --- creator tags --------------------------------------------------------------------------

from clipper.campaigns import for_video, list_campaigns  # noqa: E402
from clipper.models import Meta  # noqa: E402

AUTO = """
name: Any creator (auto)
credit: { enabled: true, handle: auto, position: below_headline }
clip_length: { min: 20, max: 60 }
required_hashtags: [auto]
"""


def meta(channel="Just One More Thing", handle="@JustOneMoreThing", kind="youtube"):
    return Meta(job_id="v", source_kind=kind, source="s", title="t", description="", channel=channel,
                duration=10.0, width=1280, height=720, fps=30.0, max_height=1080, channel_handle=handle)


def test_auto_campaign_uses_the_videos_creator(tmp_path):
    c = for_video(load_campaign("auto", write(tmp_path, "auto", AUTO)), meta())
    assert c.credit_enabled and c.credit_handle == "@JustOneMoreThing"
    assert c.required_hashtags == ["#justonemorething"]


def test_auto_handle_falls_back_to_the_channel_name(tmp_path):
    c = for_video(load_campaign("auto", write(tmp_path, "auto", AUTO)), meta(handle=""))
    assert c.credit_handle == "@JustOneMoreThing"


def test_every_campaign_gets_the_creator_tag_once(tmp_path):
    named = write(tmp_path, "jubilee", VALID.replace("@examplepod", "@jubilee").replace('["#examplepod"]', '["#Jubilee"]'))
    c = for_video(load_campaign("jubilee", named), meta(channel="Jubilee", handle="@jubilee"))
    assert c.credit_handle == "@jubilee"                          # a named creator keeps its handle
    assert [t.lower() for t in c.required_hashtags] == ["#jubilee"]  # no duplicate creator tag
    other = write(tmp_path, "pod", VALID.replace('["#examplepod"]', "[]"))
    c = for_video(load_campaign("pod", other), meta(channel="Marcus Jones", handle="@marcusjones"))
    assert c.required_hashtags == ["#marcusjones"]


def test_local_files_get_no_made_up_creator(tmp_path):
    c = for_video(load_campaign("auto", write(tmp_path, "auto", AUTO)), meta(channel="", handle="", kind="local"))
    assert not c.credit_enabled and c.credit_handle is None
    assert c.required_hashtags == []


def test_the_example_template_is_not_listed(tmp_path):
    root = write(tmp_path, "example", VALID)
    write(tmp_path, "auto", AUTO)
    assert [c["slug"] for c in list_campaigns(root)] == ["auto"]


def test_the_projects_auto_campaign_loads():
    from clipper.pipeline import campaign_root
    c = load_campaign("auto", campaign_root())
    assert c.credit_handle == "auto" and c.required_hashtags == ["auto"]
