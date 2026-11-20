"""Armazenamento do histórico de processamentos.

Dois backends com a mesma interface:
    RepositorioMemoria   desenvolvimento local e testes
    RepositorioDynamoDB  nuvem (AWS), dentro da camada gratuita

Modelagem no DynamoDB (uma tabela, chaves pk/sk):
    pk = "PROC"        sk = <id>        item de RESUMO (pequeno)  -> listagem
    pk = "DET#<id>"    sk = "DADOS"     item de DETALHE (JSON)    -> tela e PDF

O resumo é separado do detalhe de propósito: o DynamoDB cobra leitura pelo
tamanho do item lido, mesmo com ProjectionExpression. Listar 50 resumos custa
poucas unidades de leitura; listar 50 detalhes estouraria a cota provisionada.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from typing import Protocol

from .registro import resumo_de


class Repositorio(Protocol):
    def salvar(self, registro: dict) -> None: ...
    def obter(self, rid: str) -> dict | None: ...
    def listar(self, limite: int) -> list[dict]: ...


class RepositorioMemoria:
    def __init__(self, maximo: int = 50):
        self._dados: "OrderedDict[str, dict]" = OrderedDict()
        self._maximo = maximo

    def salvar(self, registro: dict) -> None:
        self._dados[registro["id"]] = json.loads(json.dumps(registro))   # cópia isolada
        while len(self._dados) > self._maximo:
            self._dados.popitem(last=False)

    def obter(self, rid: str) -> dict | None:
        reg = self._dados.get(rid)
        return json.loads(json.dumps(reg)) if reg else None

    def listar(self, limite: int) -> list[dict]:
        resumos = [resumo_de(r) for r in self._dados.values()]
        return sorted(resumos, key=lambda r: r["id"], reverse=True)[:limite]


class RepositorioDynamoDB:
    PK_LISTA = "PROC"

    def __init__(self, tabela: str, recurso=None):
        if recurso is None:
            import boto3   # já vem no runtime do Lambda; só é importado se usado
            recurso = boto3.resource("dynamodb")
        self._tabela = recurso.Table(tabela)

    def salvar(self, registro: dict) -> None:
        rid = registro["id"]
        # 1º o detalhe, depois o resumo: o resumo nunca aponta para um detalhe inexistente.
        self._tabela.put_item(Item={
            "pk": f"DET#{rid}", "sk": "DADOS",
            "dados": json.dumps(registro, ensure_ascii=False),
        })
        resumo = {k: v for k, v in resumo_de(registro).items() if v is not None}
        self._tabela.put_item(
            Item={"pk": self.PK_LISTA, "sk": rid, **resumo},
            ConditionExpression="attribute_not_exists(sk)",
        )

    def obter(self, rid: str) -> dict | None:
        resposta = self._tabela.get_item(Key={"pk": f"DET#{rid}", "sk": "DADOS"})
        item = resposta.get("Item")
        return json.loads(item["dados"]) if item else None

    def listar(self, limite: int) -> list[dict]:
        from boto3.dynamodb.conditions import Key
        resposta = self._tabela.query(
            KeyConditionExpression=Key("pk").eq(self.PK_LISTA),
            ScanIndexForward=False,      # mais recentes primeiro (sk começa pela data UTC)
            Limit=limite,
        )
        resumos = []
        for item in resposta["Items"]:
            resumo = {k: item.get(k) for k in resumo_de({}).keys()}
            resumo["id"] = item["sk"]
            for campo in ("total", "dentro", "fora"):       # Decimal -> int
                if resumo[campo] is not None:
                    resumo[campo] = int(resumo[campo])
            resumos.append(resumo)
        return resumos


def criar_repositorio(config) -> Repositorio:
    if config.armazenamento == "dynamodb":
        return RepositorioDynamoDB(config.tabela)
    return RepositorioMemoria(config.max_historico)
