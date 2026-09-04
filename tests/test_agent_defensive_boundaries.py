from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import matplotlib

matplotlib.use("Agg", force=True)

import numpy as np
import pytest

from hcaptcha_challenger.agent.challenger import RoboticArm
from hcaptcha_challenger.agent.exceptions import ChallengeViewportUnavailable
from hcaptcha_challenger.agent.validation import (
    BoundsValidationError,
    CoordinateBoundsValidator,
    ViewportBounds,
)
from hcaptcha_challenger.helper.create_coordinate_grid import (
    canvas_to_rgb,
    create_coordinate_grid,
)
from hcaptcha_challenger.models import PointCoordinate, SpatialPath


@pytest.fixture
def bounds() -> ViewportBounds:
    return ViewportBounds(x=10, y=20, width=100, height=80)


def make_arm(point_response=None, path_response=None) -> RoboticArm:
    arm = RoboticArm.__new__(RoboticArm)
    arm.page = SimpleNamespace(
        wait_for_timeout=AsyncMock(),
        mouse=SimpleNamespace(click=AsyncMock()),
    )
    arm.config = SimpleNamespace(
        WAIT_FOR_CHALLENGE_VIEW_TO_RENDER_MS=0,
        create_cache_key=Mock(return_value=Path("/tmp/defensive-test")),
    )
    arm.captcha_payload = None
    arm.get_challenge_frame_locator = AsyncMock(return_value=Mock())
    arm.check_crumb_count = AsyncMock(return_value=1)
    arm._capture_spatial_mapping = AsyncMock(
        return_value=(Path("raw.png"), Path("projection.png"))
    )
    arm._match_user_prompt = Mock(return_value="test")
    arm._get_live_viewport_bounds = AsyncMock(
        return_value=ViewportBounds(x=0, y=0, width=100, height=100)
    )
    arm._perform_drag_drop = AsyncMock()

    arm._spatial_point_reasoner = AsyncMock(return_value=point_response)
    arm._spatial_point_reasoner.cache_response = Mock()
    arm._spatial_path_reasoner = AsyncMock(return_value=path_response)
    arm._spatial_path_reasoner.cache_response = Mock()
    return arm


async def test_grid_uses_requested_logical_dimensions() -> None:
    image = np.zeros((1000, 1000, 3), dtype=np.uint8)

    result = create_coordinate_grid(
        image,
        (0.0, 0.0, 1000.0, 1000.0),
        x_line_space_num=3,
        y_line_space_num=3,
    )

    assert result.shape == (1000, 1000, 3)


async def test_physical_buffer_is_downsampled_to_logical_dimensions() -> None:
    rgba = np.zeros((20, 24, 4), dtype=np.uint8)

    class RetinaCanvas:
        def get_width_height(self, physical: bool = False) -> tuple[int, int]:
            return (24, 20) if physical else (12, 10)

        def buffer_rgba(self) -> memoryview:
            return memoryview(rgba)

    result = canvas_to_rgb(RetinaCanvas())

    assert result.shape == (10, 12, 3)


async def test_validator_reports_point_and_path_roles(bounds: ViewportBounds) -> None:
    point_violations = CoordinateBoundsValidator.validate_points(
        [PointCoordinate(x=111, y=30)], bounds
    )
    path_violations = CoordinateBoundsValidator.validate_paths(
        [
            SpatialPath(
                start_point=PointCoordinate(x=50, y=19),
                end_point=PointCoordinate(x=50, y=101),
            )
        ],
        bounds,
    )

    assert [item.role for item in point_violations] == ["point"]
    assert [item.role for item in path_violations] == ["drag-start", "drag-end"]
    assert point_violations[0].bounds == bounds


async def test_out_of_bounds_point_never_reaches_mouse() -> None:
    response = SimpleNamespace(
        points=[PointCoordinate(x=25, y=622)],
        log_message="test",
    )
    arm = make_arm(point_response=response)

    with pytest.raises(BoundsValidationError):
        await arm.challenge_image_label_select(Mock(value="area-select"))

    arm.page.mouse.click.assert_not_awaited()


async def test_out_of_bounds_path_never_reaches_drag() -> None:
    response = SimpleNamespace(
        paths=[
            SpatialPath(
                start_point=PointCoordinate(x=25, y=25),
                end_point=PointCoordinate(x=500, y=25),
            )
        ],
        log_message="test",
    )
    arm = make_arm(path_response=response)

    with pytest.raises(BoundsValidationError):
        await arm.challenge_image_drag_drop(Mock(value="drag-drop"))

    arm._perform_drag_drop.assert_not_awaited()


async def test_missing_frame_raises_typed_exception() -> None:
    main_frame = SimpleNamespace(child_frames=[])
    arm = RoboticArm.__new__(RoboticArm)
    arm.page = SimpleNamespace(main_frame=main_frame, frames=[])

    with pytest.raises(ChallengeViewportUnavailable):
        await arm.get_challenge_frame_locator()


async def test_detached_viewport_bounds_raise_typed_exception() -> None:
    challenge_view = SimpleNamespace(bounding_box=AsyncMock(return_value=None))
    frame = SimpleNamespace(locator=Mock(return_value=challenge_view))
    arm = RoboticArm.__new__(RoboticArm)
    arm.get_challenge_frame_locator = AsyncMock(return_value=frame)

    with pytest.raises(ChallengeViewportUnavailable):
        await arm._get_live_viewport_bounds()
