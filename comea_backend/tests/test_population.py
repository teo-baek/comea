import pytest

import population


def test_default_population_is_zero():
    population.set_current_population(0)
    assert population.get_current_population() == 0


def test_set_and_get_population():
    population.set_current_population(100)
    assert population.get_current_population() == 100
    population.set_current_population(0)  # 테스트 격리 위해 원복


def test_negative_population_rejected():
    with pytest.raises(ValueError):
        population.set_current_population(-1)
