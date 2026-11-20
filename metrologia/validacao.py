"""Validação de autenticidade por QR Code.

O QR Code impresso no PDF aponta para /validar/<id>?t=<token>. O token é um HMAC
do id com a chave secreta da aplicação: quem não tem o PDF não consegue adivinhar
endereços de outros processamentos. A página pública mostra só o mínimo necessário
(parecer, instrumento, data e contagem de pontos); medições e cliente ficam atrás do login.
"""
from __future__ import annotations

import hashlib
import hmac

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

TAMANHO_TOKEN = 24


def gerar_token(chave: str, rid: str) -> str:
    return hmac.new(chave.encode("utf-8"), rid.encode("utf-8"), hashlib.sha256).hexdigest()[:TAMANHO_TOKEN]


def token_valido(chave: str, rid: str, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(gerar_token(chave, rid), token)


def desenho_qr(url: str, lado: float) -> Drawing:
    """QR Code vetorial (ReportLab) com `lado` pontos de aresta, nível de correção M."""
    widget = QrCodeWidget(url, barLevel="M", barBorder=2)
    x0, y0, x1, y1 = widget.getBounds()
    desenho = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    desenho.add(widget)
    return desenho

