"""Registro de um processamento: o que é guardado e como volta a virar resultado.

O registro é um dicionário simples (serializável em JSON). Isso permite guardá-lo
tanto em memória quanto no DynamoDB sem conversão de tipos numéricos.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .calculos import APROVADO, ResultadoCalibracao
from .leitura import Planilha

CAMPOS_RESUMO = ("id", "criado_em", "arquivo", "cliente", "codigo", "denominacao",
                 "parecer", "total", "dentro", "fora")


def novo_id() -> str:
    """Ordenável por data (UTC) e único: serve de chave de ordenação no DynamoDB."""
    agora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"{agora}-{uuid.uuid4().hex[:8]}"


def criar_registro(arquivo: str, planilha: Planilha, resultado: ResultadoCalibracao) -> dict:
    meta = planilha.metadados
    rid = novo_id()
    return {
        "id": rid,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arquivo": (arquivo or "planilha.xlsx")[:120],
        "cliente": meta.get("cliente"),
        "codigo": meta.get("codigo"),
        "denominacao": meta.get("denominacao"),
        "metadados": dict(meta),
        "aba": planilha.aba,
        "linha_cabecalho": planilha.linha_cabecalho,
        "descartadas": list(planilha.descartadas),
        "parecer": resultado.parecer,
        "total": resultado.total,
        "dentro": resultado.dentro,
        "fora": resultado.fora,
        "parametros_fora": list(resultado.pontos_fora),
        "pontos": resultado.pontos,
    }


def resumo_de(registro: dict) -> dict:
    return {k: registro.get(k) for k in CAMPOS_RESUMO}


def resultado_de(registro: dict) -> ResultadoCalibracao:
    """Reconstrói o objeto de resultado (usado para gerar o PDF de um registro salvo)."""
    return ResultadoCalibracao(
        pontos=registro["pontos"], total=registro["total"], dentro=registro["dentro"],
        fora=registro["fora"], parecer=registro["parecer"],
        pontos_fora=registro["parametros_fora"],
    )


def indicadores(resumos: list[dict]) -> dict:
    total = len(resumos)
    aprovados = sum(1 for r in resumos if r["parecer"] == APROVADO)
    return {
        "total": total,
        "aprovados": aprovados,
        "reprovados": total - aprovados,
        "taxa_aprovacao": round(100 * aprovados / total, 1) if total else None,
        "pontos_fora": sum(int(r["fora"] or 0) for r in resumos),
    }
