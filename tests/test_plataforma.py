"""Painel, histórico, detalhe e login da plataforma (cliente de teste do Flask)."""
import io
import re

import pytest

from app import create_app
from metrologia.config import Config
from tests.helpers import PONTOS_APROVADO, PONTOS_REPROVADO, xlsx_em_bytes

SENHA = "senha-de-teste-123"


def _envia(c, conteudo, nome="p.xlsx", **kw):
    return c.post("/processar", data={"planilha": (io.BytesIO(conteudo), nome)},
                  content_type="multipart/form-data", **kw)


@pytest.fixture()
def aberto():
    app = create_app(Config())
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def protegido():
    app = create_app(Config(senha=SENHA, secret_key="x" * 40))
    app.config["TESTING"] = True
    return app.test_client()


def test_painel_vazio(aberto):
    html = aberto.get("/").get_data(as_text=True)
    assert "Nenhum processamento ainda" in html and "Taxa de aprovação" in html


def test_processar_redireciona_para_o_detalhe(aberto):
    r = _envia(aberto, xlsx_em_bytes(PONTOS_APROVADO))
    assert r.status_code == 302 and "/processamentos/" in r.headers["Location"]


def test_painel_lista_e_calcula_indicadores(aberto):
    _envia(aberto, xlsx_em_bytes(PONTOS_APROVADO), nome="ok.xlsx")
    _envia(aberto, xlsx_em_bytes(PONTOS_REPROVADO), nome="ruim.xlsx")
    _envia(aberto, xlsx_em_bytes(PONTOS_REPROVADO), nome="ruim2.xlsx")
    html = aberto.get("/").get_data(as_text=True)
    assert html.index("ruim2.xlsx") < html.index("ruim.xlsx") < html.index("ok.xlsx")   # recentes primeiro
    assert re.search(r'indicador__valor">3<', html)                                      # total
    assert "33,3%" in html                                                               # 1 de 3 aprovado
    assert "1 de 4" in html and "TESTE-001" in html


def test_detalhe_mostra_resultado_salvo_e_link_do_pdf(aberto):
    r = _envia(aberto, xlsx_em_bytes(PONTOS_REPROVADO), follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "REPROVADO" in html and "fora: POSICAO_1" in html and "ruim" not in html
    rid = re.search(r"/pdf/([0-9A-Za-z-]+)", html).group(1)
    assert aberto.get(f"/processamentos/{rid}").status_code == 200
    assert aberto.get(f"/pdf/{rid}").data.startswith(b"%PDF")


def test_detalhe_inexistente_e_404_amigavel(aberto):
    r = aberto.get("/processamentos/nao-existe")
    assert r.status_code == 404 and "não encontrado" in r.get_data(as_text=True)


def test_erro_de_upload_mantem_a_pagina_de_nova_analise(aberto):
    r = _envia(aberto, b"lixo", nome="x.xlsx")
    assert r.status_code == 422 and 'type="file"' in r.get_data(as_text=True)


def test_arquivo_acima_do_limite_retorna_413(aberto):
    grande = b"0" * (4 * 1024 * 1024 + 10)
    r = _envia(aberto, grande, nome="g.xlsx")
    assert r.status_code == 413 and "4 MB" in r.get_data(as_text=True)


def test_health_e_publico_e_nao_vaza_dados(protegido):
    r = protegido.get("/health")
    assert r.status_code == 200 and r.get_json() == {"status": "ok", "armazenamento": "memoria"}


# ------------------------------------------------------------------- login
@pytest.mark.parametrize("caminho", ["/", "/novo", "/processamentos/x", "/pdf/x"])
def test_paginas_exigem_login(protegido, caminho):
    r = protegido.get(caminho)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_processar_sem_login_nao_grava(protegido):
    r = _envia(protegido, xlsx_em_bytes(PONTOS_APROVADO))
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    protegido.post("/login", data={"senha": SENHA})
    assert "Nenhum processamento ainda" in protegido.get("/").get_data(as_text=True)


def test_api_sem_login_retorna_401_json(protegido):
    r = protegido.post("/api/processar", data={})
    assert r.status_code == 401 and "erro" in r.get_json()


def test_senha_errada_nao_entra(protegido):
    r = protegido.post("/login", data={"senha": "errada"})
    assert r.status_code == 401 and "Senha incorreta" in r.get_data(as_text=True)
    assert protegido.get("/").status_code == 302


def test_senha_certa_entra_e_volta_ao_destino(protegido):
    r = protegido.post("/login", data={"senha": SENHA, "next": "/novo"})
    assert r.status_code == 302 and r.headers["Location"] == "/novo"
    assert protegido.get("/novo").status_code == 200


@pytest.mark.parametrize("destino", ["https://evil.example", "//evil.example", "/\\evil.example"])
def test_login_nao_redireciona_para_fora(protegido, destino):
    r = protegido.post("/login", data={"senha": SENHA, "next": destino})
    assert r.headers["Location"] == "/"


def test_logout_encerra_a_sessao(protegido):
    protegido.post("/login", data={"senha": SENHA})
    assert protegido.get("/").status_code == 200
    protegido.post("/logout")
    assert protegido.get("/").status_code == 302


def test_cabecalhos_de_seguranca(aberto):
    h = aberto.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert h["Cache-Control"] == "no-store"


def test_cookie_de_sessao_httponly(protegido):
    r = protegido.post("/login", data={"senha": SENHA})
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
