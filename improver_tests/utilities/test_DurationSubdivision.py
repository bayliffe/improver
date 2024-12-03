# (C) Crown Copyright, Met Office. All rights reserved.
#
# This file is part of 'IMPROVER' and is released under the BSD 3-Clause license.
# See LICENSE in the root of the repository for full licensing details.
"""Unit tests for DurationSubdivision plugin."""

import datetime
from datetime import datetime as dt
from datetime import timedelta
from typing import List, Optional, Tuple

import iris
import numpy as np
import pytest
from iris.cube import Cube, CubeList
from iris.exceptions import CoordinateNotFoundError

from improver.synthetic_data.set_up_test_cubes import set_up_variable_cube
from improver.utilities.temporal_interpolation import DurationSubdivision


def _grid_params(spatial_grid: str, npoints: int) -> Tuple[Tuple[float, float], float]:
    """Set domain corner and grid spacing for lat-lon or equal area
    projections.

    Args:
        spatial_grid:
            "latlon" or "equalarea" to determine the type of projection.
        npoints:
            The number of grid points to use in both x and y.
    Returns:
        A tuple containing a further tuple that includes the grid corner
        coordinates, and a single value specifying the grid spacing.
    """

    domain_corner = None
    grid_spacing = None
    if spatial_grid == "latlon":
        domain_corner = (40, -20)
        grid_spacing = 40 / (npoints - 1)
    elif spatial_grid == "equalarea":
        domain_corner = (-100000, -400000)
        grid_spacing = np.around(1000000.0 / npoints)
    return domain_corner, grid_spacing


def diagnostic_cube(
    data: np.ndarray,
    time: dt = dt(2024, 6, 15, 12),
    frt: dt = dt(2024, 6, 15, 6),
    period: int = 3600,
    spatial_grid: str = "latlon",
    realizations: Optional[List] = None,
) -> Cube:
    """Return a diagnostic cube containing the provided data.

    Args:
        data:
            The data to be contained in the cube.
        time:
            A datetime object that gives the validity time of the cube.
        frt:
            The forecast reference time for the cube.
        period:
            The length of the period represented by the cube in seconds.
        spatial_grid:
            Whether this is a lat-lon or equal areas projection.
        realizations:
            An optional list of realizations identifiers. The length of this
            list will determine how many realizations are created.
    Returns:
        A diagnostic cube for use in testing.
    """
    npoints = data.shape[0]
    domain_corner, grid_spacing = _grid_params(spatial_grid, npoints)

    if realizations:
        data = np.stack([data] * len(realizations))

    time_bounds = [time - timedelta(seconds=period), time]

    return set_up_variable_cube(
        data,
        time=time,
        frt=frt,
        time_bounds=time_bounds,
        spatial_grid=spatial_grid,
        domain_corner=domain_corner,
        x_grid_spacing=grid_spacing,
        y_grid_spacing=grid_spacing,
        realizations=realizations,
    )


def multi_time_cube(
    times: List,
    data: np.ndarray,
    spatial_grid: str = "latlon",
    period: int = 3600,
    realizations: Optional[List] = None,
) -> Cube:
    """Return a multi-time diagnostic cube containing the provided data.

    Args:
        times:
            A list of datetime objects that gives the validity times for
            the cube.
        data:
            The data to be contained in the cube. If the cube is 3-D the
            leading dimension should be the same size as the list of times
            and will be sliced to associate each slice with each time.
        spatial_grid:
            Whether this is a lat-lon or equal areas projection.
        bounds:
            If True return time coordinates with time bounds.
        realizations:
            An optional list of realizations identifiers. The length of this
            list will determine how many realizations are created.
    Returns:
        A diagnostic cube for use in testing.
    """
    cubes = CubeList()
    if data.ndim == 2:
        data = np.stack([data] * len(times))

    frt = sorted(times)[0] - (times[1] - times[0])  # Such that guess bounds are +ve
    for time, data_slice in zip(times, data):
        cubes.append(
            diagnostic_cube(
                data_slice, time=time, frt=frt, period=period, spatial_grid=spatial_grid, realizations=realizations
            )
        )
    return cubes.merge_cube()


