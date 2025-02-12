# (C) Crown Copyright, Met Office. All rights reserved.
#
# This file is part of 'IMPROVER' and is released under the BSD 3-Clause license.
# See LICENSE in the root of the repository for full licensing details.
"""Unit tests for ModalFromGroupings class."""

from calendar import timegm
from datetime import datetime as dt
from datetime import timedelta

import numpy as np
import pytest

from improver.categorical.modal_code import ModalFromGroupings
from improver_tests.categorical.decision_tree import wxcode_decision_tree
from improver_tests.categorical.modal_code.test_ModalCategory import (  # noqa: F401
    wxcode_series_fixture,
)

MODEL_ID_ATTR = "mosg__model_configuration"
RECORD_RUN_ATTR = "mosg__model_run"
TARGET_TIME = dt(2020, 6, 15, 18)
BROAD_CATEGORIES = {
    "wet": [10, 11, 12, 14, 15, 17, 18, 20, 21, 23, 24, 26, 27, 29, 30],
    "dry": [1, 3, 4, 5, 6, 7, 8],
}
# Priority ordered categories (keys) in case of ties
WET_CATEGORIES = {
    "extreme_convection": [30, 29, 21, 20],
    "frozen": [27, 26, 24, 23, 18, 17],
    "liquid": [15, 14, 12, 11, 10],
}
INTENSITY_CATEGORIES = {
    "rain_shower": [14, 10],
    "rain": [15, 12],
    "snow_shower": [26, 23],
    "snow": [27, 24],
    "thunder": [30, 29],
    "cloud": [7, 8],
    "sun": [3, 1],
    "vis": [5, 6],
}


@pytest.mark.parametrize("record_run_attr", [False])
@pytest.mark.parametrize("model_id_attr", [True])
@pytest.mark.parametrize("interval", [1])
@pytest.mark.parametrize("offset_reference_times", [True])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize(
    "data, expected",
    (
        # Sunny day (1), one rain code (15) that is in the minority, expect sun
        # code (1).
        ([1, 1, 1, 15], 1),
        # Short period with an equal split. The most significant weather
        # (hail, 21) should be returned.
        ([1, 21], 21),
        # A single time is provided in which a sleet shower is forecast (16).
        # We expect the cube to be returned with the night code changed to a
        # day code (17).
        ([16], 17),
        # Equal split in day codes, but a night code corresponding to one
        # of the day types means a valid mode can be calculated. We expect the
        # day code (10) to be returned.
        ([1, 1, 10, 10, 9], 10),
        # No clear representative code. Groups by wet and dry codes and selects
        # the most significant dry code (8).
        ([1, 3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 15], 8),
        # No clear representative code. More dry symbols are present, so the most
        # significant dry code is selected (8).
        ([1, 3, 4, 5, 6, 7, 8, 16, 11, 12, 14, 15], 8),
        # No clear representative code. More dry symbols are present, so the most
        # significant dry code is selected (8).
        ([5, 5, 5, 5, 6, 6, 6, 6, 8, 8, 8, 8, 7, 7, 7, 7], 8),
        # An extreme edge case in which all the codes across time for a site
        # are different. More dry symbols are present, so we get a dry code.
        # The wet symbols are translated to their cloud equivalents, all
        # partly cloud in this case, so this symbol ends up dominating (3).
        ([1, 3, 4, 5, 7, 8, 10, 17, 20, 23], 3),
        # Equal numbers of dry and wet symbols leads to a wet symbol being chosen.
        # Code 23 and 17 are both frozen precipitation, so are grouped together,
        # and the most significant of these is chosen based on the order of the codes
        # within the frozen precipitation categorisation.
        ([1, 3, 4, 5, 10, 17, 20, 23], 23),
        # All dry symbols. The most significant dry symbol is chosen, asssuming that
        # higher index weather codes are more significant.
        ([1, 3, 4, 5], 5),
        # All wet codes. Two frozen precipitation and two "extreme". Codes from the
        # extreme category chosen in preference.
        ([29, 29, 26, 26], 29),
        # All wet codes. Two frozen precipitation and two liquid precipitation.
        # Frozen precipitation chosen in preference.
        ([10, 10, 26, 26], 26),
        # More dry codes than wet codes. Most common code (2, partly cloudy night)
        # should be converted to a day symbol.
        ([2, 2, 2, 0, 0, 2, 10, 10, 11, 12, 13], 3),
        # More dry codes than wet codes. Wet code cloud equivalents are partly
        # cloudy, so that comes to dominate in its day form (3).
        # should be converted to a day symbol.
        ([0, 0, 0, 2, 2, 0, 10, 10, 11, 12, 13], 3),
        # Two locations with different modal dry codes.
        ([[3, 3, 3, 4, 5, 5], [3, 3, 4, 4, 4, 5]], [3, 4]),
        # Four locations with different modal dry codes.
        (
            [
                [3, 3, 3, 4, 5, 5],
                [3, 3, 4, 4, 4, 5],
                [1, 1, 3, 3, 5, 6],
                [6, 6, 6, 7, 7, 7],
            ],
            [3, 4, 3, 7],
        ),
        # Tied dry weather codes. The day version of the highest index weather code
        # should be selected i.e. a partly cloudy night code (2) becomes a partly
        # cloudy day code (3).
        ([0, 0, 0, 2, 2, 2, 7, 7], 3),
        # A dry dominated set of codes, but one shower code is transformed to its
        # daytime partly cloudy equivalent and considered in determining the dominant
        # dry code, which as a result ends up as partly cloud (3).
        ([1, 1, 1, 2, 2, 9], 3),
        # Dry dominated, 3 sunshine codes, 1 overcast, and 2 light rain. The
        # overcast cloud cover in the light rain codes is included in determining the
        # dominant dry code, leading to an overcast symbol overall (8).
        ([1, 1, 1, 8, 12, 12], 8),
        # Dry dominated and after cloud equivalence (drizzle becomes overcast (8)).
        # All codes are unique dry codes, so the most significant is selected (8).
        ([1, 3, 4, 5, 7, 11], 8),
    ),
)
def test_expected_values(wxcode_series, expected):
    """Test that the expected period representative symbol is returned."""
    _, _, _, _, wxcode_cubes = wxcode_series
    result = ModalFromGroupings(
        wxcode_decision_tree(), BROAD_CATEGORIES, WET_CATEGORIES
    )(wxcode_cubes)
    expected = [expected] if not isinstance(expected, list) else expected
    for index in range(len(expected)):
        assert result.data.flatten()[index] == expected[index]


