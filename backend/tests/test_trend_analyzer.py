from unittest.mock import patch, MagicMock
from src.core.pricing.trend_analyzer import (
    resolve_mars_market,
    pct_changes,
    std,
    mean,
    percentile,
    compute_vol_stats,
    autocorrelation,
    compute_dynamic_horizon,
    calibrate,
    compute_z_score,
    date_range_for_horizon,
    classify_signal,
    series_checksum,
    load_or_recalibrate,
    build_mars_series,
    build_nass_series,
    compute_trends,
)

MOCK_DB_MARKET_COORDS = {
    "Atlanta": (33.749, -84.388),
    "Baltimore": (39.290, -76.612),
    "Bronx": (40.837, -73.865),
    "Chicago": (41.878, -87.630),
    "Detroit": (42.331, -83.046),
    "Everett": (47.979, -122.202),
    "Los Angeles": (34.052, -118.244),
    "Miami": (25.762, -80.192),
    "Philadelphia": (39.953, -75.164),
}


# --- resolve_mars_market ---


@patch(
    "src.core.pricing.trend_analyzer.get_db_market_coords",
    return_value=MOCK_DB_MARKET_COORDS,
)
def test_resolve_mars_market_exact_match(mock_coords):
    mock_sb = MagicMock()
    assert resolve_mars_market(mock_sb, 41.88, -87.63) == "Chicago"


@patch(
    "src.core.pricing.trend_analyzer.get_db_market_coords",
    return_value=MOCK_DB_MARKET_COORDS,
)
def test_resolve_mars_market_fallback_to_nearest(mock_coords):
    mock_sb = MagicMock()
    result = resolve_mars_market(mock_sb, 40.71, -74.01)
    assert result == "Bronx"


@patch(
    "src.core.pricing.trend_analyzer.get_db_market_coords",
    return_value=MOCK_DB_MARKET_COORDS,
)
def test_resolve_mars_market_seattle_falls_to_everett(mock_coords):
    mock_sb = MagicMock()
    result = resolve_mars_market(mock_sb, 47.61, -122.33)
    assert result == "Everett"


# --- pct_changes ---


def test_pct_changes_basic():
    series = [100, 110, 105, 115]
    changes = pct_changes(series)
    assert len(changes) == 3
    assert abs(changes[0] - 10.0) < 0.01
    assert abs(changes[1] - (-4.545)) < 0.01
    assert abs(changes[2] - 9.524) < 0.01


def test_pct_changes_empty():
    assert pct_changes([]) == []
    assert pct_changes([100]) == []


def test_pct_changes_skips_zero_base():
    changes = pct_changes([0, 100, 200])
    assert len(changes) == 1
    assert abs(changes[0] - 100.0) < 0.01


# --- std / mean ---


def test_std_basic():
    vals = [2, 4, 4, 4, 5, 5, 7, 9]
    result = std(vals)
    # Sample std (n-1): sqrt(32/7) ≈ 2.138
    assert abs(result - 2.138) < 0.01


def test_std_single():
    assert std([5]) == 0.0
    assert std([]) == 0.0


def test_mean_basic():
    assert mean([1, 2, 3, 4, 5]) == 3.0
    assert mean([]) == 0.0


# --- percentile ---


def test_percentile_basic():
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile(vals, 50) == 5.5
    assert percentile(vals, 0) == 1.0
    assert percentile(vals, 100) == 10.0


def test_percentile_quartiles():
    vals = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0]
    p25 = percentile(vals, 25)
    p75 = percentile(vals, 75)
    assert p25 < p75
    assert 4.0 < p25 < 7.0
    assert 12.0 < p75 < 15.0


# --- compute_vol_stats ---


def test_vol_stats_from_calibrations():
    mock_sb = MagicMock()
    mock_result = MagicMock()
    mock_result.data = [
        {"volatility": 2.0},
        {"volatility": 5.0},
        {"volatility": 8.0},
        {"volatility": 12.0},
        {"volatility": 20.0},
        {"volatility": 30.0},
    ]
    mock_sb.table.return_value.select.return_value.gt.return_value.execute.return_value = mock_result

    stats = compute_vol_stats(mock_sb)
    assert stats["p25"] < stats["p50"] < stats["p75"]
    assert stats["p25"] > 0


