"""Teste de fumaca da plataforma publicada (ou rodando localmente).

    python deploy/smoke_test.py https://xxxx.lambda-url.us-east-1.on.aws SUA_SENHA

Verifica: saude, bloqueio sem login, login, envio de planilha de exemplo,
pagina de detalhe, PDF e painel. Usa apenas a biblioteca padrao.
"""
from __future__ import annotations

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

EXEMPLO = Path(__file__).resolve().parent.parent / "exemplos" / "exemplo_aprovado.xlsx"


class SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def main(base: str, senha: str) -> int:
    base = base.rstrip("/")
    jar = http.cookiejar.CookieJar()
    abrir = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), SemRedirecionar()).open
    falhas = 0

    def verificar(nome, ok, detalhe=""):
        nonlocal falhas
        print(f"[{'OK' if ok else 'FALHOU'}] {nome} {detalhe}")
        falhas += 0 if ok else 1

    def req(url, dados=None, cabecalhos=None):
        try:
            r = abrir(urllib.request.Request(url, data=dados, headers=cabecalhos or {}), timeout=40)
            return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    s, _, corpo = req(f"{base}/health")
    verificar("saude publica", s == 200 and b'"ok"' in corpo, f"(HTTP {s})")

    s, h, _ = req(f"{base}/")
    verificar("painel exige login", s == 302 and "/login" in h.get("Location", ""), f"(HTTP {s})")

    s, _, _ = req(f"{base}/login", urllib.parse.urlencode({"senha": "senha-errada-xx"}).encode())
    verificar("senha errada recusada", s == 401, f"(HTTP {s})")

    s, _, _ = req(f"{base}/login", urllib.parse.urlencode({"senha": senha}).encode())
    verificar("login correto", s == 302 and len(list(jar)) > 0, f"(HTTP {s})")

    if not EXEMPLO.exists():
        print(f"Planilha de exemplo ausente: {EXEMPLO}")
        return 1
    limite = uuid.uuid4().hex
    corpo_mp = (f"--{limite}\r\nContent-Disposition: form-data; name=\"planilha\"; filename=\"{EXEMPLO.name}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + EXEMPLO.read_bytes() + f"\r\n--{limite}--\r\n".encode()
    s, h, _ = req(f"{base}/processar", corpo_mp, {"Content-Type": f"multipart/form-data; boundary={limite}"})
    destino = h.get("Location", "")
    verificar("envio da planilha", s == 302 and "/processamentos/" in destino, f"(HTTP {s})")
    if "/processamentos/" not in destino:
        return 1

    s, _, html = req(base + destino if destino.startswith("/") else destino)
    verificar("detalhe com parecer", s == 200 and (b"APROVADO" in html or b"REPROVADO" in html), f"(HTTP {s})")

    rid = re.search(r"/processamentos/(.+)$", destino).group(1)
    s, h, pdf = req(f"{base}/pdf/{rid}")
    verificar("PDF gerado", s == 200 and pdf.startswith(b"%PDF"), f"(HTTP {s}, {len(pdf)} bytes)")

    s, _, html = req(f"{base}/")
    verificar("historico no painel", s == 200 and EXEMPLO.name.encode() in html, f"(HTTP {s})")

    print("\nTudo certo." if not falhas else f"\n{falhas} verificacao(oes) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
