"""Testes do histórico: mesmo contrato nos dois backends (memória e DynamoDB simulado)."""
import time

import pytest

from metrologia.registro import criar_registro, indicadores, novo_id, resultado_de
from metrologia.repositorio import RepositorioMemoria
from metrologia.servico import analisar
from tests.helpers import PONTOS_APROVADO, PONTOS_REPROVADO, xlsx_em_bytes


def _registro(pontos, nome="a.xlsx"):
    planilha, resultado = analisar(xlsx_em_bytes(pontos))
    return criar_registro(nome, planilha, resultado)


@pytest.fixture(params=["memoria", "dynamodb"])
def repo(request, monkeypatch):
    if request.param == "memoria":
        yield RepositorioMemoria(maximo=50)
        return
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    for chave, valor in {"AWS_ACCESS_KEY_ID": "teste", "AWS_SECRET_ACCESS_KEY": "teste",
                         "AWS_DEFAULT_REGION": "us-east-1"}.items():
        monkeypatch.setenv(chave, valor)
    from metrologia.repositorio import RepositorioDynamoDB
    with moto.mock_aws():
        recurso = boto3.resource("dynamodb")
        recurso.create_table(
            TableName="t", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}])
        yield RepositorioDynamoDB("t", recurso)


def test_salvar_e_obter_preserva_o_registro_inteiro(repo):
    reg = _registro(PONTOS_REPROVADO)
    repo.salvar(reg)
    lido = repo.obter(reg["id"])
    assert lido["parecer"] == "REPROVADO" and lido["parametros_fora"] == ["POSICAO_1"]
    assert lido["pontos"] == reg["pontos"]                       # floats idênticos
    assert lido["metadados"]["codigo"] == "TESTE-001"


def test_obter_inexistente_devolve_none(repo):
    assert repo.obter("nao-existe") is None


def test_listar_mais_recentes_primeiro_e_com_limite(repo):
    ids = []
    for pontos in (PONTOS_APROVADO, PONTOS_REPROVADO, PONTOS_APROVADO):
        reg = _registro(pontos)
        repo.salvar(reg)
        ids.append(reg["id"])
        time.sleep(0.002)
    listados = repo.listar(50)
    assert [r["id"] for r in listados] == ids[::-1]
    assert len(repo.listar(2)) == 2


def test_listar_devolve_so_resumo_com_tipos_python(repo):
    repo.salvar(_registro(PONTOS_REPROVADO))
    resumo = repo.listar(10)[0]
    assert "pontos" not in resumo                                  # detalhe fica fora da listagem
    assert (resumo["total"], resumo["dentro"], resumo["fora"]) == (4, 3, 1)
    assert all(isinstance(resumo[c], int) for c in ("total", "dentro", "fora"))


def test_resultado_reconstruido_serve_para_gerar_pdf(repo):
    from metrologia.pdf import gerar_pdf
    reg = _registro(PONTOS_REPROVADO)
    repo.salvar(reg)
    lido = repo.obter(reg["id"])
    assert gerar_pdf(lido["metadados"], resultado_de(lido)).startswith(b"%PDF")


def test_memoria_descarta_os_mais_antigos():
    repo = RepositorioMemoria(maximo=2)
    ids = []
    for _ in range(3):
        reg = _registro(PONTOS_APROVADO)
        repo.salvar(reg)
        ids.append(reg["id"])
        time.sleep(0.002)
    assert repo.obter(ids[0]) is None and repo.obter(ids[2]) is not None


def test_ids_sao_unicos_e_ordenaveis_por_data():
    ids = [novo_id() for _ in range(200)]
    assert len(set(ids)) == 200
    assert ids[0][:8].isdigit() and "T" in ids[0]


def test_indicadores():
    assert indicadores([]) == {"total": 0, "aprovados": 0, "reprovados": 0,
                               "taxa_aprovacao": None, "pontos_fora": 0}
    resumos = [{"parecer": "APROVADO", "fora": 0}, {"parecer": "REPROVADO", "fora": 2},
               {"parecer": "APROVADO", "fora": 0}]
    assert indicadores(resumos) == {"total": 3, "aprovados": 2, "reprovados": 1,
                                    "taxa_aprovacao": 66.7, "pontos_fora": 2}