def test_vol_stats_bootstrap_fallback():
    mock_sb = MagicMock()
    mock_result = MagicMock()
    mock_result.data = [{"volatility": 5.0}]
    mock_sb.table.return_value.select.return_value.gt.return_value.execute.return_value = mock_result

    stats = compute_vol_stats(mock_sb)
    assert stats == {"p25": 3.0, "p50": 8.0, "p75": 15.0}


# --- autocorrelation ---


def test_autocorrelation_periodic():
    series = [1, 2, 3, 4] * 10
    lag = autocorrelation(series, max_lag=8)
    assert lag == 4


def test_autocorrelation_short_series():
    lag = autocorrelation([1, 2, 3])
    assert lag >= 1


def test_autocorrelation_constant():
    lag = autocorrelation([5, 5, 5, 5, 5])
    assert lag == 1


# --- compute_dynamic_horizon ---

SAMPLE_VOL_STATS = {"p25": 3.0, "p50": 8.0, "p75": 15.0}


def test_dynamic_horizon_high_volatility():
    # Volatility at p75 → vol_pct=1.0 → scale=0.5 → short horizon
    h = compute_dynamic_horizon(15.0, 10, 100, SAMPLE_VOL_STATS)
    assert h <= 6


def test_dynamic_horizon_low_volatility():
    # Volatility at p25 → vol_pct=0.0 → scale=2.0 → long horizon
    h = compute_dynamic_horizon(3.0, 5, 100, SAMPLE_VOL_STATS)
    assert h >= 8


def test_dynamic_horizon_medium_volatility():
    # Volatility at p50 → vol_pct≈0.42 → scale≈1.37
    h = compute_dynamic_horizon(8.0, 6, 100, SAMPLE_VOL_STATS)
    assert 5 <= h <= 12


def test_dynamic_horizon_small_dataset():
    h = compute_dynamic_horizon(10.0, 5, 4, SAMPLE_VOL_STATS)
    assert h == 2


def test_dynamic_horizon_capped_at_half():
    h = compute_dynamic_horizon(5.0, 30, 20, SAMPLE_VOL_STATS)
    assert h <= 10


def test_dynamic_horizon_continuous_scaling():
    # Higher volatility → shorter horizon (continuous, no jumps)
    h_low = compute_dynamic_horizon(3.0, 8, 100, SAMPLE_VOL_STATS)
    h_mid = compute_dynamic_horizon(9.0, 8, 100, SAMPLE_VOL_STATS)
    h_high = compute_dynamic_horizon(15.0, 8, 100, SAMPLE_VOL_STATS)
    assert h_low > h_mid > h_high


def test_dynamic_horizon_adapts_to_vol_stats():
    # Same volatility (10.0) but different distributions → different horizons
    narrow = {"p25": 8.0, "p50": 10.0, "p75": 12.0}
    wide = {"p25": 2.0, "p50": 10.0, "p75": 30.0}

    h_narrow = compute_dynamic_horizon(10.0, 6, 100, narrow)
    h_wide = compute_dynamic_horizon(10.0, 6, 100, wide)

    # In a narrow distribution, 10.0 is at the 50th percentile
    # In a wide distribution, 10.0 is closer to the 25th percentile (more stable)
    assert h_wide >= h_narrow


# --- calibrate ---


def test_calibrate_sufficient_data():
    series = [100, 102, 98, 105, 103, 99, 107, 101, 104, 100]
    cal = calibrate(series, "MARS", "Chicago")
    assert cal["source"] == "MARS"
    assert cal["market"] == "Chicago"
    assert cal["data_points_used"] == 10
    assert cal["volatility"] > 0
    assert cal["std_change"] > 0
    # dynamic_horizon is 0 (set later by compute_trends with vol_stats)
    assert cal["dynamic_horizon"] == 0


def test_calibrate_insufficient_data():
    series = [100, 102]
    cal = calibrate(series, "NASS")
    assert cal["mean_change"] == 0.0
    assert cal["std_change"] == 0.0
    assert cal["data_points_used"] == 2


def test_calibrate_volatile_series():
    series = [
        100,
        150,
        80,
        160,
        70,
        140,
        90,
        130,
        75,
        145,
        85,
        155,
        65,
        170,
        60,
        180,
        50,
        190,
        55,
        175,
    ]
    cal = calibrate(series, "MARS", "Bronx")
    assert cal["volatility"] > 10


