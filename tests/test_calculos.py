"""Testes das regras de negócio (roteiro AV03, Item 1)."""
import json

import pandas as pd
import pytest

from metrologia.calculos import (APROVADO, DENTRO, FORA, REPROVADO,
                                 SemPontosError, calcular)


def _df(*linhas):
    """linhas: (parametro, nominal, tol_mais, tol_menos, [leituras])"""
    return pd.DataFrame([
        {"parametro": p, "nominal": n, "tol_mais": tp, "tol_menos": tm,
         "leituras": ls, "media_planilha": None}
        for p, n, tp, tm, ls in linhas])


def _ponto(res, nome):
    return next(p for p in res.pontos if p["parametro"] == nome)


def test_media_das_leituras():
    res = calcular(_df(("A", 10.0, 0.1, -0.1, [10.02, 10.04, 10.06])))
    assert _ponto(res, "A")["media"] == pytest.approx(10.04)


def test_erro_sistematico_e_media_menos_padrao():
    res = calcular(_df(("A", 10.0, 0.1, -0.1, [9.98, 9.96])))
    assert _ponto(res, "A")["erro_sistematico"] == pytest.approx(-0.03)
    assert _ponto(res, "A")["erro_absoluto"] == pytest.approx(0.03)


def test_ponto_dentro_e_fora_da_tolerancia():
    res = calcular(_df(("OK", 10.0, 0.05, -0.05, [10.01]),
                       ("RUIM", 10.0, 0.05, -0.05, [10.2])))
    assert _ponto(res, "OK")["status"] == DENTRO
    assert _ponto(res, "RUIM")["status"] == FORA


def test_parecer_aprovado_quando_todos_dentro():
    res = calcular(_df(("A", 1.0, 0.1, -0.1, [1.01]), ("B", 2.0, 0.1, -0.1, [1.95])))
    assert (res.parecer, res.aprovado, res.fora) == (APROVADO, True, 0)


def test_parecer_reprovado_se_um_ponto_fora():
    res = calcular(_df(("A", 1.0, 0.1, -0.1, [1.01]), ("B", 2.0, 0.1, -0.1, [2.5])))
    assert res.parecer == REPROVADO and not res.aprovado
    assert res.pontos_fora == ["B"] and (res.dentro, res.fora) == (1, 1)


def test_limite_exato_nao_reprova_por_ponto_flutuante():
    # Nominal do diâmetro real (16,964) com medida exatamente no limite superior:
    # 16,974 - 16,964 = 0,010000000000001563 em float, ligeiramente acima de 0,01.
    assert abs(16.974 - 16.964) > 0.01   # prova de que a armadilha existe
    res = calcular(_df(("D", 16.964, 0.01, -0.01, [16.974])))
    assert _ponto(res, "D")["status"] == DENTRO


def test_sem_a_margem_o_mesmo_caso_seria_reprovado():
    # Documenta por que a margem de 1e-7 existe: sem ela o ponto sairia FORA.
    assert not (abs(16.974 - 16.964) <= 0.01)


def test_pouco_acima_do_limite_reprova():
    res = calcular(_df(("D", 6.075, 0.01, -0.01, [6.0851])))   # erro 0,0101
    assert _ponto(res, "D")["status"] == FORA


def test_tolerancia_assimetrica_usa_lado_correto():
    # Tol. +0,1 / 0,0: erro negativo (abaixo do nominal) está FORA.
    abaixo = calcular(_df(("P", 0.0, 0.1, 0.0, [-0.05])))
    acima = calcular(_df(("P", 0.0, 0.1, 0.0, [0.05])))
    assert _ponto(abaixo, "P")["status"] == FORA
    assert _ponto(acima, "P")["status"] == DENTRO


def test_erro_negativo_infimo_por_float_nao_reprova():
    res = calcular(_df(("P", 0.0, 0.1, 0.0, [-1e-9])))
    assert _ponto(res, "P")["status"] == DENTRO


def test_limites_min_max_batem_com_a_aula():
    p = _ponto(calcular(_df(("D", 6.075, 0.01, -0.01, [6.075]))), "D")
    assert p["limite_min"] == pytest.approx(6.065)
    assert p["limite_max"] == pytest.approx(6.085)


def test_desvio_padrao_amostral():
    p = _ponto(calcular(_df(("A", 0.0, 1, -1, [0.002167, 0.002267]))), "A")
    assert p["desvio_padrao"] == pytest.approx(7.0710678e-05, rel=1e-6)
    assert _ponto(calcular(_df(("B", 0.0, 1, -1, [0.5]))), "B")["desvio_padrao"] == 0.0


def test_sem_pontos_levanta_erro():
    with pytest.raises(SemPontosError):
        calcular(_df())


def test_resultado_e_serializavel_em_json():
    res = calcular(_df(("A", 1.0, 0.1, -0.1, [1.01, 1.02])))
    assert json.loads(json.dumps(res.para_dict()))["parecer"] == APROVADO
