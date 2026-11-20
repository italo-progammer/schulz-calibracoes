"""Teste de regressão com a planilha REAL da Schulz (opcional, não versionada).

Os arquivos reais contêm dados internos da empresa e não ficam no repositório.
Para rodar localmente:
    SCHULZ_XLSX=/caminho/planilha_real.xlsx pytest tests/test_planilha_real.py -v
"""
import os

import pytest

from metrologia.servico import analisar

CAMINHO = os.environ.get("SCHULZ_XLSX")
pytestmark = pytest.mark.skipif(not CAMINHO, reason="defina SCHULZ_XLSX para rodar")


def test_planilha_real_le_14_pontos_e_media_confere_com_o_excel():
    planilha, resultado = analisar(CAMINHO)
    assert resultado.total == 14
    for _, linha in planilha.pontos.iterrows():
        assert sum(linha["leituras"]) / len(linha["leituras"]) == pytest.approx(
            linha["media_planilha"], abs=1e-12)


def test_planilha_real_parecer_conforme_regras_do_roteiro():
    _, resultado = analisar(CAMINHO)
    assert (resultado.dentro, resultado.fora) == (8, 6)
    assert resultado.parecer == "REPROVADO"
    assert all("POSIÇÃO" in nome for nome in resultado.pontos_fora)