def test_calibrate_stable_series():
    series = [
        100,
        100.5,
        99.8,
        100.2,
        100.1,
        99.9,
        100.3,
        100.0,
        99.7,
        100.4,
        100.1,
        99.8,
        100.2,
        100.0,
        99.9,
        100.1,
    ]
    cal = calibrate(series, "NASS")
    assert cal["volatility"] < 2.0


# --- date_range_for_horizon ---


def test_date_range_basic():
    dates = [
        "2025-01-01",
        "2025-01-02",
        "2025-01-03",
        "2025-01-04",
        "2025-01-05",
        "2025-01-06",
    ]
    result = date_range_for_horizon(dates, 3)
    assert result == "2025-01-01 to 2025-01-06"


def test_date_range_insufficient():
    dates = ["2025-01-01", "2025-01-02"]
    assert date_range_for_horizon(dates, 3) is None


def test_date_range_empty():
    assert date_range_for_horizon([], 3) is None


def test_date_range_nass_format():
    dates = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
    result = date_range_for_horizon(dates, 2)
    assert result == "2024-03 to 2024-06"


# --- compute_z_score ---


def test_z_score_normal_change():
    series = [100, 101, 99, 100, 101, 100, 99, 101, 100, 102]
    result = compute_z_score(series, horizon=3, mean_change=0.5, std_change=2.0)
    assert result is not None
    assert "z_score" in result
    assert "change_pct" in result
    assert abs(result["z_score"]) < 2.0


def test_z_score_big_spike():
    series = [100, 100, 100, 100, 100, 100, 100, 100, 130, 135, 140]
    result = compute_z_score(series, horizon=3, mean_change=0.0, std_change=1.0)
    assert result is not None
    assert result["z_score"] > 2.0


def test_z_score_big_drop():
    series = [100, 100, 100, 100, 100, 100, 100, 100, 70, 65, 60]
    result = compute_z_score(series, horizon=3, mean_change=0.0, std_change=1.0)
    assert result is not None
    assert result["z_score"] < -2.0


def test_z_score_insufficient_data():
    result = compute_z_score([100, 110], horizon=3, mean_change=0.0, std_change=1.0)
    assert result is None


def test_z_score_zero_std():
    series = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    result = compute_z_score(series, horizon=3, mean_change=0.0, std_change=0.0)
    assert result is not None
    assert result["z_score"] == 0.0


# --- classify_signal (z-score based) ---


def test_classify_both_strong_up():
    assert classify_signal(2.5, 2.1) == "strong_up"


def test_classify_both_strong_down():
    assert classify_signal(-2.5, -3.0) == "strong_down"


def test_classify_strong_plus_moderate_up():
    assert classify_signal(2.5, 1.7) == "strong_up"


def test_classify_strong_plus_moderate_down():
    assert classify_signal(-1.6, -2.3) == "strong_down"


def test_classify_both_moderate_up():
    assert classify_signal(1.7, 1.6) == "moderate_up"


def test_classify_both_moderate_down():
    assert classify_signal(-1.8, -1.5) == "moderate_down"


def test_classify_both_flat():
    assert classify_signal(0.5, -0.3) == "stable"


def test_classify_mixed():
    assert classify_signal(2.5, -2.0) == "mixed"


def test_classify_mixed_moderate():
    assert classify_signal(1.7, -1.8) == "mixed"


def test_classify_one_up_one_flat():
    assert classify_signal(2.0, 0.5) == "moderate_up"


def test_classify_one_down_one_flat():
    assert classify_signal(0.2, -1.8) == "moderate_down"


def test_classify_only_mars():
    assert classify_signal(2.5, None) == "moderate_up"
    assert classify_signal(-2.5, None) == "moderate_down"
    assert classify_signal(0.5, None) == "stable"


def test_classify_only_nass():
    assert classify_signal(None, 1.8) == "moderate_up"
    assert classify_signal(None, -2.5) == "moderate_down"


def test_classify_neither():
    assert classify_signal(None, None) == "stable"


# --- series_checksum ---


def test_series_checksum_deterministic():
    s = [100.0, 102.5, 99.8]
    assert series_checksum(s) == series_checksum(s)


def test_series_checksum_changes_on_correction():
    original = [100.0, 102.5, 99.8]
    corrected = [100.0, 103.0, 99.8]  # middle value corrected
    assert series_checksum(original) != series_checksum(corrected)


