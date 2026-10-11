
import pytest

from clipper import jobs
from clipper.web import review


def test_load_job_reads_everything(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    assert [c.n for c in data.candidates] == [1, 2]
    assert data.plans[1].analyzed_end == pytest.approx(14.9)
    assert data.campaign.name == "Pod"
    assert data.status["state"] == "ready_for_review"


def test_load_job_404s_on_missing_or_unsafe_ids(web_cfg):
    for bad in ("nope", "../x", ""):
        with pytest.raises(review.ReviewError) as exc:
            review.load_job(bad, web_cfg)
        assert exc.value.status == 404


def test_view_includes_words_in_the_analyzed_range_with_fixes(web_cfg, web_job):
    paths = web_job()
    jobs.write_json(paths.word_fixes, {"12": "twelve"})
    data = review.load_job("vid1", web_cfg)
    view = review.candidate_view(data.candidates[0], data)
    assert view["bounds"] == {"min_start": 0.0, "max_end": pytest.approx(14.9)}
    texts = [w["text"] for w in view["words"]]
    assert "twelve" in texts and texts[0] == "w0"
    assert all(w["end"] <= 14.9 + 1e-6 for w in view["words"])


def test_view_reports_finished_length_and_limits(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    view = review.candidate_view(data.candidates[0], data)
    # 4.9 s of speech with 0.1 s gaps, no long pauses, played at 1.1x
    assert view["finished_length"] == pytest.approx(4.9 / 1.1, abs=0.05)
    assert view["in_limits"] is True
    assert view["ends_on_sentence"] is True           # ends on "w19."


def test_view_flags_a_non_sentence_ending(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    c = data.candidates[0]
    c.end = 8.9                                          # ends on "w17"
    assert review.candidate_view(c, data)["ends_on_sentence"] is False


def test_patch_trim_is_stored_exactly_and_marks_edited(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    cand, layout_changed = review.apply_patch(data, 1, {"start": 4.43, "end": 12.37})
    assert (cand.start, cand.end) == (4.43, 12.37)
    assert cand.edited is True and layout_changed is False
    saved = review.load_job("vid1", web_cfg).candidates[0]
    assert (saved.start, saved.end, saved.edited) == (4.43, 12.37, True)


@pytest.mark.parametrize("patch,fragment", [
    ({"start": -0.5}, "analyzed range"),
    ({"end": 15.5}, "analyzed range"),
    ({"start": 9.0, "end": 9.5}, "at least"),
    ({"start": 9.0, "end": 8.0}, "at least"),
    ({"start": float("nan")}, "number"),
    ({"start": "5"}, "number"),
    ({"layout": "zoom"}, "layout"),
    ({"bogus": 1}, "bogus"),
    ({"headline": "x" * 201}, "headline"),
    ({"approved": "yes"}, "approved"),
])
def test_patch_rejects_bad_input_with_422(web_cfg, web_job, patch, fragment):
    web_job()
    data = review.load_job("vid1", web_cfg)
    with pytest.raises(review.ReviewError) as exc:
        review.apply_patch(data, 1, patch)
    assert exc.value.status == 422
    assert fragment in str(exc.value)


def test_patch_rejects_edits_unless_ready_or_done(web_cfg, web_job):
    web_job(state="reframing")
    data = review.load_job("vid1", web_cfg)
    with pytest.raises(review.ReviewError) as exc:
        review.apply_patch(data, 1, {"headline": "New"})
    assert exc.value.status == 409


def test_approving_alone_does_not_count_as_an_edit(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    cand, _ = review.apply_patch(data, 1, {"approved": True})
    assert cand.approved is True and cand.edited is False


def test_layout_change_is_reported(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    cand, layout_changed = review.apply_patch(data, 2, {"layout": "fit"})
    assert cand.layout == "fit" and layout_changed is True


def test_music_needs_a_campaign_that_allows_it(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    with pytest.raises(review.ReviewError, match="music"):
        review.apply_patch(data, 1, {"music_on": True})


def test_music_track_must_be_inside_the_campaign_folder(web_cfg, web_job, web_home):
    web_job(job_id="mus", campaign="musical")
    data = review.load_job("mus", web_cfg)
    good = str(web_home / "music" / "pod" / "bed.mp3")
    cand, _ = review.apply_patch(data, 1, {"music_on": True, "music_track": good})
    assert cand.music_track == good
    data = review.load_job("mus", web_cfg)
    with pytest.raises(review.ReviewError, match="music"):
        review.apply_patch(data, 1, {"music_track": "/etc/passwd"})


def test_word_fixes_merge_and_validate(web_cfg, web_job):
    web_job()
    data = review.load_job("vid1", web_cfg)
    assert review.save_word_fixes(data, {"3": "three"}) == {"3": "three"}
    data = review.load_job("vid1", web_cfg)
    assert review.save_word_fixes(data, {"4": "four."}) == {"3": "three", "4": "four."}
    for bad in ({"999": "x"}, {"a": "x"}, {"3": ""}, {"3": "two\nlines"}):
        with pytest.raises(review.ReviewError):
            review.save_word_fixes(review.load_job("vid1", web_cfg), bad)


def test_has_edits(web_cfg, web_job):
    web_job()
    assert review.has_edits(review.load_job("vid1", web_cfg)) is False
    review.apply_patch(review.load_job("vid1", web_cfg), 1, {"approved": True})
    assert review.has_edits(review.load_job("vid1", web_cfg)) is True




def test_job_summary_for_a_job_without_meta(web_cfg):
    paths = jobs.paths_for("fresh", web_cfg)
    jobs.set_status(paths, "queued")
    summary = review.job_summary(paths, busy=True)
    assert summary["id"] == "fresh" and summary["state"] == "queued"
    assert summary["progress"] == 0.0
    assert summary["title"] is None and summary["busy"] is True
    assert summary["candidates"] == 0 and summary["clips"] == 0


def test_list_campaigns_reports_invalid_files(web_home):
    from clipper.campaigns import list_campaigns
    (web_home / "campaigns" / "broken.yaml").write_text("name: B\nclip_length: { min: 9, max: 1 }\n")
    listing = {c["slug"]: c for c in list_campaigns(web_home / "campaigns")}
    assert listing["pod"]["valid"] is True and listing["pod"]["name"] == "Pod"
    assert listing["broken"]["valid"] is False and "clip_length" in listing["broken"]["error"]


def test_a_failed_render_leaves_the_job_editable_so_the_bad_clip_can_be_fixed(web_cfg, web_job):
    paths = web_job()
    jobs.set_status(paths, "failed", error="music track missing", failed_step="render")
    cand, _ = review.apply_patch(review.load_job("vid1", web_cfg), 1, {"approved": False})
    assert cand.approved is False
    jobs.set_status(paths, "failed", error="Claude overloaded", failed_step="pick")
    with pytest.raises(review.ReviewError) as exc:
        review.apply_patch(review.load_job("vid1", web_cfg), 1, {"approved": True})
    assert exc.value.status == 409


def test_a_new_pick_clears_old_framing_and_render_errors(web_cfg, web_job):
    paths = web_job()
    paths.work.mkdir(parents=True, exist_ok=True)
    review.render_error_path(paths, 1).write_text("old")
    review.reframe_error_path(paths, 2).write_text("old")
    review.clear_errors(paths)
    assert list(paths.work.iterdir()) == []


def _clip(paths, name):
    paths.out.mkdir(parents=True, exist_ok=True)
    (paths.out / name).write_bytes(b"v")
    return paths.out / name


def test_a_candidate_knows_its_rendered_clip(web_cfg, web_job):
    paths = web_job()
    data = review.load_job("vid1", web_cfg)
    one, two = data.candidates[0], data.candidates[1]
    assert review.candidate_view(one, data)["clip"] is None
    clip = _clip(paths, "01-one.mp4")
    assert review.candidate_view(one, data)["clip"] == "01-one.mp4"      # by number, when unlogged
    assert review.candidate_view(two, data)["clip"] is None
    review.record_render(paths, clip, one)
    assert review.candidate_view(one, data)["clip"] == "01-one.mp4"


def test_a_clip_from_an_earlier_pick_is_not_the_new_candidates(web_cfg, web_job):
    import dataclasses
    paths = web_job()
    data = review.load_job("vid1", web_cfg)
    one = data.candidates[0]
    review.record_render(paths, _clip(paths, "01-one.mp4"), one)
    repicked = dataclasses.replace(one, orig_start=one.orig_start + 60, start=one.start + 60,
                                   end=one.end + 60, orig_end=one.orig_end + 60)
    assert review.clip_for(repicked, paths, review.clip_log(paths)) is None


def test_posted_marks_are_kept_per_clip_and_a_new_render_starts_unposted(web_cfg, web_job):
    paths = web_job()
    one = review.load_job("vid1", web_cfg).candidates[0]
    clip = _clip(paths, "01-one.mp4")
    review.record_render(paths, clip, one)
    assert review.set_posted(paths, "01-one.mp4", True, "2026-10-11T10:00:00+00:00")["posted_at"]
    assert review.clip_view(paths, clip, review.clip_log(paths))["posted_at"] == "2026-10-11T10:00:00+00:00"
    assert review.job_summary(paths, busy=False)["posted"] == 1
    review.set_posted(paths, "01-one.mp4", False, "x")
    assert review.job_summary(paths, busy=False)["posted"] == 0
    review.set_posted(paths, "01-one.mp4", True, "2026-10-11T10:00:00+00:00")
    review.record_render(paths, clip, one)                                # rendered again
    assert review.clip_log(paths)["01-one.mp4"]["posted_at"] is None
