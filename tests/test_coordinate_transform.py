import pytest

from core.coordinate_transform import MapCalibration


def test_world_pixel_round_trip():
    calibration = MapCalibration(
        world_min_x=-100,
        world_max_x=100,
        world_min_y=-200,
        world_max_y=200,
        pixel_min_x=0,
        pixel_max_x=1000,
        pixel_min_y=0,
        pixel_max_y=2000,
        invert_y=True,
    )
    pixel = calibration.world_to_pixel(25, -50)
    assert pixel == (625.0, 1250.0)
    assert calibration.pixel_to_world(*pixel) == (25.0, -50.0)


def test_non_inverted_y():
    calibration = MapCalibration(0, 100, 0, 100, 0, 500, 0, 500, False)
    assert calibration.world_to_pixel(20, 40) == (100.0, 200.0)


def test_swapped_axes_round_trip():
    calibration = MapCalibration(
        world_min_x=-607000,
        world_max_x=509000,
        world_min_y=-505000,
        world_max_y=607000,
        pixel_min_x=0,
        pixel_max_x=7800,
        pixel_min_y=0,
        pixel_max_y=7817,
        invert_y=False,
        invert_x=False,
        swap_axes=True,
    )
    pixel = calibration.world_to_pixel(0, 0)
    assert pixel == pytest.approx((3542.2661870503597, 4251.719534050179))
    world = calibration.pixel_to_world(*pixel)
    assert abs(world[0]) < 1e-9
    assert abs(world[1]) < 1e-9