def test_series_checksum_same_count_different_values():
    a = [10.0, 20.0, 30.0]
    b = [10.0, 20.0, 30.1]
    assert len(a) == len(b)
    assert series_checksum(a) != series_checksum(b)


# --- load_or_recalibrate ---


def test_load_or_recalibrate_cache_hit():
    series = list(range(20))
    mock_sb = MagicMock()
    stored = {
        "commodity_id": "c1",
        "source": "MARS",
        "market": "Chicago",
        "volatility": 5.0,
        "autocorrelation_lag": 3,
        "dynamic_horizon": 6,
        "mean_change": 0.5,
        "std_change": 2.0,
        "data_points_used": 20,
        "series_checksum": series_checksum(series),
    }
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[stored]
    )

    result = load_or_recalibrate(
        mock_sb, "c1", list(range(20)), "MARS", "Chicago", "now"
    )
    assert result == stored
    mock_sb.table.return_value.upsert.assert_not_called()


def test_load_or_recalibrate_cache_miss():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"data_points_used": 10}]
    )
    mock_sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    series = [
        100,
        102,
        98,
        105,
        103,
        99,
        107,
        101,
        104,
        100,
        106,
        103,
        99,
        108,
        101,
        105,
        100,
        103,
        107,
        102,
    ]
    result = load_or_recalibrate(mock_sb, "c1", series, "MARS", "Chicago", "now")
    assert result["data_points_used"] == 20
    assert result["volatility"] > 0


def test_load_or_recalibrate_checksum_mismatch():
    """Same data_points_used but different values (data correction) → recalibrate."""
    mock_sb = MagicMock()
    stored = {
        "data_points_used": 5,
        "series_checksum": series_checksum([10.0, 20.0, 30.0, 40.0, 50.0]),
    }
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[stored]
    )
    mock_sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    corrected = [10.0, 20.0, 35.0, 40.0, 50.0]  # 3rd value corrected
    result = load_or_recalibrate(mock_sb, "c1", corrected, "MARS", "Chicago", "now")
    assert result["data_points_used"] == 5
    assert result["series_checksum"] == series_checksum(corrected)


# --- build_mars_series ---


def test_build_mars_series():
    mock_sb = MagicMock()

    mock_commodities = MagicMock()
    mock_commodities.data = [{"raw_name": "TOMATOES"}]

    mock_prices = MagicMock()
    mock_prices.data = [
        {"report_date": "2025-01-01", "low_price": 10, "high_price": 12},
        {"report_date": "2025-01-01", "low_price": 11, "high_price": 13},
        {"report_date": "2025-01-02", "low_price": 14, "high_price": 16},
    ]

    def table_router(name):
        t = MagicMock()
        if name == "commodities":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_commodities
        elif name == "wholesale_prices":
            t.select.return_value.in_.return_value.eq.return_value.order.return_value.execute.return_value = mock_prices
        return t

    mock_sb.table.side_effect = table_router

    series, dates = build_mars_series(mock_sb, "tomatoes", "Chicago")
    assert len(series) == 2
    assert series[0] == 11.5
    assert series[1] == 15.0
    assert dates == ["2025-01-01", "2025-01-02"]


def test_build_mars_series_empty():
    mock_sb = MagicMock()
    mock_commodities = MagicMock()
    mock_commodities.data = []

    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_commodities

    series, dates = build_mars_series(mock_sb, "unknown", "Chicago")
    assert series == []
    assert dates == []


# --- build_nass_series ---


def test_build_nass_series():
    mock_sb = MagicMock()

    mock_commodities = MagicMock()
    mock_commodities.data = [{"raw_name": "WHEAT"}]

    mock_prices = MagicMock()
    mock_prices.data = [
        {"price": 5.0, "unit": "$/BU", "year": 2025, "month": 1},
        {"price": 5.2, "unit": "$/BU", "year": 2025, "month": 2},
        {"price": 4.8, "unit": "$/BU", "year": 2025, "month": 3},
    ]

    def table_router(name):
        t = MagicMock()
        if name == "commodities":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_commodities
        elif name == "commodity_prices":
            t.select.return_value.in_.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = mock_prices
        return t

    mock_sb.table.side_effect = table_router

    series, unit, dates = build_nass_series(mock_sb, "wheat")
    assert series == [5.0, 5.2, 4.8]
    assert unit == "$/BU"
    assert dates == ["2025-01", "2025-02", "2025-03"]


