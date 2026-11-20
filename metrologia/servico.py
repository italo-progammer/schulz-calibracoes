"""Camada de serviço: orquestra ingestão -> cálculo (sem depender do Flask).

Mantida separada da interface web de propósito: a mesma função pode ser
chamada por uma rota Flask, por testes ou por uma função serverless (o
desenho do Tema 02 prevê Lambda para esta etapa).
"""
from __future__ import annotations

from .calculos import ResultadoCalibracao, calcular
from .leitura import Planilha, ler_planilha


def analisar(origem) -> tuple[Planilha, ResultadoCalibracao]:
    planilha = ler_planilha(origem)
    resultado = calcular(planilha.pontos)
    return planilha, resultado