def fidelity_cube(data: np.ndarray, period: int, fidelity_period: int):
    """Define a cube with an equally spaced leading time coordinate that
    splits the period defined into shorter periods equal in length to the
    fidelity period. Divide the data amongst these equally."""

    time = dt(2024, 6, 15, 21)
    intervals = period // fidelity_period
    times = [time - (i * timedelta(seconds=fidelity_period)) for i in range(0, intervals)][::-1]
    fidelity_data = data / intervals
    return multi_time_cube(times, fidelity_data.astype(np.float32), period=fidelity_period)


@pytest.fixture
def basic_cube(period: int):
    """Define a cube with default values except for the period."""

    data = np.ones((5, 5), dtype=np.float32)
    return diagnostic_cube(data, period=period)


@pytest.fixture
def data_cube(data: np.ndarray, time: dt, period: int):
    """Define a cube with specific period, data, and validity time."""

    return diagnostic_cube(data.astype(np.float32), time=time, period=period)


@pytest.fixture
def renormalisation_cubes(times: List[dt], data: np.ndarray):
    """Define a cube with an equally spaced leading time coordinate and
    specific data, which is a equal subdivision of the input data which
    is also returned in a single period cube."""
    period = (times[1] - times[0]).total_seconds() * len(times)
    fidelity_data = data / len(times)
    fidelity_period = period / len(times)
    fidelity_cube = multi_time_cube(times, fidelity_data.astype(np.float32), period=fidelity_period)
    input_cube = diagnostic_cube(data.astype(np.float32), time=times[-1], period=period)
    return input_cube, fidelity_cube


@pytest.mark.parametrize(
    "kwargs,mask_value,exception",
    [
        (
            {"target_period": 60, "fidelity": 10, "night_mask": False, "day_mask": False},
            None,  # Expected mask value
            None,  # Expected exception
        ),  # Check plugin initialised correctly without a mask.
        (
            {"target_period": 360, "fidelity": 1, "night_mask": True, "day_mask": False},
            0,  # Expected mask value
            None,  # Expected exception
        ),  # Check plugin initialised correctly with night mask option.
        (
            {"target_period": 10, "fidelity": 2, "night_mask": False, "day_mask": True},
            1,  # Expected mask value
            None,  # Expected exception
        ),  # Check plugin initialised correctly with day mask option.
        (
            {"target_period": 360, "fidelity": 1, "night_mask": True, "day_mask": True},
            None,  # Expected mask value
            "Only one or neither of night_mask and day_mask may be set to True",  # Expected exception
        ),  # Check plugin raises exception if day and night mask options both set True.
        (
            {"target_period": 0, "fidelity": 10, "night_mask": False, "day_mask": False},
            None,  # Expected mask value
            ("Target period and fidelity must be a positive integer numbers of seconds. "
            f"Currently set to target_period: 0, fidelity: 10"),  # Expected exception
        ),  # Check plugin raises exception if target period is 0.
        (
            {"target_period": -100, "fidelity": 10, "night_mask": False, "day_mask": False},
            None,  # Expected mask value
            ("Target period and fidelity must be a positive integer numbers of seconds. "
            f"Currently set to target_period: -100, fidelity: 10"),  # Expected exception
        ),  # Check plugin raises exception if target period is < 0.
        (
            {"target_period": 100, "fidelity": 0, "night_mask": False, "day_mask": False},
            None,  # Expected mask value
            ("Target period and fidelity must be a positive integer numbers of seconds. "
            f"Currently set to target_period: 100, fidelity: 0"),  # Expected exception
        ),  # Check plugin raises exception if fidelity is 0.
        (
            {"target_period": 100, "fidelity": -10, "night_mask": False, "day_mask": False},
            None,  # Expected mask value
            ("Target period and fidelity must be a positive integer numbers of seconds. "
            f"Currently set to target_period: 100, fidelity: -10"),  # Expected exception
        ),  # Check plugin raises exception if fidelity is < 0.
    ],
)
def test__init__(kwargs, mask_value, exception):
    """Test plugin configured as expected and exceptions raised by the
    __init__ method."""

    if exception is not None:
        with pytest.raises(ValueError, match=exception):
            DurationSubdivision(**kwargs)
    else:
        plugin = DurationSubdivision(**kwargs)
        for key in [key for key in kwargs.keys() if "mask" not in key]:
            assert getattr(plugin, key) == kwargs[key]
        assert plugin.mask_value == mask_value