# --- compute_trends (integration) ---


@patch(
    "src.core.pricing.trend_analyzer.get_db_market_coords",
    return_value=MOCK_DB_MARKET_COORDS,
)
def test_compute_trends_full_flow(mock_coords):
    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "lat": "41.88",
        "lng": "-87.63",
    }

    mock_tracked = MagicMock()
    mock_tracked.data = [
        {
            "commodity_id": "c1",
            "raw_ingredient_name": "tomato",
            "commodities": {"id": "c1", "parent": "tomatoes"},
        }
    ]

    mars_commodities = MagicMock()
    mars_commodities.data = [{"raw_name": "TOMATOES"}]

    mars_prices = MagicMock()
    mars_prices.data = [
        {
            "report_date": f"2025-01-{i + 1:02d}",
            "low_price": 10 + i * 0.5,
            "high_price": 12 + i * 0.5,
        }
        for i in range(20)
    ]

    nass_commodities = MagicMock()
    nass_commodities.data = [{"raw_name": "TOMATOES"}]

    nass_prices = MagicMock()
    nass_prices.data = [
        {"price": 5.0 + i * 0.3, "unit": "$/CWT", "year": 2024, "month": i + 1}
        for i in range(12)
    ]

    # vol_stats query — return enough calibrations for real percentiles
    vol_stats_result = MagicMock()
    vol_stats_result.data = [
        {"volatility": 2.0},
        {"volatility": 5.0},
        {"volatility": 8.0},
        {"volatility": 12.0},
        {"volatility": 18.0},
    ]

    # calibration cache — return empty (force recalibration)
    empty_cal = MagicMock()
    empty_cal.data = []

    call_count = {"commodities": 0}

    def table_router(name):
        t = MagicMock()
        if name == "restaurants":
            t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif name == "restaurant_commodities":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_tracked
        elif name == "commodities":
            call_count["commodities"] += 1
            if call_count["commodities"] <= 1:
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mars_commodities
            else:
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = nass_commodities
        elif name == "wholesale_prices":
            t.select.return_value.in_.return_value.eq.return_value.order.return_value.execute.return_value = mars_prices
        elif name == "commodity_prices":
            t.select.return_value.in_.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value = nass_prices
        elif name == "commodity_calibrations":
            # load_or_recalibrate queries → cache miss; vol_stats query → return data
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = empty_cal
            t.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = empty_cal
            t.select.return_value.gt.return_value.execute.return_value = (
                vol_stats_result
            )
            t.upsert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "trends":
            t.upsert.return_value.execute.return_value = MagicMock(
                data=[{"id": "trend-1"}]
            )
        elif name == "trend_signals":
            t.upsert.return_value.execute.return_value = MagicMock(data=[{}])
        return t

    mock_sb.table.side_effect = table_router

    result = compute_trends(mock_sb, "r1")
    assert result["computed"] == 1
    assert len(result["trends"]) == 1
    assert "vol_stats" in result

    trend = result["trends"][0]
    assert trend["parent"] == "tomatoes"
    assert trend["signal"] in (
        "strong_up",
        "moderate_up",
        "stable",
        "moderate_down",
        "strong_down",
        "mixed",
    )
    assert trend["mars_calibration"] is not None
    assert trend["mars_calibration"]["volatility"] is not None
    assert trend["mars_calibration"]["dynamic_horizon"] > 0
    assert trend["nass_calibration"] is not None


@patch(
    "src.core.pricing.trend_analyzer.get_db_market_coords",
    return_value=MOCK_DB_MARKET_COORDS,
)
def test_compute_trends_no_data(mock_coords):
    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "lat": "41.88",
        "lng": "-87.63",
    }

    mock_tracked = MagicMock()
    mock_tracked.data = [
        {
            "commodity_id": "c1",
            "raw_ingredient_name": "saffron",
            "commodities": {"id": "c1", "parent": "saffron"},
        }
    ]

    empty = MagicMock()
    empty.data = []

    def table_router(name):
        t = MagicMock()
        if name == "restaurants":
            t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif name == "restaurant_commodities":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_tracked
        elif name == "commodities":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = empty
        elif name == "commodity_calibrations":
            t.select.return_value.gt.return_value.execute.return_value = empty
        return t

    mock_sb.table.side_effect = table_router

    result = compute_trends(mock_sb, "r1")
    assert result["computed"] == 0
