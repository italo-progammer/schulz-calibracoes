"""Validação de autenticidade por QR Code: token, página pública e QR no PDF."""
import io
import re
from urllib.parse import parse_qs, urlparse

import pytest

from app import create_app
from metrologia.config import Config
from metrologia.validacao import desenho_qr, gerar_token, token_valido
from tests.helpers import PONTOS_APROVADO, PONTOS_REPROVADO, xlsx_em_bytes

SENHA = "senha-de-teste-123"


def _cliente(**cfg):
    app = create_app(Config(secret_key="k" * 40, **cfg))
    app.config["TESTING"] = True
    return app.test_client()


def _envia(c, pontos):
    r = c.post("/processar", data={"planilha": (io.BytesIO(xlsx_em_bytes(pontos)), "p.xlsx")},
               content_type="multipart/form-data")
    return re.search(r"/processamentos/(.+)$", r.headers["Location"]).group(1)


def _url_do_qr(c, rid):
    """Pega o link que o app embute no QR (mesma função usada no PDF)."""
    html = c.get(f"/processamentos/{rid}").get_data(as_text=True)
    return re.search(r'href="([^"]*/validar/[^"]+)"', html).group(1).replace("&amp;", "&")


def test_token_e_deterministico_e_depende_da_chave_e_do_id():
    assert gerar_token("a" * 32, "id1") == gerar_token("a" * 32, "id1")
    assert gerar_token("a" * 32, "id1") != gerar_token("a" * 32, "id2")
    assert gerar_token("a" * 32, "id1") != gerar_token("b" * 32, "id1")


def test_token_invalido_ou_ausente_e_recusado():
    t = gerar_token("k" * 32, "id1")
    assert token_valido("k" * 32, "id1", t)
    assert not token_valido("k" * 32, "id1", None)
    assert not token_valido("k" * 32, "id1", "")
    assert not token_valido("k" * 32, "id1", t[:-1] + ("0" if t[-1] != "0" else "1"))
    assert not token_valido("k" * 32, "outro", t)


def test_qr_vira_desenho_com_o_tamanho_pedido():
    d = desenho_qr("https://exemplo.com/validar/abc?t=123", 80)
    assert (d.width, d.height) == (80, 80)


@pytest.mark.parametrize("pontos,parecer", [(PONTOS_APROVADO, "APROVADO"), (PONTOS_REPROVADO, "REPROVADO")])
def test_pagina_de_validacao_mostra_o_parecer(pontos, parecer):
    c = _cliente()
    url = _url_do_qr(c, _envia(c, pontos))
    r = c.get(urlparse(url).path + "?" + urlparse(url).query)
    assert r.status_code == 200 and parecer in r.get_data(as_text=True)


def test_pagina_publica_nao_expoe_medicoes_nem_cliente():
    c = _cliente()
    url = _url_do_qr(c, _envia(c, PONTOS_REPROVADO))
    html = c.get(urlparse(url).path + "?" + urlparse(url).query).get_data(as_text=True)
    assert "Setor de Teste" not in html          # cliente solicitante
    assert "POSICAO_1" not in html and "Média" not in html


def test_token_errado_ou_id_inexistente_respondem_igual_404():
    c = _cliente()
    rid = _envia(c, PONTOS_APROVADO)
    ruim = c.get(f"/validar/{rid}?t=deadbeef")
    sem = c.get(f"/validar/{rid}")
    inexistente = c.get(f"/validar/nao-existe?t={gerar_token('k' * 40, 'nao-existe')}")
    assert ruim.status_code == sem.status_code == inexistente.status_code == 404
    assert ruim.get_data() == sem.get_data() == inexistente.get_data()


def test_validacao_funciona_sem_login_mas_o_detalhe_continua_protegido():
    c = _cliente(senha=SENHA)
    c.post("/login", data={"senha": SENHA})
    rid = _envia(c, PONTOS_APROVADO)
    url = _url_do_qr(c, rid)
    anonimo = _cliente(senha=SENHA).get  # outro cliente, outra sessão (e outra chave: token não vale)
    assert anonimo(f"/processamentos/{rid}").status_code == 302
    c.post("/logout")
    r = c.get(urlparse(url).path + "?" + urlparse(url).query)
    assert r.status_code == 200 and "APROVADO" in r.get_data(as_text=True)
    assert c.get(f"/processamentos/{rid}").status_code == 302


def test_pdf_contem_qr_e_o_link_aponta_para_a_base_publica():
    c = _cliente(base_url="https://schulz.exemplo.com.br")
    rid = _envia(c, PONTOS_APROVADO)
    url = _url_do_qr(c, rid)
    assert url.startswith("https://schulz.exemplo.com.br/validar/")
    assert parse_qs(urlparse(url).query)["t"][0] == gerar_token("k" * 40, rid)
    pdf = c.get(f"/pdf/{rid}")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_pdf_com_qr_e_maior_que_sem_qr():
    from metrologia.pdf import gerar_pdf
    from metrologia.servico import analisar
    planilha, resultado = analisar(xlsx_em_bytes(PONTOS_APROVADO))
    com = gerar_pdf(planilha.metadados, resultado, url_validacao="https://x.com/validar/a?t=b", id_registro="a")
    sem = gerar_pdf(planilha.metadados, resultado)
    assert len(com) > len(sem)
