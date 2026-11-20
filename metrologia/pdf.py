"""Geração do relatório em PDF com ReportLab (estrutura da aula 02).

Componentes: SimpleDocTemplate (página Carta + margens), ParagraphStyle
(fontes/cores/entrelinhas) e Table/TableStyle (grade, fundos condicionais).

O PDF é um *relatório de apoio* do MVP. Não reproduz o timbre, a numeração
nem a assinatura do Certificado de Calibração oficial da Schulz.
"""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .calculos import FORA, ResultadoCalibracao
from .validacao import desenho_qr

VERDE = colors.HexColor("#C6F6D5")   # parecer aprovado (slide "Design do relatório")
VERMELHO = colors.HexColor("#FED7D7")  # parecer reprovado
CABECALHO = colors.HexColor("#1F3864")
LINHA_FORA = colors.HexColor("#FFF5F5")


def fmt(valor, casas: int) -> str:
    """Número com vírgula decimal (padrão brasileiro)."""
    return f"{valor:.{casas}f}".replace(".", ",")


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontSize=17,
                                 textColor=CABECALHO, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=9,
                              textColor=colors.HexColor("#555555"), spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11,
                             textColor=CABECALHO, spaceBefore=10, spaceAfter=4),
        "txt": ParagraphStyle("txt", parent=base["Normal"], fontSize=9, leading=12),
        "cel": ParagraphStyle("cel", parent=base["Normal"], fontSize=8, leading=10),
        "celh": ParagraphStyle("celh", parent=base["Normal"], fontSize=8, leading=10,
                               textColor=colors.white, fontName="Helvetica-Bold"),
        "parecer": ParagraphStyle("parecer", parent=base["Normal"], fontSize=14,
                                  leading=18, alignment=TA_CENTER,
                                  fontName="Helvetica-Bold"),
        "nota": ParagraphStyle("nota", parent=base["Normal"], fontSize=7.5,
                               textColor=colors.HexColor("#666666"), leading=10),
    }


def gerar_pdf(metadados: dict, resultado: ResultadoCalibracao, *,
              url_validacao: str | None = None, id_registro: str | None = None) -> bytes:
    est = _estilos()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, title="Relatório de cálculo metrológico",
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    )
    p = lambda texto, estilo: Paragraph(escape(str(texto)), est[estilo])  # noqa: E731

    historia = [
        p("Relatório de Cálculo Metrológico", "titulo"),
        p("MVP de automação da emissão de certificados de calibração — "
          "Projeto Aplicado III (Schulz S.A.)", "sub"),
    ]

    # --- identificação ---------------------------------------------------
    rotulos = [("Cliente solicitante", "cliente"), ("Técnico executante", "tecnico"),
               ("Código do instrumento", "codigo"), ("Denominação", "denominacao"),
               ("Fabricante", "fabricante"), ("Data", "data"),
               ("Temperatura ambiente", "temperatura")]
    linhas_id = [[p(rot, "celh"), p(metadados.get(chave) or "—", "cel")]
                 for rot, chave in rotulos]
    tabela_id = Table(linhas_id, colWidths=[1.7 * inch, 5.4 * inch])
    tabela_id.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CABECALHO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    historia += [p("Identificação", "h2"), tabela_id]

    # --- parecer -----------------------------------------------------------
    cor = VERDE if resultado.aprovado else VERMELHO
    banner = Table(
        [[p(f"PARECER FINAL: INSTRUMENTO {resultado.parecer}", "parecer")]],
        colWidths=[7.1 * inch], rowHeights=[0.5 * inch])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cor),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#718096")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    resumo = (f"{resultado.total} pontos avaliados: {resultado.dentro} dentro e "
              f"{resultado.fora} fora da tolerância.")
    historia += [Spacer(1, 10), banner, Spacer(1, 4), p(resumo, "txt")]

    # --- resultados por ponto ---------------------------------------------
    cab = ["Parâmetro", "Nominal", "Tol. +", "Tol. -", "Média", "Erro", "LEA", "Status"]
    dados = [[p(c, "celh") for c in cab]]
    fundo = []
    for i, pt in enumerate(resultado.pontos, start=1):
        dados.append([
            p(pt["parametro"], "cel"),
            p(fmt(pt["nominal"], 3), "cel"),
            p(fmt(pt["tol_mais"], 3), "cel"),
            p(fmt(pt["tol_menos"], 3), "cel"),
            p(fmt(pt["media"], 4), "cel"),
            p(fmt(pt["erro_sistematico"], 4), "cel"),
            p(fmt(pt["lea"], 3), "cel"),
            p(pt["status"], "cel"),
        ])
        if pt["status"] == FORA:
            fundo.append(("BACKGROUND", (0, i), (-1, i), LINHA_FORA))
    tabela = Table(dados, repeatRows=1, colWidths=[
        1.45 * inch, 0.65 * inch, 0.55 * inch, 0.55 * inch,
        0.8 * inch, 0.8 * inch, 0.5 * inch, 1.8 * inch])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CABECALHO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        *fundo,
    ]))
    historia += [p("Resultados por ponto de ensaio (mm)", "h2"), tabela, Spacer(1, 8)]

    historia.append(p(
        "Regras aplicadas: média das leituras; erro sistemático = média - valor "
        "nominal; LEA = |Tol. +| (erro >= 0) ou |Tol. -| (erro < 0); ponto "
        "DENTRO_DA_TOLERANCIA quando |erro| <= LEA (margem de 1e-7 contra "
        "imprecisão de ponto flutuante). Parecer APROVADO somente se todos os "
        "pontos estiverem dentro. Documento de apoio gerado automaticamente; "
        "não substitui o Certificado de Calibração assinado.", "nota"))

    if url_validacao:
        qr = Table([[desenho_qr(url_validacao, 1.1 * inch),
                     [p("Validação de autenticidade", "h2"),
                      p("Aponte a câmera do celular para o QR Code para conferir, na página "
                        "pública da plataforma, o parecer registrado para este processamento.", "txt"),
                      p(f"Registro: {id_registro or '—'}", "nota")]]],
                   colWidths=[1.3 * inch, 5.8 * inch])
        qr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0"))]))
        historia += [Spacer(1, 8), qr]

    doc.build(historia)
    return buffer.getvalue()
