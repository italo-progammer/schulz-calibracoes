"""Ingestão: leitura e saneamento das planilhas .xlsx de calibração.

Fluxo (conforme a aula 02):
    1. repair_xlsx_stream()  -> corrige o formato "Strict OpenXML" em memória;
    2. pandas.read_excel()   -> carrega todas as abas sem cabeçalho fixo;
    3. localização dinâmica  -> acha a linha do cabeçalho ("Parâmetro ...");
    4. extração/filtragem    -> descarta linhas vazias, erros de fórmula e rodapés.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

# Planilhas salvas pelo Excel no modo "Strict Open XML" usam URIs diferentes
# das do modo padrão (Transitional). O openpyxl só entende as do modo padrão.
NAMESPACES_STRICT_PARA_PADRAO = {
    "http://purl.oclc.org/ooxml/spreadsheetml/main":
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/officeDocument/relationships":
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/sharedTypes":
        "http://schemas.openxmlformats.org/officeDocument/2006/sharedTypes",
    "http://purl.oclc.org/ooxml/drawingml/main":
        "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/drawingml/spreadsheetDrawing":
        "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "http://purl.oclc.org/ooxml/drawingml/chart":
        "http://schemas.openxmlformats.org/drawingml/2006/chart",
}

# rótulo (normalizado, sem ":") -> chave do metadado
ROTULOS_METADADOS = {
    "cliente solicitante": "cliente",
    "tecnico executante": "tecnico",
    "codigo": "codigo",
    "denominacao": "denominacao",
    "fabricante": "fabricante",
    "data": "data",
    "temperatura ambiente": "temperatura",
}


class PlanilhaInvalida(ValueError):
    """Planilha fora do layout esperado. A mensagem é voltada ao usuário."""


@dataclass
class Planilha:
    aba: str
    linha_cabecalho: int  # número da linha no Excel (base 1)
    metadados: dict
    pontos: pd.DataFrame
    descartadas: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------
# 1) Correção do formato Strict OpenXML
# --------------------------------------------------------------------------
def _bytes_de(origem) -> bytes:
    if isinstance(origem, (bytes, bytearray)):
        return bytes(origem)
    if hasattr(origem, "read"):
        return origem.read()
    with open(origem, "rb") as arquivo:
        return arquivo.read()


def repair_xlsx_stream(origem) -> io.BytesIO:
    """Reescreve os XMLs internos do .xlsx trocando namespaces Strict por padrão.

    Trabalha inteiramente em memória (io.BytesIO) e devolve um objeto limpo,
    pronto para o pandas. Arquivos que já estão no formato padrão passam
    inalterados.
    """
    bruto = _bytes_de(origem)
    try:
        entrada = zipfile.ZipFile(io.BytesIO(bruto))
    except zipfile.BadZipFile as exc:
        raise PlanilhaInvalida(
            "O arquivo enviado não é um .xlsx válido (estrutura ZIP inválida)."
        ) from exc

    saida = io.BytesIO()
    with entrada, zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for item in entrada.infolist():
            dados = entrada.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                texto = dados.decode("utf-8")
                for strict, padrao in NAMESPACES_STRICT_PARA_PADRAO.items():
                    texto = texto.replace(strict, padrao)
                texto = texto.replace(' conformance="strict"', "")
                dados = texto.encode("utf-8")
            destino.writestr(item, dados)
    saida.seek(0)
    return saida


# --------------------------------------------------------------------------
# 2) Utilitários de normalização
# --------------------------------------------------------------------------
def _norm(valor) -> str:
    """Texto minúsculo, sem acentos e sem espaços repetidos ('' para vazio)."""
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def _para_numero(valor) -> float | None:
    """Converte para float aceitando vírgula decimal e '°'; erros -> None."""
    if valor is None or isinstance(valor, (bool, np.bool_)):
        return None
    if isinstance(valor, (int, float, np.integer, np.floating)):
        numero = float(valor)
        return None if np.isnan(numero) else numero
    if isinstance(valor, str):
        texto = valor.strip().replace("°", "").replace(" ", "")
        if not texto or texto.startswith("#"):
            return None
        try:
            return float(texto.replace(",", "."))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# 3) Localização dinâmica do cabeçalho e extração
# --------------------------------------------------------------------------
def _localizar_tabela(df: pd.DataFrame):
    """Acha a linha que começa com 'Parâmetro' e mapeia as colunas pelo nome."""
    for i in range(len(df)):
        textos = [_norm(c) for c in df.iloc[i].tolist()]
        if not any(t.startswith("parametro") for t in textos):
            continue
        colunas: dict[str, int] = {}
        medidas: list[int] = []
        for j, texto in enumerate(textos):
            if not texto:
                continue
            compacto = texto.replace(" ", "").replace(".", "")
            # só vale a primeira ocorrência (colunas auxiliares repetem 'tol+')
            if texto.startswith("parametro"):
                colunas.setdefault("parametro", j)
            elif texto == "valor nominal":
                colunas.setdefault("nominal", j)
            elif compacto == "tol+":
                colunas.setdefault("tol_mais", j)
            elif compacto == "tol-":
                colunas.setdefault("tol_menos", j)
            elif texto.startswith("medida"):
                medidas.append(j)
            elif texto == "media":
                colunas.setdefault("media_planilha", j)
        obrigatorias = {"parametro", "nominal", "tol_mais", "tol_menos"}
        if obrigatorias <= colunas.keys() and medidas:
            return i, colunas, medidas
    return None


def _extrair_pontos(df, inicio, colunas, medidas):
    pontos, descartadas = [], []
    for i in range(inicio + 1, len(df)):
        linha = df.iloc[i].tolist()
        textos = [_norm(c) for c in linha]
        # fim da tabela: seção de incerteza ou observações
        if any(t.startswith(("incerteza", "observac")) for t in textos if t):
            break

        celula = linha[colunas["parametro"]]
        nome = celula.strip() if isinstance(celula, str) else ""
        tem_conteudo = any(t and not t.startswith("#") for t in textos)

        if not nome:
            if tem_conteudo:
                descartadas.append({
                    "linha": i + 1, "parametro": _norm(celula) or "(vazio)",
                    "motivo": "sem nome de parâmetro (resíduo de rodapé)"})
            continue  # linha totalmente vazia

        nominal = _para_numero(linha[colunas["nominal"]])
        tol_mais = _para_numero(linha[colunas["tol_mais"]])
        tol_menos = _para_numero(linha[colunas["tol_menos"]])
        leituras = [x for x in (_para_numero(linha[j]) for j in medidas)
                    if x is not None]

        if None in (nominal, tol_mais, tol_menos):
            descartadas.append({"linha": i + 1, "parametro": nome,
                                "motivo": "nominal ou tolerâncias ausentes/inválidos"})
            continue
        if not leituras:
            descartadas.append({"linha": i + 1, "parametro": nome,
                                "motivo": "nenhuma leitura numérica"})
            continue

        media_planilha = None
        if "media_planilha" in colunas:
            media_planilha = _para_numero(linha[colunas["media_planilha"]])

        pontos.append({
            "linha": i + 1, "parametro": nome, "nominal": nominal,
            "tol_mais": tol_mais, "tol_menos": tol_menos,
            "leituras": leituras, "media_planilha": media_planilha,
        })
    return pontos, descartadas


def _formatar_metadado(chave: str, valor) -> str:
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor).strip()
    return texto


def _extrair_metadados(df: pd.DataFrame, limite_linha: int) -> dict:
    """Busca por palavra-chave: valor = 1ª célula preenchida à direita do rótulo."""
    meta = {chave: None for chave in ROTULOS_METADADOS.values()}
    for i in range(min(limite_linha, len(df))):
        linha = df.iloc[i].tolist()
        for j, celula in enumerate(linha):
            if not isinstance(celula, str):
                continue
            chave = ROTULOS_METADADOS.get(_norm(celula).rstrip(":").strip())
            if chave is None or meta[chave] is not None:
                continue
            for candidato in linha[j + 1:]:
                texto = _norm(candidato)
                if texto and not texto.endswith(":"):
                    meta[chave] = _formatar_metadado(chave, candidato)
                    break
    return meta


# --------------------------------------------------------------------------
# 4) API pública
# --------------------------------------------------------------------------
def ler_planilha(origem) -> Planilha:
    """Lê o .xlsx (bytes, caminho ou arquivo) e devolve metadados + pontos."""
    buffer = repair_xlsx_stream(origem)
    try:
        abas = pd.read_excel(buffer, sheet_name=None, header=None, engine="openpyxl")
    except Exception as exc:  # arquivo corrompido, senha, etc.
        raise PlanilhaInvalida(
            f"Não foi possível abrir a planilha ({type(exc).__name__})."
        ) from exc
    if not abas:
        raise PlanilhaInvalida("A planilha não possui nenhuma aba legível.")

    for nome_aba, df in abas.items():
        achado = _localizar_tabela(df)
        if achado is None:
            continue
        cabecalho, colunas, medidas = achado
        pontos, descartadas = _extrair_pontos(df, cabecalho, colunas, medidas)
        if not pontos:
            raise PlanilhaInvalida(
                f"A aba '{nome_aba}' tem o cabeçalho de resultados, mas nenhuma "
                "linha com nominal, tolerâncias e leituras preenchidos "
                "(parece um modelo em branco)."
            )
        return Planilha(
            aba=nome_aba,
            linha_cabecalho=cabecalho + 1,
            metadados=_extrair_metadados(df, cabecalho),
            pontos=pd.DataFrame(pontos),
            descartadas=descartadas,
        )

    raise PlanilhaInvalida(
        "Não encontrei a tabela de resultados. Esperado um cabeçalho com "
        "'Parâmetro avaliado', 'Valor nominal', 'Tol. +', 'Tol. -' e "
        "'Medida 1' (e demais medidas)."
    )
