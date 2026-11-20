"""Regras de negócio e cálculos metrológicos (roteiro AV03, Item 1).

Para cada ponto de ensaio:
    média das leituras      = soma(leituras) / n
    erro sistemático        = média - valor padrão (nominal)
    LEA (limite admissível) = |Tol. +| se o erro é >= 0, senão |Tol. -|
    validação por ponto     = |erro| <= LEA   ->  DENTRO_DA_TOLERANCIA
                                                  FORA_DA_TOLERANCIA
Parecer final: APROVADO se todos os pontos estão dentro; senão REPROVADO.

Por que o LEA depende do sinal do erro: as tolerâncias da planilha podem ser
assimétricas (ex.: +0,1 / 0,0). Comparar |erro| com um único LEA aceitaria
erros negativos que a planilha considera fora. Com tolerâncias simétricas o
critério é idêntico a |erro| <= LEA. Equivale aos limites da aula:
[nominal - |Tol. -|, nominal + |Tol. +|].
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Margem contra imprecisão de ponto flutuante (slide "Lógica de decisão").
# Exemplo verificado: 16,974 - 16,964 = 0,010000000000001563 em float, acima do
# limite de 0,01 embora a medida esteja exatamente no limite; não pode reprovar.
TOLERANCIA_FLOAT = 1e-7

DENTRO = "DENTRO_DA_TOLERANCIA"
FORA = "FORA_DA_TOLERANCIA"
APROVADO = "APROVADO"
REPROVADO = "REPROVADO"


class SemPontosError(ValueError):
    """Não há pontos de ensaio para calcular."""


@dataclass
class ResultadoCalibracao:
    pontos: list[dict]
    total: int
    dentro: int
    fora: int
    parecer: str
    pontos_fora: list[str]

    @property
    def aprovado(self) -> bool:
        return self.parecer == APROVADO

    def para_dict(self) -> dict:
        return {
            "parecer": self.parecer,
            "total_pontos": self.total,
            "pontos_dentro": self.dentro,
            "pontos_fora": self.fora,
            "parametros_fora": self.pontos_fora,
            "pontos": self.pontos,
        }


def _desvio_padrao(leituras: list[float]) -> float:
    return statistics.stdev(leituras) if len(leituras) >= 2 else 0.0


def calcular(pontos: pd.DataFrame) -> ResultadoCalibracao:
    """Aplica média, erro sistemático, validação por ponto e parecer final."""
    if pontos is None or len(pontos) == 0:
        raise SemPontosError("Nenhum ponto de ensaio para calcular.")

    df = pontos.copy()
    df["n_leituras"] = df["leituras"].apply(len)
    df["media"] = df["leituras"].apply(lambda xs: sum(xs) / len(xs))
    df["desvio_padrao"] = df["leituras"].apply(_desvio_padrao)

    df["erro_sistematico"] = df["media"] - df["nominal"]
    df["erro_absoluto"] = df["erro_sistematico"].abs()

    df["lea_sup"] = df["tol_mais"].abs()
    df["lea_inf"] = df["tol_menos"].abs()
    df["lea"] = np.where(df["erro_sistematico"] >= 0, df["lea_sup"], df["lea_inf"])
    df["limite_min"] = df["nominal"] - df["lea_inf"]
    df["limite_max"] = df["nominal"] + df["lea_sup"]

    df["dentro"] = df["erro_absoluto"] <= df["lea"] + TOLERANCIA_FLOAT
    df["status"] = np.where(df["dentro"], DENTRO, FORA)

    registros = df.drop(columns=["leituras", "media_planilha"], errors="ignore")
    registros = registros.assign(leituras=df["leituras"]).to_dict("records")
    fora = df.loc[~df["dentro"], "parametro"].tolist()

    return ResultadoCalibracao(
        pontos=registros,
        total=len(df),
        dentro=int(df["dentro"].sum()),
        fora=len(fora),
        parecer=APROVADO if not fora else REPROVADO,
        pontos_fora=fora,
    )
