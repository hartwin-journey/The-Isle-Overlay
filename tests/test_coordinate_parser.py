import pytest

from core.coordinate_parser import CoordinateParseError, parse_coordinates


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("88,879.526, 288,696.110, 21,112.882", (88879.526, 288696.110, 21112.882)),
        ("-88,879.526, -288,696.110, -21,112.882", (-88879.526, -288696.110, -21112.882)),
        ("123.5, -456.25, 7", (123.5, -456.25, 7.0)),
        ("X=-88,879.526, Y=288,696.110, Z=21,112.882", (-88879.526, 288696.110, 21112.882)),
        ("X: 10; Y: 20; Z: 30", (10.0, 20.0, 30.0)),
    ],
)
def test_valid_coordinates(text, expected):
    parsed = parse_coordinates(text)
    assert (parsed.x, parsed.y, parsed.z) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ordinary clipboard text",
        "coordinates: 1, 2, 3 and more text",
        "1, 2",
        "1, 2, 3, 4",
        "1\n2\n3",
        "12,34.5, 2, 3",
        "1e3, 2, 3",
    ],
)
def test_invalid_coordinates(text):
    with pytest.raises(CoordinateParseError):
        parse_coordinates(text)

