from src.core.pricing.trend_analyzer import (
    resolve_mars_market,
    classify_signal,
)


# --- resolve_mars_market ---


def test_resolve_mars_market_exact_match():
    assert resolve_mars_market("Chicago", 41.88, -87.63) == "Chicago"


def test_resolve_mars_market_fallback_to_nearest():
    # "New York" not in MARS markets, should fall back to "Bronx"
    result = resolve_mars_market("New York", 40.71, -74.01)
    assert result == "Bronx"


def test_resolve_mars_market_boston_falls_to_nearest():
    # Boston not in MARS, nearest should be Bronx or Philadelphia
    result = resolve_mars_market("Boston", 42.36, -71.06)
    assert result in ("Bronx", "Philadelphia")


def test_resolve_mars_market_seattle_falls_to_everett():
    result = resolve_mars_market("Seattle", 47.61, -122.33)
    assert result == "Everett"


# --- classify_signal ---


def test_classify_both_up():
    assert classify_signal(10.0, 8.0) == "strong_up"


def test_classify_both_down():
    assert classify_signal(-7.0, -12.0) == "strong_down"


def test_classify_both_flat():
    assert classify_signal(2.0, -1.0) == "stable"


def test_classify_mixed():
    assert classify_signal(10.0, -8.0) == "mixed"


def test_classify_one_up_one_flat():
    assert classify_signal(10.0, 2.0) == "moderate_up"


def test_classify_one_down_one_flat():
    assert classify_signal(-1.0, -8.0) == "moderate_down"


def test_classify_only_mars():
    assert classify_signal(10.0, None) == "moderate_up"
    assert classify_signal(-10.0, None) == "moderate_down"
    assert classify_signal(2.0, None) == "stable"


def test_classify_only_nass():
    assert classify_signal(None, 10.0) == "moderate_up"
    assert classify_signal(None, -10.0) == "moderate_down"


def test_classify_neither():
    assert classify_signal(None, None) == "stable"
