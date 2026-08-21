"""Testes do estado compartilhado da ferramenta de medição (ui/measure_state.py)."""

import math

import pytest

from ui.measure_state import MeasureState, convert_points, format_distance


def test_starts_inactive_with_no_result():
    state = MeasureState()
    assert state.is_page_active() is False
    assert state.last_segment() is None
    assert state.last_distance_pt() is None
    assert state.unit() == "mm"


def test_set_page_active_emits_signal_only_on_change():
    state = MeasureState()
    calls = []
    state.active_changed.connect(lambda: calls.append(1))

    state.set_page_active(True)
    assert len(calls) == 1
    state.set_page_active(True)
    assert len(calls) == 1
    state.set_page_active(False)
    assert len(calls) == 2


def test_set_unit_emits_signal_only_on_change():
    state = MeasureState()
    calls = []
    state.unit_changed.connect(lambda: calls.append(1))

    state.set_unit("cm")
    assert state.unit() == "cm"
    assert len(calls) == 1
    state.set_unit("cm")
    assert len(calls) == 1


def test_set_unit_rejects_invalid_unit():
    state = MeasureState()
    with pytest.raises(ValueError):
        state.set_unit("furlong")


def test_set_result_computes_distance_and_emits_signal():
    state = MeasureState()
    calls = []
    state.result_changed.connect(lambda: calls.append(1))

    state.set_result(page_index=0, start_pdf=(0, 0), end_pdf=(72, 0))

    assert state.last_segment() == (0, (0, 0), (72, 0))
    assert state.last_distance_pt() == pytest.approx(72.0)
    assert len(calls) == 1


def test_clear_result_is_a_noop_when_already_empty():
    state = MeasureState()
    calls = []
    state.result_changed.connect(lambda: calls.append(1))

    state.clear_result()

    assert calls == []


def test_clear_result_resets_state():
    state = MeasureState()
    state.set_result(page_index=0, start_pdf=(0, 0), end_pdf=(10, 0))

    state.clear_result()

    assert state.last_segment() is None
    assert state.last_distance_pt() is None


def test_convert_points_to_common_units():
    assert convert_points(72.0, "in") == pytest.approx(1.0)
    assert convert_points(72.0, "mm") == pytest.approx(25.4)
    assert convert_points(72.0, "cm") == pytest.approx(2.54)
    assert convert_points(72.0, "pt") == pytest.approx(72.0)


def test_convert_points_rejects_invalid_unit():
    with pytest.raises(ValueError):
        convert_points(10.0, "furlong")


def test_format_distance():
    assert format_distance(72.0, "in") == "1.00 in"


def test_set_result_diagonal_uses_pythagoras():
    state = MeasureState()
    state.set_result(page_index=0, start_pdf=(0, 0), end_pdf=(3, 4))

    assert state.last_distance_pt() == pytest.approx(5.0)
    assert state.last_distance_pt() == pytest.approx(math.hypot(3, 4))
