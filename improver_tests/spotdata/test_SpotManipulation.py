# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown copyright. The Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Unit tests for SpotManipulation class"""

import warnings

import iris
import numpy as np
import pytest
from iris.coords import AuxCoord, DimCoord
from numpy.testing import assert_array_equal

from improver.metadata.utilities import create_coordinate_hash
from improver.spotdata.spot_manipulation import SpotManipulation
from improver.synthetic_data.set_up_test_cubes import (
    add_coordinate,
    set_up_percentile_cube,
    set_up_probability_cube,
    set_up_spot_variable_cube,
    set_up_variable_cube,
)

ATTRIBUTES = {"mosg__grid_domain": "global", "mosg__grid_type": "standard"}


@pytest.fixture
def gridded_variable(grid_data):
    """Create a gridded variable cube from which to extract spot foreasts."""
    height_crd = DimCoord(
        np.array([1.5], dtype=np.float32), standard_name="height", units="m"
    )
    return set_up_variable_cube(
        grid_data, include_scalar_coords=[height_crd], attributes=ATTRIBUTES,
    )


@pytest.fixture
def gridded_lapse_rate(lapse_rates):
    """Create a gridded lapse_rate cube."""
    height_crd = DimCoord(
        np.array([1.5], dtype=np.float32), standard_name="height", units="m"
    )
    return set_up_variable_cube(
        lapse_rates,
        name="air_temperature_lapse_rate",
        units="K m-1",
        include_scalar_coords=[height_crd],
        attributes=ATTRIBUTES,
    )


@pytest.fixture
def gridded_percentiles(grid_data):
    """Create a gridded percentile cube from which to extract spot foreasts."""
    n_percentiles = grid_data.shape[0]
    percentiles = np.linspace(20, 80, n_percentiles)
    return set_up_percentile_cube(grid_data, percentiles, attributes=ATTRIBUTES,)


@pytest.fixture
def gridded_probabilities(grid_data):
    """Create a gridded probability cube from which to extract spot foreasts."""
    n_thresholds = grid_data.shape[0]
    thresholds = np.linspace(273, 283, n_thresholds)
    return set_up_probability_cube(grid_data, thresholds, attributes=ATTRIBUTES,)


@pytest.fixture
def neighbour_cube(neighbour_data):
    """Takes in a 3D array. The leading dimension corresponds to each type
    of neighbour selection. The second dimension corresponds to the different
    attributes, these being x_index, y_index, and vertical_displacement. The
    final dimension corresponds to the different sites."""

    n_methods = neighbour_data.shape[0]
    # Generate a cube with the right number of sites to which we can add
    # further coordinates.
    data_1d = neighbour_data[0, 0]

    cube = set_up_spot_variable_cube(data_1d)
    methods = [
        "nearest",
        "nearest_land",
        "nearest_minimum_dz",
        "nearest_land_minimum_dz",
    ]
    method_name = AuxCoord(
        methods[0:n_methods], long_name="neighbour_selection_method_name"
    )
    grid_attributes_key = AuxCoord(
        ["x_index", "y_index", "vertical_displacement"], long_name="grid_attributes_key"
    )
    cube = add_coordinate(cube, [0, 1, 2], "grid_attributes", dtype="int32")
    cube = add_coordinate(
        cube, np.arange(n_methods), "neighbour_selection_method", dtype="int32"
    )
    if n_methods == 1:
        cube = iris.util.new_axis(cube, "neighbour_selection_method")
    cube.add_aux_coord(method_name, 0)
    cube.add_aux_coord(grid_attributes_key, 1)
    cube.data = neighbour_data
    return cube


def add_grid_hash(target, source):
    """Add a grid hash attribute to the target cube that has been generated
    using the coordinates on the source cube. This allows a neighbour cube
    to be used with a gridded cube by ensuring the hash test passes in the
    spot extraction plugin."""

    grid_hash = create_coordinate_hash(source)
    target.attributes["model_grid_hash"] = grid_hash


