"""Simula o AWS Lambda recebendo eventos HTTP no formato de uma Function URL (payload v2).

Usa o handler real (apig-wsgi + Flask) e um DynamoDB simulado (moto). Cobre o que o
deploy exige e que os testes do Flask não cobrem: upload multipart em base64, cookie
de sessão em `cookies`, PDF binário em base64 e persistência no DynamoDB.
"""
import base64
import importlib
import json
import re
from urllib.parse import urlencode

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
pytest.importorskip("apig_wsgi")
from urllib3.filepost import encode_multipart_formdata  # noqa: E402

from tests.helpers import PONTOS_APROVADO, PONTOS_REPROVADO, xlsx_em_bytes  # noqa: E402

SENHA = "senha-bem-longa-123"
HOST = "abc123.lambda-url.us-east-1.on.aws"


@pytest.fixture()
def handler(monkeypatch):
    for chave, valor in {
        "AWS_ACCESS_KEY_ID": "teste", "AWS_SECRET_ACCESS_KEY": "teste", "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_LAMBDA_FUNCTION_NAME": "calibracoes", "APP_PASSWORD": SENHA, "SECRET_KEY": "s" * 48,
        "STORAGE_BACKEND": "dynamodb", "TABLE_NAME": "tabela-teste",
    }.items():
        monkeypatch.setenv(chave, valor)
    with moto.mock_aws():
        boto3.resource("dynamodb").create_table(
            TableName="tabela-teste", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}])
        import lambda_handler
        yield importlib.reload(lambda_handler).handler


def _evento(metodo, caminho, *, corpo=b"", tipo=None, cookies=None, query=""):
    headers = {"host": HOST, "x-forwarded-proto": "https", "x-forwarded-for": "203.0.113.9"}
    if tipo:
        headers["content-type"] = tipo
    binario = bool(corpo) and not (tipo or "").startswith("application/x-www-form-urlencoded")
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": caminho, "rawQueryString": query,
        "cookies": cookies or [], "headers": headers,
        "requestContext": {"accountId": "anonymous", "apiId": "abc123", "domainName": HOST,
                           "domainPrefix": "abc123", "requestId": "r1", "routeKey": "$default", "stage": "$default",
                           "time": "02/Nov/2026:10:00:00 +0000", "timeEpoch": 1793613600000,
                           "http": {"method": metodo, "path": caminho, "protocol": "HTTP/1.1",
                                    "sourceIp": "203.0.113.9", "userAgent": "teste"}},
        "body": (base64.b64encode(corpo).decode() if binario else corpo.decode()) if corpo else None,
        "isBase64Encoded": binario,
    }


def _login(handler, senha=SENHA):
    corpo = urlencode({"senha": senha}).encode()
    return handler(_evento("POST", "/login", corpo=corpo, tipo="application/x-www-form-urlencoded"), None)


def _cookie(resposta):
    return [c.split(";")[0] for c in resposta.get("cookies", [])]


def _upload(handler, pontos, cookies):
    corpo, tipo = encode_multipart_formdata({"planilha": ("planilha.xlsx", xlsx_em_bytes(pontos, estrito=True),
                                                         "application/octet-stream")})
    return handler(_evento("POST", "/processar", corpo=corpo, tipo=tipo, cookies=cookies), None)


def test_health_publico(handler):
    r = handler(_evento("GET", "/health"), None)
    assert r["statusCode"] == 200 and json.loads(r["body"]) == {"status": "ok", "armazenamento": "dynamodb"}


def test_sem_login_redireciona_para_login(handler):
    r = handler(_evento("GET", "/"), None)
    assert r["statusCode"] == 302 and r["headers"]["location"].startswith("/login")


def test_senha_errada(handler):
    assert _login(handler, "errada")["statusCode"] == 401


def test_login_devolve_cookie_seguro(handler):
    r = _login(handler)
    assert r["statusCode"] == 302
    bruto = r["cookies"][0]
    assert bruto.startswith("session=") and "HttpOnly" in bruto and "Secure" in bruto


def test_fluxo_completo_na_nuvem_simulada(handler):
    cookies = _cookie(_login(handler))
    assert handler(_evento("GET", "/", cookies=cookies), None)["statusCode"] == 200

    enviado = _upload(handler, PONTOS_REPROVADO, cookies)
    assert enviado["statusCode"] == 302
    destino = enviado["headers"]["location"]
    rid = re.search(r"/processamentos/(.+)$", destino).group(1)

    detalhe = handler(_evento("GET", destino, cookies=cookies), None)
    assert detalhe["statusCode"] == 200
    assert "REPROVADO" in detalhe["body"] and "POSICAO_1" in detalhe["body"]

    pdf = handler(_evento("GET", f"/pdf/{rid}", cookies=cookies), None)
    assert pdf["statusCode"] == 200 and pdf["isBase64Encoded"] is True
    assert base64.b64decode(pdf["body"]).startswith(b"%PDF")
    assert pdf["headers"]["content-type"] == "application/pdf"

    painel = handler(_evento("GET", "/", cookies=cookies), None)
    assert "planilha.xlsx" in painel["body"] and "REPROVADO" in painel["body"]


def test_historico_persiste_entre_invocacoes(handler):
    cookies = _cookie(_login(handler))
    _upload(handler, PONTOS_APROVADO, cookies)
    _upload(handler, PONTOS_REPROVADO, cookies)
    painel = handler(_evento("GET", "/", cookies=cookies), None)["body"]
    assert painel.count("planilha.xlsx") == 2 and re.search(r'indicador__valor">2<', painel)


def test_api_json_com_sessao(handler):
    cookies = _cookie(_login(handler))
    corpo, tipo = encode_multipart_formdata({"planilha": ("p.xlsx", xlsx_em_bytes(PONTOS_APROVADO), "x")})
    r = handler(_evento("POST", "/api/processar", corpo=corpo, tipo=tipo, cookies=cookies), None)
    dados = json.loads(r["body"])
    assert r["statusCode"] == 200 and dados["parecer"] == "APROVADO" and dados["id"]


def test_sem_sessao_nada_e_gravado(handler):
    assert _upload(handler, PONTOS_APROVADO, [])["statusCode"] == 302
    cookies = _cookie(_login(handler))
    assert "Nenhum processamento ainda" in handler(_evento("GET", "/", cookies=cookies), None)["body"]


def test_arquivos_estaticos_sem_login(handler):
    r = handler(_evento("GET", "/static/style.css"), None)
    assert r["statusCode"] == 200 and "--azul" in r["body"]


def test_funcao_recusa_subir_sem_senha(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "f")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    import lambda_handler
    from metrologia.config import ConfigError
    with pytest.raises(ConfigError):
        importlib.reload(lambda_handler)