@pytest.mark.parametrize(
    "period", [60, 120, 3600],  # Diagnostic periods in seconds.
)
def test_cube_period(basic_cube, period):
    """Test that this method returns the cube period in seconds."""

    plugin = DurationSubdivision(60, 1)
    result = plugin.cube_period(basic_cube)
    assert result == period



@pytest.mark.parametrize(
    "kwargs,data,time,period",
    [
        (
            {"target_period": 3600, "fidelity": 1800, "night_mask": False, "day_mask": False},
            np.full((10, 10), 10800),  # Data in the input cube.
            dt(2024, 6, 15, 12),  # Validity time
            10800,  # Input period
        ),
        (
            {"target_period": 3600, "fidelity": 1800, "night_mask": True, "day_mask": False},
            np.full((10, 10), 7200),  # Data in the input cube.
            dt(2024, 6, 15, 21),  # Validity time
            3600,  # Input period
        ),
        (
            {"target_period": 3600, "fidelity": 900, "night_mask": False, "day_mask": True},
            np.full((10, 10), 10800),  # Data in the input cube.
            dt(2024, 6, 15, 21),  # Validity time
            10800,  # Input period
        ),
    ],
)
def test_allocate_data(data_cube, kwargs, data, time, period):
    """Test data is allocated to shorter fidelity periods correctly and that
    the metadata associated with these shorter periods is correct."""

    plugin = DurationSubdivision(**kwargs)
    result = plugin.allocate_data(data_cube, period)
    time_dimension_length = period / kwargs["fidelity"]

    # Check expected number of sub-divisions created.
    assert result.shape[0] == time_dimension_length

    # Check sub-divisions have the correct metadata.
    assert result[-1].coord("time").cell(0).point == time
    bounds, = np.unique(np.diff(result.coord("time").bounds, axis=1))
    assert bounds == kwargs["fidelity"]

    collapsed_result = np.around(result.collapsed("time", iris.analysis.SUM).data, decimals=6)
    if not any([kwargs[key] for key in kwargs.keys() if "mask" in key]):
        # Check that summing over the time dimension returns the original data
        # if we've applied no masking.
        np.testing.assert_array_equal(collapsed_result, data)
        # Without masking we can test that all the shorter durations are the
        # expected fraction of the total.
        for cslice in result.slices_over("time"):
            np.testing.assert_array_almost_equal(cslice.data, data / time_dimension_length)
    else:
        # If we've applied masking the reaccumulated data must be less than
        # or equal to the original data.
        assert (collapsed_result <= data).all()


