"""Testes ponta a ponta da aplicação web (cliente de teste do Flask)."""
import io
import re

import pytest

from app import create_app
from metrologia.config import Config
from tests.helpers import (PONTOS_APROVADO, PONTOS_REPROVADO,
                           planilha_em_branco_bytes, xlsx_em_bytes)


@pytest.fixture()
def cliente():
    app = create_app(Config())          # local: memória e sem login
    app.config["TESTING"] = True
    return app.test_client()


def _envia(cliente, conteudo, nome="planilha.xlsx", rota="/processar"):
    return cliente.post(rota, data={"planilha": (io.BytesIO(conteudo), nome)},
                        content_type="multipart/form-data", follow_redirects=True)


def test_pagina_de_nova_analise_tem_formulario_de_upload(cliente):
    r = cliente.get("/novo")
    assert r.status_code == 200
    assert b'type="file"' in r.data and b"Processar planilha" in r.data


def test_fluxo_completo_aprovado(cliente):
    r = _envia(cliente, xlsx_em_bytes(PONTOS_APROVADO, estrito=True))
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "APROVADO" in html and "REPROVADO" not in html
    assert "DIAMETRO_A" in html and "DENTRO_DA_TOLERANCIA" in html
    assert "4 de 4 pontos dentro da tolerância" in html


def test_fluxo_completo_reprovado_lista_ponto_fora(cliente):
    r = _envia(cliente, xlsx_em_bytes(PONTOS_REPROVADO))
    html = r.get_data(as_text=True)
    assert "REPROVADO" in html and "FORA_DA_TOLERANCIA" in html
    assert "fora: POSICAO_1" in html


def test_pdf_do_processamento(cliente):
    html = _envia(cliente, xlsx_em_bytes(PONTOS_REPROVADO)).get_data(as_text=True)
    rid = re.search(r"/pdf/([0-9A-Za-z-]+)", html).group(1)
    r = cliente.get(f"/pdf/{rid}")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF") and len(r.data) > 2000


def test_pdf_inexistente_retorna_404(cliente):
    assert cliente.get("/pdf/inexistente-123").status_code == 404


def test_extensao_invalida_retorna_400(cliente):
    r = _envia(cliente, b"a;b\n1;2", nome="dados.csv")
    assert r.status_code == 400 and "Formato não suportado" in r.get_data(as_text=True)


def test_sem_arquivo_retorna_400(cliente):
    assert cliente.post("/processar", data={}).status_code == 400


def test_planilha_em_branco_retorna_422_com_mensagem(cliente):
    r = _envia(cliente, planilha_em_branco_bytes())
    assert r.status_code == 422 and "modelo em branco" in r.get_data(as_text=True)


def test_arquivo_corrompido_retorna_422(cliente):
    assert _envia(cliente, b"lixo", nome="x.xlsx").status_code == 422


def test_api_json(cliente):
    r = _envia(cliente, xlsx_em_bytes(PONTOS_REPROVADO), rota="/api/processar")
    corpo = r.get_json()
    assert r.status_code == 200
    assert corpo["parecer"] == "REPROVADO" and corpo["parametros_fora"] == ["POSICAO_1"]
    assert corpo["total_pontos"] == 4 and corpo["metadados"]["codigo"] == "TESTE-001"


def test_api_erro_em_json(cliente):
    r = _envia(cliente, planilha_em_branco_bytes(), rota="/api/processar")
    assert r.status_code == 422 and "erro" in r.get_json()


def test_html_escapa_conteudo_da_planilha(cliente):
    malicioso = xlsx_em_bytes(PONTOS_APROVADO, cliente="<script>alert(1)</script>")
    html = _envia(cliente, malicioso).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
