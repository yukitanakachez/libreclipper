import pytest

from clipper.models import Rect
from clipper.reframe import layout


def test_single_crop_is_nine_sixteenths_of_frame_height_on_16x9():
    crop = layout.single_crop(Rect(0.45, 0.3, 0.1, 0.2), 1920, 1080)
    assert crop.h == pytest.approx(1.0)
    assert crop.w * 1920 == pytest.approx(1080 * 9 / 16, abs=1.0)


def test_single_crop_centres_on_the_face():
    crop = layout.single_crop(Rect(0.60, 0.3, 0.10, 0.2), 1920, 1080)
    assert crop.x + crop.w / 2 == pytest.approx(0.65, abs=0.01)


def test_single_crop_is_clamped_inside_the_frame():
    crop = layout.single_crop(Rect(0.95, 0.3, 0.05, 0.2), 1920, 1080)
    assert crop.x >= 0.0 and crop.x + crop.w <= 1.0 + 1e-9


def test_single_crop_on_a_vertical_source_uses_full_width_not_more():
    # 1080x1920 source is already narrower than 9:16 of its height
    crop = layout.single_crop(Rect(0.4, 0.3, 0.2, 0.2), 1080, 1920)
    assert crop.w == pytest.approx(1.0)
    assert crop.x == 0.0
    assert crop.h <= 1.0 + 1e-9


def test_single_crop_on_a_square_source_stays_in_bounds():
    crop = layout.single_crop(Rect(0.8, 0.3, 0.2, 0.2), 1080, 1080)
    assert crop.x >= 0.0 and crop.x + crop.w <= 1.0 + 1e-9
    assert crop.h == pytest.approx(1.0)


def test_stack_crops_are_nine_eighths_each_and_ordered_left_to_right():
    crops = layout.stack_crops([Rect(0.7, 0.3, 0.1, 0.2), Rect(0.2, 0.3, 0.1, 0.2)], 1920, 1080)
    assert len(crops) == 2
    top_aspect = (crops[0].w * 1920) / (crops[0].h * 1080)
    assert top_aspect == pytest.approx(9 / 8, rel=0.02)
    assert crops[0].x < crops[1].x


def test_fit_rect_is_the_whole_frame():
    assert layout.fit_rect() == Rect(0.0, 0.0, 1.0, 1.0)


@pytest.mark.parametrize("n_faces,confident,expected", [
    (1, True, "single"), (1, False, "single"),
    (2, True, "speaker"), (2, False, "stack"),
    (3, False, "fit"), (0, True, "fit"),
])
def test_choose_layout(n_faces, confident, expected):
    assert layout.choose_layout(n_faces, confident) == expected