@pytest.mark.parametrize(
    "times,data,masking,expected_factors",
    [
        (
            [dt(2024, 6, 15, 13), dt(2024, 6, 15, 14), dt(2024, 6, 15, 15)],  # List of times for fidelity cubes.
            np.full((3, 3), 10800),  # Data in the input cube.
            [(0, 0, 0), (1, 1, 1)],  # Indices at which to zero points in the fidelity cube (time, y, x)
            [1.5, 1.5]  # Expected factors at points that are zeroed, 1 everywhere else by construction.
        ),  # 1/3 of the fidelity periods at two locations are zeroed yielding a 1.5 factor at those points.
        (
            [dt(2024, 6, 15, 12), dt(2024, 6, 15, 15)],  # List of times for fidelity cubes.
            np.full((3, 3), 3600),  # Data in the input cube.
            [(0, 1, 1)],  # Indices at which to zero points in the fidelity cube (time, y, x)
            [2, 2]  # Expected factors at points that are zeroed, 1 everywhere else by construction.
        ),  # A single point is masked in 1/2 of the fidelity periods yielding a 2 factor there.
        (
            [dt(2024, 6, 15, 12), dt(2024, 6, 15, 15)],  # List of times for fidelity cubes.
            np.full((3, 3), 3600),  # Data in the input cube.
            [(0, 1, 1), (1, 1, 1)],  # Indices at which to zero points in the fidelity cube (time, y, x)
            [0, 0]  # Expected factors at points that are zeroed, 1 everywhere else by construction.
        ),  # All fidelity periods are zeroed, so the factor returned is forced to zero.
    ],
)
def test_renormalisation_factor(renormalisation_cubes, masking, expected_factors):
    """Test the renormalisation_factor method returns the array of renormalisation
    factors."""
    plugin = DurationSubdivision(target_period=10, fidelity=1)  # Settings irrelevant
    cube, fidelity_period_cube = renormalisation_cubes

    # Zero some data points in the fidelity cubes to simulate masking impact.
    # And construct expected factors array.
    expected = np.ones((cube.shape))
    for index, exp in zip(masking, expected_factors):
        fidelity_period_cube.data[index] = 0.
        expected[index[1:]] = exp

    result = plugin.renormalisation_factor(cube, fidelity_period_cube)

    assert (result == expected).all()


@pytest.mark.parametrize(
    "kwargs,data,input_period,expected",
    [
        (
            {"target_period": 3600, "fidelity": 1800},
            np.full((10, 10), 10800),  # Data in the input cube.
            10800,  # Input period
            np.full((3, 10, 10), 3600)  # Expected data in the output cube.
        ),  # Split a 3-hour period into 1-hour periods using a fidelity of 30 minutes.
        (
            {"target_period": 3600, "fidelity": 900},
            np.full((3, 3), 3600),  # Data in the input cube.
            10800,  # Input period
            np.full((3, 3, 3), 1200)  # Expected data in the output cube.
        ),  # Split a 3-hour period into 1-hour periods using a fidelity of 15 minutes.
        (
            {"target_period": 5400, "fidelity": 1800},
            np.full((3, 3), 10800),  # Data in the input cube.
            21600,  # Input period
            np.full((4, 3, 3), 2700)  # Expected data in the output cube.
        ),  # Split a 6-hour period into 1.5-hour periods using a fidelity of 30 minutes.
    ],
)
def test_construct_target_periods(kwargs, data, input_period, expected):
    """Test the construct_target_periods method returns the expected period
    data."""

    plugin = DurationSubdivision(**kwargs)
    input_cube = fidelity_cube(data, input_period, kwargs["fidelity"])
    result = plugin.construct_target_periods(input_cube)

    # Check a single cube is returned
    assert isinstance(result, Cube)

    # Check shorter period cubes have the right length.
    bounds, = np.unique(np.diff(result.coord("time").bounds, axis=1))
    assert bounds == kwargs["target_period"]

    # Check subdivided data is as expected. Also checks that shape is as
    # expected.
    np.testing.assert_array_almost_equal(result.data, expected)