@pytest.mark.parametrize("record_run_attr", [False])
@pytest.mark.parametrize("model_id_attr", [False, True])
@pytest.mark.parametrize("interval", [1])
@pytest.mark.parametrize("offset_reference_times", [False, True])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize(
    "data, wet_bias, expected, reverse_wet_values, reverse_wet_keys",
    (
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. As 4 codes are wet, a wet code is produced.
        ([1, 3, 4, 5, 7, 8, 10, 10, 10, 10], 2, 10, False, False),
        # More dry codes (7) than wet codes (3),the most significant dry symbol
        # is selected after cloud equivalence, which become partly cloudy (3).
        ([1, 3, 4, 5, 7, 8, 8, 10, 10, 10], 1, 3, False, False),
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. As 3 codes are wet, a dry code is produced.
        ([1, 3, 4, 5, 7, 8, 8, 10, 10, 10], 2, 3, False, False),
        # A wet bias of 3 means that at least 1/(1+3) * 10 = 2.5 codes must be wet
        # in order to produce a wet code. As 3 codes are wet, a wet code is produced.
        ([1, 3, 4, 5, 7, 8, 8, 10, 10, 10], 3, 10, False, False),
        # A wet bias of 2 should have no impact on the chosen dry code if one is
        # chosen. In this case cloudy conditions dominate the dry codes, and the
        # cloud equivalents to the showers are partly cloudy. If the wet bias were
        # multiplying up the wet code cloud equivalents we would expect (3) to
        # be the resulting dry symbol (5x3), but instead we end up tied 3x3 and 3x7,
        # so the more significant (7) code results. This is what we want.
        ([7, 7, 7, 1, 3, 10, 10], 2, 7, False, False),
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. A tie between the wet codes with the
        # highest index selected.
        ([1, 3, 4, 5, 7, 8, 10, 10, 14, 14], 2, 14, False, False),
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. A tie between the wet codes with the
        # lowest index (after reversing the dictionary) selected.
        ([1, 3, 4, 5, 7, 8, 10, 10, 14, 14], 2, 10, True, False),
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. A tie between the wet codes with the
        # highest index selected.
        ([1, 3, 4, 5, 7, 8, 10, 10, 18, 18], 2, 18, True, False),
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. A tie between the wet codes with the
        # lowest index (after reversing the dictionary) selected.
        ([1, 3, 4, 5, 7, 8, 10, 10, 18, 18], 2, 10, True, True),
        # A wet bias of 2 means that at least 1/(1+2) * 10 = 3.33 codes must be wet
        # in order to produce a wet code. The point with 1 wet symbol gets a dry code,
        # whilst the point with 4 codes gets a wet code.
        (
            [[1, 3, 4, 5, 7, 8, 10, 1, 1, 1], [1, 3, 4, 5, 7, 8, 10, 10, 10, 10]],
            2,
            [1, 10],
            False,
            False,
        ),
        # Wet bias does not impact the contribution of wet code dry equivalents
        # in determining the overall summary in dry dominated scenarios. Here the
        # large wet bias does not lead to a partly cloudy summary code, once the
        # shower code is dried it contributes only a single partly cloudy
        # code which is insufficient to change the chosen cloudy (7) summary.
        ([1, 3, 4, 7, 7, 9], 3, 7, False, False),
    ),
)
def test_expected_values_wet_bias(
    wxcode_series, wet_bias, expected, reverse_wet_values, reverse_wet_keys
):
    """Test that the expected period representative symbol is returned."""
    _, _, _, _, wxcode_cubes = wxcode_series
    wet_categories = WET_CATEGORIES.copy()
    if reverse_wet_values:
        wet_categories = {}
        for key in WET_CATEGORIES.keys():
            wet_categories[key] = [i for i in reversed(WET_CATEGORIES[key])]
    if reverse_wet_keys:
        wet_categories = dict(reversed(list(wet_categories.items())))

    result = ModalFromGroupings(
        wxcode_decision_tree(),
        BROAD_CATEGORIES,
        wet_categories,
        wet_bias=wet_bias,
    )(wxcode_cubes)
    expected = [expected] if not isinstance(expected, list) else expected
    for index in range(len(expected)):
        assert result.data.flatten()[index] == expected[index]


