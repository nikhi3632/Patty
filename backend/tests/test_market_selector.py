import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.pricing.market_selector import find_nearest_market


@pytest.mark.integration
def test_chicago_restaurant_gets_chicago_market():
    result = find_nearest_market(41.8898, -87.6303)
    assert result == "Chicago"


@pytest.mark.integration
def test_new_city_ny_gets_new_york_market():
    result = find_nearest_market(41.1395, -73.9895)
    assert result == "New York"


@pytest.mark.integration
def test_miami_restaurant_gets_miami_market():
    result = find_nearest_market(25.76, -80.19)
    assert result == "Miami"


@pytest.mark.integration
def test_la_restaurant_gets_la_market():
    result = find_nearest_market(34.05, -118.24)
    assert result == "Los Angeles"
