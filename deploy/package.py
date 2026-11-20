"""Monta build/package/ com o codigo e as dependencias para o AWS Lambda.

Roda em Windows, macOS ou Linux: o pip baixa as rodas binarias para Linux x86_64
(o ambiente do Lambda), independentemente do sistema de quem executa.

    python deploy/package.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "build" / "package"
LIMITE_MB = 250          # limite do Lambda para o pacote descompactado

ARQUIVOS = ["app.py", "lambda_handler.py"]
PASTAS = ["metrologia", "templates", "static"]
IGNORAR = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".pytest_cache")
PODAR = ["tests", "__pycache__"]


def tamanho_mb(pasta: Path) -> float:
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) / 1024 / 1024


def main() -> int:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)

    print("1/3 Instalando dependencias (Linux x86_64, Python 3.12)...")
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-r", str(RAIZ / "deploy" / "requirements-lambda.txt"),
        "--target", str(DESTINO), "--platform", "manylinux2014_x86_64",
        "--only-binary=:all:", "--python-version", "3.12", "--implementation", "cp",
        "--upgrade", "--quiet", "--disable-pip-version-check",
    ], check=True)

    print("2/3 Copiando o codigo da aplicacao...")
    for nome in ARQUIVOS:
        shutil.copy2(RAIZ / nome, DESTINO / nome)
    for nome in PASTAS:
        shutil.copytree(RAIZ / nome, DESTINO / nome, ignore=IGNORAR)

    print("3/3 Removendo arquivos desnecessarios...")
    for alvo in PODAR:
        for caminho in DESTINO.rglob(alvo):
            if caminho.is_dir() and caminho.parent != DESTINO / "metrologia":
                shutil.rmtree(caminho, ignore_errors=True)

    tam = tamanho_mb(DESTINO)
    print(f"Pacote pronto em {DESTINO.relative_to(RAIZ)} ({tam:.0f} MB; limite {LIMITE_MB} MB).")
    if tam > LIMITE_MB:
        print("ERRO: pacote acima do limite do Lambda.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