@pytest.mark.parametrize("record_run_attr", [False])
@pytest.mark.parametrize("model_id_attr", [False, True])
@pytest.mark.parametrize("offset_reference_times", [False, True])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize(
    "data, interval, day_weighting, day_start, day_end, day_length, expected",
    (
        # All weather codes supplied are considered as daytime.
        # There are more light shower codes, so this is the modal code.
        ([10, 10, 10, 10, 10, 1, 1, 1, 1], 1, 1, 0, 9, 24, 10),
        # For a day length of 9 and a day weighting of 2, the number of clear day codes
        # doubles with one more shower symbol giving 6 dry codes, and 5 wet codes.
        ([10, 10, 10, 10, 1, 1, 1, 1, 1], 1, 2, 3, 5, 9, 1),
        # Dry with one wet symbol changed to a cloud equivalent (3). This falls in the
        # day weighting period, meaning we end up with 5x1 and 5x3, such that the more
        # significant weather code (3) will be chosen. This demonstrates that the day
        # weighting multiplication of the wet codes does impact the chosen dry code
        # when these codes fall in the period of enhanced day weighting.
        ([1, 1, 1, 10, 8, 1, 3, 3, 3], 1, 2, 3, 5, 9, 3),
        # Selecting a different period results in 6 dry codes and 6 wet codes,
        # so the resulting code is wet.
        ([10, 10, 10, 10, 10, 1, 1, 1, 1], 1, 2, 4, 7, 9, 10),
        # A day weighting of 2 with a day length of 24 means that none of these codes
        # fall within the day period, and therefore the modal code is dry (1).
        ([10, 10, 10, 10, 1, 1, 1, 1, 1], 1, 2, 9, 15, 24, 1),
        # A day weighting of 2 with a day length of 24 means that none of these codes
        # fall within the day period, and therefore the modal code is wet (10).
        ([10, 10, 10, 10, 10, 1, 1, 1, 1], 1, 2, 4, 7, 24, 10),
        # Increasing the day weighting to 3 results in 8 dry codes and 7 wet codes, so
        # the resulting code is dry.
        ([10, 10, 10, 10, 10, 1, 1, 1, 1], 1, 3, 4, 7, 9, 1),
        # An example for two points with the first point being dry, and the second point
        # being wetter, with day weighting resulting in a dry modal code.
        (
            [[1, 1, 1, 1, 1, 1, 1, 1, 1], [10, 10, 10, 10, 10, 1, 1, 1, 1]],
            1,
            3,
            4,
            7,
            9,
            [1, 1],
        ),
        # An example for two points for the first point being mostly dry, and the
        # second point being wetter, with day weighting resulting in a dry modal code.
        (
            [[1, 1, 1, 1, 10, 1, 1, 1, 1], [1, 1, 10, 10, 10, 1, 1, 1, 1]],
            1,
            3,
            2,
            5,
            9,
            [1, 10],
        ),
        # More clear symbols, but partly cloudy symbol is emphasised more as it
        # falls within the mid part of the day. Resulting symbol is partly cloudy.
        # Uses 3-hourly data to ensure file counting works for non-hourly inputs.
        ([0, 0, 1, 3, 3, 10, 12, 12], 3, 2, 6, 18, 24, 3),
    ),
)
def test_expected_values_day_weighting(
    wxcode_series, day_weighting, day_start, day_end, day_length, expected
):
    """Test that the expected period representative symbol is returned."""
    _, _, _, _, wxcode_cubes = wxcode_series
    class_instance = ModalFromGroupings
    class_instance.DAY_LENGTH = day_length
    result = ModalFromGroupings(
        wxcode_decision_tree(),
        BROAD_CATEGORIES,
        WET_CATEGORIES,
        day_weighting=day_weighting,
        day_start=day_start,
        day_end=day_end,
    )(wxcode_cubes)
    expected = [expected] if not isinstance(expected, list) else expected
    for index in range(len(expected)):
        assert result.data.flatten()[index] == expected[index]


