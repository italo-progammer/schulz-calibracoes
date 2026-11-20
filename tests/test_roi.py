import math
from scripts.calcular_roi import Premissas, resumo


def test_formula_do_roteiro_com_numeros_redondos():
    p = Premissas(certificados_ano=120, min_manual=25, min_auto=2, custo_hora=60, investimento=1000, custo_operacao_ano=0)
    assert math.isclose(p.horas_economizadas(), 46.0)
    assert math.isclose(p.economia_bruta(), 2760.0)
    assert math.isclose(p.roi_pct(), (2760 - 1000) / 1000 * 100)       # 176 %
    assert math.isclose(p.payback_meses(), 1000 / (2760 / 12))


def test_custo_de_operacao_reduz_a_economia_liquida():
    p = Premissas(certificados_ano=120, custo_operacao_ano=500)
    assert math.isclose(p.economia_liquida(), p.economia_bruta() - 500)


def test_economia_zero_nao_tem_payback():
    p = Premissas(min_manual=2, min_auto=2)
    assert p.payback_meses() == float("inf")


def test_volume_vem_do_certificado_00091():
    assert math.isclose(Premissas().certificados_ano, 91 / 238 * 365)
    assert 139 < resumo(Premissas())["certificados_ano"] < 141
