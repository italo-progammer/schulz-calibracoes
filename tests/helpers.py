"""Gerador de planilhas sintéticas com o layout da aba 'Registro' da Schulz.

Os valores são inventados (nada vem de dados reais da empresa), mas a
estrutura reproduz o que a planilha real tem: metadados com rótulos,
cabeçalho na linha 29, colunas auxiliares repetindo 'tol+'/'tol-', linhas
em branco com #VALUE!, bloco de incerteza e observações, e opcionalmente
resíduos numéricos de rodapé.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

from openpyxl import Workbook

# nome, nominal, tol+, tol-, leituras...
PONTOS_APROVADO = [
    ("DIAMETRO_A", 10.000, 0.010, -0.010, 10.004, 10.006),
    ("DIAMETRO_B", 25.400, 0.020, -0.020, 25.395, 25.399),
    ("PLANICIDADE", 0.000, 0.050, 0.000, 0.012, 0.014),
    ("POSICAO_1", 0.000, 0.100, 0.000, 0.040, 0.042),
]
PONTOS_REPROVADO = PONTOS_APROVADO[:3] + [
    ("POSICAO_1", 0.000, 0.100, 0.000, 0.250, 0.260),   # fora: 0,255 > 0,1
]

_PADRAO_PARA_STRICT = {
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main":
        "http://purl.oclc.org/ooxml/spreadsheetml/main",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships":
        "http://purl.oclc.org/ooxml/officeDocument/relationships",
    "http://schemas.openxmlformats.org/drawingml/2006/main":
        "http://purl.oclc.org/ooxml/drawingml/main",
}


def criar_xlsx(caminho, pontos, *, linhas_topo_extra: int = 0,
               residuos_antes_da_incerteza: bool = False,
               virgula_decimal_texto: bool = False,
               cliente: str = "Setor de Teste", codigo: str = "TESTE-001") -> None:
    """Escreve um .xlsx (formato padrão) no caminho informado."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Registro"
    off = linhas_topo_extra

    ws["C1"] = "Registro - Calibração de Instrumento (fixture sintética)"
    ws[f"B{5+off}"], ws[f"C{5+off}"] = "Data:", datetime(2026, 1, 15, 9, 30)
    ws[f"G{5+off}"], ws[f"H{5+off}"] = "Temperatura ambiente:", "20,1°"
    ws[f"B{7+off}"], ws[f"C{7+off}"] = "Cliente solicitante:", cliente
    ws[f"G{7+off}"] = "OS:"                       # rótulo sem valor, como na real
    ws[f"B{9+off}"], ws[f"C{9+off}"] = "Técnico executante:", "Técnico de Teste"
    ws[f"B{18+off}"], ws[f"C{18+off}"] = "Código:", codigo
    ws[f"B{20+off}"], ws[f"C{20+off}"] = "Denominação:", "Instrumento de teste"
    ws[f"B{24+off}"], ws[f"C{24+off}"] = "Fabricante:", "Não consta"

    cab = 29 + off
    titulos = {"B": "Parâmetro avaliado", "C": "Valor nominal", "D": "Tol. +",
               "E": "Tol. -", "F": "Medida 1", "G": "Medida 2", "H": "Média",
               "I": "Desvio padrão", "K": "ABS do valor nominal",
               "L": "tol+", "M": "tol-"}
    for col, texto in titulos.items():
        ws[f"{col}{cab}"] = texto

    linha = cab + 1
    for nome, nominal, tp, tm, m1, m2 in pontos:
        ws[f"B{linha}"], ws[f"C{linha}"] = nome, nominal
        ws[f"D{linha}"], ws[f"E{linha}"] = tp, tm
        if virgula_decimal_texto:
            ws[f"F{linha}"], ws[f"G{linha}"] = str(m1).replace(".", ","), str(m2).replace(".", ",")
        else:
            ws[f"F{linha}"], ws[f"G{linha}"] = m1, m2
        ws[f"H{linha}"] = (m1 + m2) / 2          # valor em cache, como no Excel
        ws[f"K{linha}"], ws[f"L{linha}"] = abs(nominal), "Rep"
        linha += 1

    if residuos_antes_da_incerteza:
        ws[f"B{linha}"], ws[f"C{linha}"] = 2, 16.9698       # resíduo numérico
        linha += 1
        ws[f"B{linha}"] = "Nota sem números"                # texto sem medidas
        linha += 1

    for _ in range(5):                                      # linhas "vazias" da real
        for col in "BCDEFGHIK":
            ws[f"{col}{linha}"] = " "
        ws[f"L{linha}"], ws[f"M{linha}"] = "#VALUE!", "#VALUE!"
        linha += 1

    ws[f"C{linha+1}"], ws[f"D{linha+1}"] = "Incerteza de medição:", 0.002
    ws[f"A{linha+4}"] = "Observações:"
    ws[f"B{linha+12}"], ws[f"C{linha+12}"] = 2, 16.9698     # resíduo pós-tabela
    wb.save(caminho)


def converter_para_strict(origem, destino) -> None:
    """Regrava o .xlsx com namespaces Strict (reproduz a falha do arquivo real)."""
    with zipfile.ZipFile(origem) as zin, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            dados = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                texto = dados.decode("utf-8")
                for padrao, strict in _PADRAO_PARA_STRICT.items():
                    texto = texto.replace(padrao, strict)
                if item.filename == "xl/workbook.xml":
                    texto = texto.replace("<workbook ", '<workbook conformance="strict" ', 1)
                dados = texto.encode("utf-8")
            zout.writestr(item, dados)


def xlsx_em_bytes(pontos, *, estrito=False, **kwargs) -> bytes:
    """Atalho para testes: devolve o conteúdo do .xlsx em bytes."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as pasta:
        base = Path(pasta) / "base.xlsx"
        criar_xlsx(base, pontos, **kwargs)
        if estrito:
            saida = Path(pasta) / "strict.xlsx"
            converter_para_strict(base, saida)
            return saida.read_bytes()
        return base.read_bytes()


def planilha_em_branco_bytes() -> bytes:
    """Modelo com cabeçalho, mas sem nenhuma linha de dados."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Registro"
    for col, texto in {"B": "Parâmetro avaliado", "C": "Valor nominal", "D": "Tol. +",
                       "E": "Tol. -", "F": "Medida 1", "G": "Medida 2"}.items():
        ws[f"{col}29"] = texto
    for linha in range(30, 40):
        ws[f"B{linha}"] = " "
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