@pytest.mark.parametrize("record_run_attr", [False])
@pytest.mark.parametrize("model_id_attr", [False, True])
@pytest.mark.parametrize("interval", [1])
@pytest.mark.parametrize("offset_reference_times", [False, True])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize(
    "data, ignore_intensity, expected, reverse_intensity_dict",
    (
        # Dry dominated. Rain contributes overcast conditions. Cloud therefore
        # becomes the dry code. The cloud group contains 2 overcast codes and
        # 1 cloudy code, so overcast (8) is chosen.
        ([1, 1, 1, 7, 12, 12], True, 8, False),
        # Dry dominated. Showers contribute partly cloudy conditions meaning
        # the sunny/partly cloudy group provides the summary code. Of this
        # there are 2 sunny and 2 partly cloud codes, with the latter chosen (3)
        # as more significant.
        ([1, 1, 10, 14, 8, 8, 8], True, 3, False),
        # Dry. The overcast cloud code (8) is the single dominant code. However,
        # partly cloudy and sunny are more dominant when grouped. Of these 5
        # codes sunny (1) is dominant and is therefore returned.
        ([1, 1, 1, 3, 3, 8, 8, 8, 8], True, 1, False),
        # All precipitation is frozen. Sleet shower is the modal code.
        ([23, 23, 23, 26, 17, 17, 17, 17], False, 17, False),
        # When snow shower codes are grouped, light snow shower is chosen as it
        # is the most common weather code.
        ([23, 23, 23, 26, 17, 17, 17, 17], True, 23, False),
        # When snow shower codes are grouped, heavy snow shower is chosen as the
        # snow shower codes are equally likely, so the first entry within the
        # intensity category dictionary is chosen.
        ([23, 23, 26, 26, 17, 17, 17, 17], True, 26, False),
        # Demonstrate that reversing the ordering within the intensity categories
        # gives a different result in the event of a tie.
        ([23, 23, 26, 26, 17, 17, 17, 17], True, 23, True),
        # Use ignore intensity option, with wet symbols that do not have intensity
        # variants.
        ([11, 11, 11, 11, 11, 11, 11, 11], True, 11, False),
        # When snow shower codes are grouped, heavy snow shower is chosen as the
        # snow shower codes are equally likely, so the first entry within the
        # intensity category dictionary is chosen.
        (
            [[1, 1, 1, 1, 1, 1, 1, 1], [23, 23, 26, 26, 17, 17, 17, 17]],
            True,
            [1, 26],
            False,
        ),
        # Demonstrate that the visibility category allows low vis to dominate.
        ([5, 5, 6, 6, 1, 1, 1], True, 5, False),
        # As above but reversed intensity order to yield fog instead of mist.
        ([5, 5, 6, 6, 1, 1, 1], True, 6, True),
    ),
)
def test_expected_values_ignore_intensity(
    wxcode_series, ignore_intensity, expected, reverse_intensity_dict
):
    """Test that the expected period representative symbol is returned."""
    _, _, _, _, wxcode_cubes = wxcode_series
    if ignore_intensity:
        intensity_categories = INTENSITY_CATEGORIES.copy()
        if reverse_intensity_dict:
            intensity_categories = {}
            for key in INTENSITY_CATEGORIES.keys():
                intensity_categories[key] = [
                    i for i in reversed(INTENSITY_CATEGORIES[key])
                ]
    else:
        intensity_categories = None
    result = ModalFromGroupings(
        wxcode_decision_tree(),
        BROAD_CATEGORIES,
        WET_CATEGORIES,
        intensity_categories=intensity_categories,
    )(wxcode_cubes)
    expected = [expected] if not isinstance(expected, list) else expected
    for index in range(len(expected)):
        assert result.data.flatten()[index] == expected[index]