@pytest.mark.parametrize(
    "grid_data,neighbour_data,expected",
    [
        (
            np.arange(273, 282).reshape(3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            np.array([274, 275]),
        ),
        (
            np.arange(273, 282).reshape(3, 3),
            np.array([[[1, 2], [2, 2], [5, 10]]]),
            np.array([280, 281]),
        ),
    ],
)
def test_basic_extraction(gridded_variable, neighbour_cube, expected):
    """Test that basic spot extraction via the SpotManipulation plugin returns
    the expected values."""

    add_grid_hash(neighbour_cube, gridded_variable)
    result = SpotManipulation()([gridded_variable, neighbour_cube])
    assert_array_equal(result.data, expected)
    assert result.attributes.get("model_grid_hash", None) is None


@pytest.mark.parametrize(
    "grid_data,neighbour_data,kwargs,expected",
    [
        (
            np.arange(273, 291).reshape(2, 3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"extract_percentiles": [20, 80]},
            np.array([[274, 275], [283, 284]]),
        ),
        (
            np.arange(273, 291).reshape(2, 3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"extract_percentiles": [50]},
            np.array([278.5, 279.5]),
        ),
    ],
)
def test_percentile_extraction(gridded_percentiles, neighbour_cube, kwargs, expected):
    """Test that percentiles can be extracted, either extracting existing
    percentiles on a percentile input cube, or resampling existing percentiles
    if needed."""

    add_grid_hash(neighbour_cube, gridded_percentiles)
    result = SpotManipulation(**kwargs)([gridded_percentiles, neighbour_cube])
    assert_array_equal(result.data, expected)


@pytest.mark.parametrize(
    "grid_data,neighbour_data,kwargs,expected",
    [
        (
            np.stack(
                [
                    np.full((3, 3), 1.0, dtype=np.float32),
                    np.full((3, 3), 0.75, dtype=np.float32),
                    np.full((3, 3), 0.5, dtype=np.float32),
                    np.full((3, 3), 0.25, dtype=np.float32),
                    np.full((3, 3), 0.0, dtype=np.float32),
                ]
            ),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"extract_percentiles": [50]},
            np.array([278, 278]),
        ),
        (
            np.stack(
                [
                    np.full((3, 3), 1.0, dtype=np.float32),
                    np.full((3, 3), 0.75, dtype=np.float32),
                    np.full((3, 3), 0.5, dtype=np.float32),
                    np.full((3, 3), 0.25, dtype=np.float32),
                    np.full((3, 3), 0.0, dtype=np.float32),
                ]
            ),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"extract_percentiles": [40, 60]},
            np.array([[277, 277], [279, 279]]),
        ),
    ],
)
def test_percentiles_from_probabilities(
    gridded_probabilities, neighbour_cube, kwargs, expected
):
    """Test that percentiles can be extracted from a probability cube."""

    add_grid_hash(neighbour_cube, gridded_probabilities)
    result = SpotManipulation(**kwargs)([gridded_probabilities, neighbour_cube])
    assert_array_equal(result.data, expected)


@pytest.mark.parametrize(
    "grid_data,neighbour_data,kwargs,expected",
    [
        (
            np.arange(273, 291).reshape(2, 3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {},
            np.array([[274, 275], [283, 284]]),
        ),
        (
            np.arange(273, 291).reshape(2, 3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"suppress_warnings": True},
            np.array([[274, 275], [283, 284]]),
        ),
    ],
)
def test_unknown_prob_type_warning(
    gridded_percentiles, neighbour_cube, kwargs, expected
):
    """Test a warning is raised if percentiles are requested from a cube from
    which they cannot be extracted and that all data is returned in spot
    format. In this case that is the 20th and 80th pecentiles are both
    returned rather than the requested 50th percentile. If the
    suppress_warnings option is set then test that no warning is raised."""

    add_grid_hash(neighbour_cube, gridded_percentiles)
    gridded_percentiles.coord("percentile").rename("kittens")

    if "suppress_warnings" in kwargs.keys():
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = SpotManipulation(extract_percentiles=[50], **kwargs)(
                [gridded_percentiles, neighbour_cube]
            )
    else:
        with pytest.warns(
            UserWarning, match="Diagnostic cube is not a known probabilistic type"
        ):
            result = SpotManipulation(extract_percentiles=[50], **kwargs)(
                [gridded_percentiles, neighbour_cube]
            )

    assert_array_equal(result.data, expected)


@pytest.mark.parametrize(
    "grid_data,lapse_rates,neighbour_data,kwargs,expected",
    [
        (
            np.arange(273, 282).reshape(3, 3),
            np.full((3, 3), 0.1, dtype=np.float32),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"apply_lapse_rate_correction": True},
            np.array([274.5, 276]),
        ),
        (
            np.arange(273, 282).reshape(3, 3),
            np.full((3, 3), 0, dtype=np.float32),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"apply_lapse_rate_correction": True, "fixed_lapse_rate": 0.2},
            np.array([275, 277]),
        ),
    ],
)
def test_lapse_rate_correction(
    gridded_variable, gridded_lapse_rate, neighbour_cube, kwargs, expected
):
    """Test the application of lapse rates using a lapse rate cube and a fixed
    lapse rate value."""

    add_grid_hash(neighbour_cube, gridded_variable)
    inputs = [gridded_variable, gridded_lapse_rate, neighbour_cube]
    if "fixed_lapse_rate" in kwargs.keys():
        inputs = [gridded_variable, neighbour_cube]

    result = SpotManipulation(**kwargs)(inputs)
    assert_array_equal(result.data, expected)


@pytest.mark.parametrize(
    "grid_data,neighbour_data,kwargs,expected",
    [
        (
            np.arange(273, 282).reshape(3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"apply_lapse_rate_correction": True},
            np.array([274, 275]),
        ),
        (
            np.arange(273, 282).reshape(3, 3),
            np.array([[[1, 2], [0, 0], [5, 10]]]),
            {"apply_lapse_rate_correction": True, "suppress_warnings": True},
            np.array([274, 275]),
        ),
    ],
)
def test_missing_lapse_rate_warning(gridded_variable, neighbour_cube, kwargs, expected):
    """Test a warning is raised if no lapse rate is specified whilst the
    apply_lapse_rate_correction kwarg is set to True. If the
    suppress_warnings option is set then test that no warning is raised."""

    add_grid_hash(neighbour_cube, gridded_variable)

    if "suppress_warnings" in kwargs.keys():
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = SpotManipulation(**kwargs)([gridded_variable, neighbour_cube])
    else:
        with pytest.warns(
            UserWarning, match="A lapse rate cube or fixed lapse rate was not provided"
        ):
            result = SpotManipulation(**kwargs)([gridded_variable, neighbour_cube])

    assert_array_equal(result.data, expected)
