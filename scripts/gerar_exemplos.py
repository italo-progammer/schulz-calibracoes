"""Gera planilhas de exemplo (sintéticas) em exemplos/ para testar a aplicação.

    python scripts/gerar_exemplos.py
"""
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.helpers import (PONTOS_APROVADO, PONTOS_REPROVADO,  # noqa: E402
                           converter_para_strict, criar_xlsx)

saida = RAIZ / "exemplos"
saida.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory() as tmp:
    for nome, pontos in (("exemplo_aprovado", PONTOS_APROVADO),
                         ("exemplo_reprovado", PONTOS_REPROVADO)):
        base = Path(tmp) / f"{nome}.xlsx"
        criar_xlsx(base, pontos)
        converter_para_strict(base, saida / f"{nome}.xlsx")  # formato Strict, como o real
        print("gerado:", saida / f"{nome}.xlsx")