@pytest.mark.parametrize("record_run_attr", [False])
@pytest.mark.parametrize("model_id_attr", [False, True])
@pytest.mark.parametrize("interval", [1])
@pytest.mark.parametrize("offset_reference_times", [False, True])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize(
    "data, wet_bias, day_weighting, day_start, day_end, day_length, ignore_intensity, expected",
    (
        # The sleet code is the most common, so this is the modal code.
        ([17, 17, 17, 17, 26, 23, 23, 23], 1, 1, 0, 12, 8, False, 17),
        # The day weighting with the day start and day end set to same value has no
        # impact on the modal code.
        ([17, 17, 17, 17, 26, 23, 23, 23], 1, 10, 3, 3, 8, False, 17),
        # The day weighting is set to emphasise the heavy snow shower (26).
        ([17, 17, 17, 17, 26, 23, 23, 23], 1, 10, 4, 5, 8, False, 26),
        # Without any weighting, there would be a dry symbol. A day weighting of 2
        # results in 6 dry codes and 5 wet codes. A wet bias of 2 means that at
        # least 1/(1+2) * 11 = 3.67 codes must be wet in order to produce a wet code.
        # As 5 codes are wet, a wet code is produced.
        ([1, 1, 1, 1, 1, 17, 17, 17], 2, 2, 4, 7, 8, False, 17),
        # Mixed precipitation. Day weighting results in the heavy rain (15) codes
        # doubling. This leads to 4 heavy rain codes vs 4 light rain codes with the
        # heavy rain codes taking precedence.
        ([10, 11, 12, 15, 15, 12, 12, 10, 3, 3, 3], 1, 2, 0, 5, 11, False, 15),
        # Similar to the example above with the intensity categorisation included.
        # The heavy rain (15) code is still the result.
        ([10, 11, 12, 15, 15, 12, 12, 10, 3, 3, 3], 1, 2, 0, 5, 11, True, 15),
        # All precipitation is frozen. Ignoring the intensities means that a
        # day weighting of 2 results in 8 sleet codes and 8 light snow shower codes.
        # A wet bias of 2 means that at least 1/(1+2) * 16 = 5.33 codes must be wet
        # in order to produce a wet code. As all codes are wet, a wet code is produced.
        # The snow code is chosen as it is the most significant frozen precipitation,
        # and ignoring intensity option ensures that the modal code is set to the
        # most common snow shower code.
        ([17, 17, 17, 17, 26, 23, 23, 23], 2, 2, 0, 8, 8, True, 23),
        # Similar to the example above but for 2 points.
        (
            [[17, 17, 17, 17, 26, 26, 23, 23], [17, 17, 17, 17, 26, 23, 23, 23]],
            2,
            2,
            0,
            8,
            8,
            True,
            [26, 23],
        ),
        # The day emphasis and dry equivalent codes for wet codes in that period
        # conspire to give an overcast (8) code to summarise the day. We include
        # emphasis of the dried codes as these still fall in the period that we
        # want to emphasise.
        ([1, 1, 12, 12, 8, 1, 1, 1], 1, 2, 2, 6, 8, True, 8),
        # Day emphasis and drying (dry dominated) are such that we end up with
        # 6, 6, 8, 8, 8, 8, 3, 3, 1, 1, 1, 5. The intensity consolidation
        # groups the partly cloudy (3) and sunny (1) codes together making this
        # the dominant group. Of this group sunny codes dominate and this becomes
        # the summary code (1).
        ([6, 6, 12, 12, 3, 1, 1, 5], 1, 2, 2, 6, 8, True, 1),
        # As above but without the intensity consolidation. The sunny and partly
        # sunny remain ungrouped allowing the dried rain, which has become
        # overcast codes to dominate. We get an overcast (8) summary.
        ([6, 6, 12, 12, 3, 1, 1, 5], 1, 2, 2, 6, 8, False, 8),
        # Looking again at the same case but with both a wet bias and a day
        # emphasis of 2 we now get a wet dominated day. The codes are
        # 6, 6, 12, 12, 12, 12, 3, 3, 1, 1, 1, 5, but wet codes count twice
        # in determining the dominant conditions. 8 wet vs 8 dry results in a wet
        # summary code. Intensity consolidation amongst the dry codes is
        # irrelevant as is the cloud equivalence.
        ([6, 6, 12, 12, 3, 1, 1, 5], 2, 2, 2, 6, 8, True, 12),
    ),
)
def test_expected_values_interactions(
    wxcode_series,
    wet_bias,
    day_weighting,
    day_start,
    day_end,
    day_length,
    ignore_intensity,
    expected,
):
    """Test that the expected period representative symbol is returned."""
    _, _, _, _, wxcode_cubes = wxcode_series
    class_instance = ModalFromGroupings
    class_instance.DAY_LENGTH = day_length
    if ignore_intensity:
        intensity_categories = INTENSITY_CATEGORIES.copy()
    else:
        intensity_categories = None

    result = class_instance(
        wxcode_decision_tree(),
        BROAD_CATEGORIES,
        WET_CATEGORIES,
        intensity_categories=intensity_categories,
        wet_bias=wet_bias,
        day_weighting=day_weighting,
        day_start=day_start,
        day_end=day_end,
    )(wxcode_cubes)
    expected = [expected] if not isinstance(expected, list) else expected
    for index in range(len(expected)):
        assert result.data.flatten()[index] == expected[index]