@pytest.mark.parametrize(
    "kwargs,data,time,period,expected,exception",
    [
        (
            {"target_period": 1100, "fidelity": 550, "night_mask": False, "day_mask": False},
            np.full((3, 3), 10800),  # Data in the input cube.
            dt(2024, 6, 15, 12),  # Validity time
            10800,  # Input period
            None,  # Expected data in the output cube (not used here).
            "The target period must be a factor of the original period",  # Expected exception
        ),  # Raise a ValueError as the target period is not a factor of the input period.
        (
            {"target_period": 7200, "fidelity": 1800, "night_mask": False, "day_mask": False},
            np.full((3, 3), 3600),  # Data in the input cube.
            dt(2024, 6, 15, 12),  # Validity time
            3600,  # Input period
            None,  # Expected data in the output cube (not used here).
            ("The target period must be a factor of the original period "
             "of the input cube and the target period must >= the input "
             "period. Input period: 3600, target period: 7200"),  # Expected exception
        ),  # Raise a ValueError as the target period is longer than the input period.
        (
            {"target_period": 3600, "fidelity": 1800, "night_mask": False, "day_mask": False},
            np.full((3, 3), 3600),  # Data in the input cube.
            dt(2024, 6, 15, 12),  # Validity time
            3600,  # Input period
            None,  # Expected data in the output cube (not used here).
            None,  # Expected exception
        ),  # Return the input cube completely unchanged as the target period matches the input period.
        (
            {"target_period": 3600, "fidelity": 1800, "night_mask": False, "day_mask": False},
            np.full((3, 3), 10800),  # Data in the input cube.
            dt(2024, 6, 15, 21),  # Validity time
            7200,  # Input period
            np.full((2, 3, 3), 3600),  # Expected data in the output cube.
            None,  # Expected exception
        ),  # Demonstate clipping of input data as input data exceeds the period.
        (
            {"target_period": 3600, "fidelity": 1800, "night_mask": True, "day_mask": False},
            np.full((3, 3), 7200),  # Data in the input cube.
            dt(2024, 6, 15, 21),  # Validity time
            7200,  # Input period
            np.array(
                [[
                    [3600., 1800.,    0.],
                    [3600., 3600., 3600.],
                    [3600., 3600., 3600.]],
                   [[3600.,    0.,    0.],
                    [3600., 3600.,    0.],
                    [3600., 3600., 3600.]
                ]], dtype=np.float32),  # Expected data in the output cube.
            None,  # Expected exception
        ),  # Night masking applies time dependent masking, meaning we get different data
            # in each of the returned periods. The total in any period does not exceed the
            # length of that period; this means that the total across periods is lower than
            # in the input.
        (
            {"target_period": 3600, "fidelity": 1800, "night_mask": False, "day_mask": True},
            np.full((3, 3), 7200),  # Data in the input cube.
            dt(2024, 6, 15, 21),  # Validity time
            7200,  # Input period
            np.array(
                [[
                    [   0., 1800., 3600.],
                    [   0.,    0.,    0.],
                    [   0.,    0.,    0.]],
                   [[0., 3600., 3600.],
                    [   0.,    0., 3600.],
                    [   0.,    0.,    0.]
                ]], dtype=np.float32),  # Expected data in the output cube.
            None,  # Expected exception
        ),  # Day masking applies time dependent masking. This is the inverse of the test
            # above, and we get a suitably inverted result.
        (
            {"target_period": 3600, "fidelity": 360, "night_mask": True, "day_mask": False},
            np.full((3, 3), 7200),  # Data in the input cube.
            dt(2024, 6, 15, 21),  # Validity time
            7200,  # Input period
            np.array(
                [[
                    [3600., 1440.,    0.],
                    [3600., 3600., 3240.],
                    [3600., 3600., 3600.]],
                   [[2880.,    0.,    0.],
                    [3600., 3600.,    0.],
                    [3600., 3600., 3600.]
                ]], dtype=np.float32),  # Expected data in the output cube.
            None,  # Expected exception
        ),  # Repeat the night masking test above but with higher fidelity, meaning that
            # the subdivided data is split into shorter periods and the night mask
            # applied more accurately. As a result we get fractions returned which are
            # multiples of this fidelity period.
    ],
)
def test_process(kwargs, data_cube, period, expected, exception):
    """Test the process method returns the expected data or raises the
    expected exceptions."""

    plugin = DurationSubdivision(**kwargs)
    if exception is not None:
        with pytest.raises(ValueError, match=exception):
            plugin.process(data_cube)
    else:
        result = plugin.process(data_cube)

        if kwargs["target_period"] == period:
            assert result is data_cube
        else:
            # Check data returned is as expected.
            np.testing.assert_array_almost_equal(result.data, expected)
            # Check periods returned are correct.
            bounds, = np.unique(np.diff(result.coord("time").bounds, axis=1))
            assert bounds == kwargs["target_period"]
