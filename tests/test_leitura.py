"""Testes de ingestão: formato Strict, cabeçalho dinâmico e filtros."""
import io
import warnings

import pytest
from openpyxl import load_workbook

from metrologia.leitura import PlanilhaInvalida, ler_planilha, repair_xlsx_stream
from tests.helpers import (PONTOS_APROVADO, planilha_em_branco_bytes,
                           xlsx_em_bytes)


def test_arquivo_strict_quebra_o_leitor_padrao_mas_nao_o_nosso():
    estrito = xlsx_em_bytes(PONTOS_APROVADO, estrito=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            abas_sem_reparo = load_workbook(io.BytesIO(estrito)).sheetnames
        except Exception:
            abas_sem_reparo = []
    assert abas_sem_reparo == []                      # a falha é reproduzida
    reparado = load_workbook(repair_xlsx_stream(estrito)).sheetnames
    assert reparado == ["Registro"]                   # e corrigida pelo módulo


def test_arquivo_padrao_passa_inalterado():
    padrao = xlsx_em_bytes(PONTOS_APROVADO)
    assert load_workbook(repair_xlsx_stream(padrao)).sheetnames == ["Registro"]


def test_le_pontos_e_metadados_do_arquivo_strict():
    pl = ler_planilha(xlsx_em_bytes(PONTOS_APROVADO, estrito=True))
    assert pl.aba == "Registro" and pl.linha_cabecalho == 29
    assert list(pl.pontos["parametro"]) == [p[0] for p in PONTOS_APROVADO]
    assert pl.metadados == {
        "cliente": "Setor de Teste", "tecnico": "Técnico de Teste",
        "codigo": "TESTE-001", "denominacao": "Instrumento de teste",
        "fabricante": "Não consta", "data": "15/01/2026", "temperatura": "20,1°"}


def test_cabecalho_dinamico_em_layout_deslocado():
    pl = ler_planilha(xlsx_em_bytes(PONTOS_APROVADO, linhas_topo_extra=7))
    assert pl.linha_cabecalho == 36
    assert len(pl.pontos) == len(PONTOS_APROVADO)
    assert pl.metadados["codigo"] == "TESTE-001"


def test_ignora_colunas_auxiliares_tol_repetidas():
    pl = ler_planilha(xlsx_em_bytes(PONTOS_APROVADO))
    primeiro = pl.pontos.iloc[0]
    assert (primeiro["tol_mais"], primeiro["tol_menos"]) == (0.010, -0.010)


def test_descarta_residuos_e_linhas_vazias_com_erro_de_formula():
    pl = ler_planilha(xlsx_em_bytes(PONTOS_APROVADO, residuos_antes_da_incerteza=True))
    assert len(pl.pontos) == len(PONTOS_APROVADO)       # só os pontos reais
    motivos = {d["motivo"] for d in pl.descartadas}
    assert any("resíduo" in m for m in motivos)
    assert any("nenhuma leitura" in m or "ausentes" in m for m in motivos)


def test_aceita_virgula_decimal_em_texto():
    pl = ler_planilha(xlsx_em_bytes(PONTOS_APROVADO, virgula_decimal_texto=True))
    assert pl.pontos.iloc[0]["leituras"] == [10.004, 10.006]


def test_media_da_planilha_e_capturada_para_conferencia():
    pl = ler_planilha(xlsx_em_bytes(PONTOS_APROVADO))
    assert pl.pontos.iloc[0]["media_planilha"] == pytest.approx(10.005)


def test_modelo_em_branco_gera_mensagem_clara():
    with pytest.raises(PlanilhaInvalida, match="modelo em branco"):
        ler_planilha(planilha_em_branco_bytes())


def test_arquivo_que_nao_e_xlsx():
    with pytest.raises(PlanilhaInvalida, match="não é um .xlsx válido"):
        ler_planilha(b"isto nao e um zip")


def test_planilha_sem_tabela_de_resultados():
    from openpyxl import Workbook
    wb = Workbook()
    wb.active["A1"] = "qualquer coisa"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(PlanilhaInvalida, match="Não encontrei a tabela"):
        ler_planilha(buf.getvalue())