@pytest.mark.parametrize("record_run_attr", [False, True])
@pytest.mark.parametrize("model_id_attr", [False, True])
@pytest.mark.parametrize("interval", [1, 3])
@pytest.mark.parametrize("offset_reference_times", [False, True])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize("data", [np.ones(12), np.ones(1)])
def test_metadata(wxcode_series):
    """Check that the returned metadata is correct. In this case we expect a
    time coordinate with bounds that describe the full period over which the
    representative symbol has been calculated while the forecast_reference_time
    will be the latest of those input and the forecast_period will be the
    difference between the forecast_reference_time and time.

    A single data point is tested which means a single cube is passed in. This
    ensures the metadata is consistent whether or not the input data has passed
    through the modal aggregator."""

    def as_utc_timestamp(time):
        return timegm(time.utctimetuple())

    (
        interval,
        model_id_attr,
        record_run_attr,
        offset_reference_times,
        wxcode_cubes,
    ) = wxcode_series

    kwargs = {}
    if model_id_attr:
        kwargs.update({"model_id_attr": MODEL_ID_ATTR})
    if record_run_attr:
        kwargs.update({"record_run_attr": RECORD_RUN_ATTR})

    result = ModalFromGroupings(
        wxcode_decision_tree(),
        BROAD_CATEGORIES,
        WET_CATEGORIES,
        intensity_categories=INTENSITY_CATEGORIES,
        **kwargs,
    )(wxcode_cubes)

    n_times = len(wxcode_cubes)
    expected_time = TARGET_TIME
    expected_bounds = [TARGET_TIME - timedelta(hours=n_times * interval), TARGET_TIME]
    expected_reference_time = TARGET_TIME - timedelta(hours=42)
    expected_forecast_period = (expected_time - expected_reference_time).total_seconds()
    expected_forecast_period_bounds = [
        expected_forecast_period - n_times * interval * 3600,
        expected_forecast_period,
    ]
    expected_model_id_attr = "uk_det uk_ens"
    expected_record_det = "uk_det:20200613T2300Z:\n"
    expected_record_ens = "uk_ens:20200613T{}00Z:"

    # Expected record_run attribute contains all contributing cycle times.
    if offset_reference_times and len(wxcode_cubes) > 1:
        expected_record_run_attr = expected_record_det + "\n".join(
            [expected_record_ens.format(value) for value in range(10, 22)]
        )
    else:
        expected_record_run_attr = expected_record_det + expected_record_ens.format(21)

    assert result.coord("time").points[0] == as_utc_timestamp(expected_time)
    assert result.coord("time").bounds[0][0] == as_utc_timestamp(expected_bounds[0])
    assert result.coord("time").bounds[0][1] == as_utc_timestamp(expected_bounds[1])
    assert result.coord("forecast_reference_time").points[0] == as_utc_timestamp(
        expected_reference_time
    )
    assert not result.coord("forecast_reference_time").has_bounds()
    assert result.coord("forecast_period").points[0] == expected_forecast_period
    assert np.allclose(
        result.coord("forecast_period").bounds[0], expected_forecast_period_bounds
    )
    assert result.cell_methods[0].method == "mode"
    assert result.cell_methods[0].coord_names[0] == "time"
    assert result.cell_methods[0].intervals[0] == f"{interval} hour"
    if model_id_attr:
        assert result.attributes[MODEL_ID_ATTR] == expected_model_id_attr
    else:
        assert MODEL_ID_ATTR not in result.attributes.keys()
    if record_run_attr and model_id_attr:
        assert RECORD_RUN_ATTR in result.attributes.keys()
        assert result.attributes[RECORD_RUN_ATTR] == expected_record_run_attr
    else:
        assert RECORD_RUN_ATTR not in result.attributes.keys()


@pytest.mark.parametrize("record_run_attr", [False])
@pytest.mark.parametrize("model_id_attr", [False])
@pytest.mark.parametrize("interval", [1, 3])
@pytest.mark.parametrize("offset_reference_times", [False])
@pytest.mark.parametrize("cube_type", ["gridded", "spot"])
@pytest.mark.parametrize("data", [[1, 1, 1, 15]])
def test_unmatching_bounds_exception(wxcode_series):
    """Test that an exception is raised if inputs do not represent the same
    intervals."""
    _, _, _, _, wxcode_cubes = wxcode_series
    bounds = wxcode_cubes[0].coord("time").bounds.copy()
    bounds[0][0] += 1800
    wxcode_cubes[0].coord("time").bounds = bounds
    with pytest.raises(
        ValueError, match="Input diagnostics do not have consistent periods."
    ):
        ModalFromGroupings(
            wxcode_decision_tree(),
            BROAD_CATEGORIES,
            WET_CATEGORIES,
            intensity_categories=INTENSITY_CATEGORIES,
        )(wxcode_cubes)
