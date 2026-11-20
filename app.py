"""Plataforma web de gestão de calibrações (Flask).

Páginas
    GET  /                       painel: indicadores e histórico recente
    GET  /novo                   formulário de envio da planilha
    POST /processar              processa, grava o histórico e redireciona ao detalhe
    GET  /processamentos/<id>    resultado e parecer de um processamento salvo
    GET  /pdf/<id>               relatório em PDF
    GET  /login  POST /login     acesso por senha        POST /logout
API / operação
    POST /api/processar          mesma lógica, resposta em JSON (exige login)
    GET  /health                 verificação de saúde (pública, sem dados sensíveis)
    GET  /validar/<id>?t=<token> validação pública pelo QR Code (só parecer e instrumento)

Local: roda em memória e sem login (ver metrologia/config.py).
Nuvem: roda no AWS Lambda por lambda_handler.py, com DynamoDB e login obrigatório.
"""
from __future__ import annotations

import hmac
import io
from datetime import datetime, timedelta, timezone

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from metrologia.calculos import SemPontosError
from metrologia.config import LIMITE_UPLOAD_BYTES, Config
from metrologia.leitura import PlanilhaInvalida
from metrologia.pdf import fmt, gerar_pdf
from metrologia.registro import criar_registro, indicadores, resultado_de
from metrologia.repositorio import criar_repositorio
from metrologia.servico import analisar
from metrologia.validacao import gerar_token, token_valido

ROTAS_PUBLICAS = {"login", "health", "static", "validar"}

try:
    from zoneinfo import ZoneInfo
    FUSO_BR = ZoneInfo("America/Sao_Paulo")
except Exception:                      # base de fusos ausente: usa UTC-3 fixo
    FUSO_BR = timezone(timedelta(hours=-3))


def data_br(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone(FUSO_BR).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def _destino_seguro(destino: str | None) -> str:
    """Só aceita caminhos internos (evita redirecionamento para sites externos)."""
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return "/"


def create_app(config: Config | None = None, repositorio=None) -> Flask:
    config = config or Config.do_ambiente()
    repo = repositorio or criar_repositorio(config)

    app = Flask(__name__)
    app.secret_key = config.secret_key
    app.config.update(
        MAX_CONTENT_LENGTH=LIMITE_UPLOAD_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.em_nuvem,       # HTTPS garantido pela Function URL
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    app.jinja_env.filters["num"] = fmt
    app.jinja_env.filters["data_br"] = data_br

    def _url_validacao(rid: str) -> str:
        caminho = url_for("validar", rid=rid, t=gerar_token(app.secret_key, rid))
        return (config.base_url + caminho) if config.base_url else request.host_url.rstrip("/") + caminho

    @app.context_processor
    def _contexto():
        return {"auth_ativa": config.auth_ativa, "armazenamento": config.armazenamento,
                "url_validacao": _url_validacao}

    # ------------------------------------------------------------ autenticação
    @app.before_request
    def _exigir_login():
        if not config.auth_ativa or request.endpoint in ROTAS_PUBLICAS or session.get("auth"):
            return None
        if request.path.startswith("/api/"):
            return jsonify(erro="Não autenticado."), 401
        return redirect(url_for("login", next=request.full_path.rstrip("?")))

    @app.after_request
    def _cabecalhos(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint != "static":
            resposta.headers.setdefault("Cache-Control", "no-store")
        return resposta

    @app.route("/login", methods=["GET", "POST"])
    def login():
        destino = _destino_seguro(request.values.get("next"))
        if not config.auth_ativa or session.get("auth"):
            return redirect(destino)
        if request.method == "POST":
            enviada = request.form.get("senha", "").encode("utf-8")
            if hmac.compare_digest(enviada, config.senha.encode("utf-8")):
                session.clear()
                session["auth"] = True
                session.permanent = True
                return redirect(destino)
            return render_template("login.html", erro="Senha incorreta.", destino=destino), 401
        return render_template("login.html", erro=None, destino=destino)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/health")
    def health():
        return jsonify(status="ok", armazenamento=config.armazenamento)

    # ------------------------------------------------------------------ páginas
    def _ler_upload():
        """Valida o envio: (bytes, nome, None) ou (None, None, mensagem_de_erro)."""
        arquivo = request.files.get("planilha")
        if arquivo is None or not arquivo.filename:
            return None, None, "Selecione um arquivo .xlsx para processar."
        if not arquivo.filename.lower().endswith(".xlsx"):
            return None, None, "Formato não suportado: envie um arquivo .xlsx."
        return arquivo.read(), arquivo.filename, None

    @app.get("/")
    def painel():
        resumos = repo.listar(config.max_historico)
        return render_template("painel.html", resumos=resumos, ind=indicadores(resumos),
                               limite=config.max_historico)

    @app.get("/novo")
    def novo():
        return render_template("novo.html", erro=None)

    @app.post("/processar")
    def processar():
        conteudo, nome, erro = _ler_upload()
        if erro:
            return render_template("novo.html", erro=erro), 400
        try:
            planilha, resultado = analisar(conteudo)
        except (PlanilhaInvalida, SemPontosError) as exc:
            return render_template("novo.html", erro=str(exc)), 422
        registro = criar_registro(nome, planilha, resultado)
        repo.salvar(registro)
        return redirect(url_for("detalhe", rid=registro["id"]))

    @app.get("/processamentos/<rid>")
    def detalhe(rid: str):
        registro = repo.obter(rid)
        if registro is None:
            abort(404)
        return render_template("resultado.html", reg=registro,
                               aprovado=registro["parecer"] == "APROVADO")

    @app.get("/pdf/<rid>")
    def pdf(rid: str):
        registro = repo.obter(rid)
        if registro is None:
            abort(404)
        conteudo = gerar_pdf(registro["metadados"], resultado_de(registro),
                             url_validacao=_url_validacao(rid), id_registro=rid)
        return send_file(io.BytesIO(conteudo), mimetype="application/pdf",
                         as_attachment=True, download_name="relatorio_calibracao.pdf")

    @app.get("/validar/<rid>")
    def validar(rid: str):
        """Página pública aberta pelo QR Code: confirma o parecer sem expor medições."""
        registro = repo.obter(rid) if token_valido(app.secret_key, rid, request.args.get("t")) else None
        if registro is None:        # token inválido e id inexistente respondem igual
            return render_template("validar.html", reg=None), 404
        return render_template("validar.html", reg=registro,
                               aprovado=registro["parecer"] == "APROVADO")

    # ---------------------------------------------------------------------- API
    @app.post("/api/processar")
    def api_processar():
        conteudo, nome, erro = _ler_upload()
        if erro:
            return jsonify(erro=erro), 400
        try:
            planilha, resultado = analisar(conteudo)
        except (PlanilhaInvalida, SemPontosError) as exc:
            return jsonify(erro=str(exc)), 422
        registro = criar_registro(nome, planilha, resultado)
        repo.salvar(registro)
        return jsonify(id=registro["id"], metadados=planilha.metadados,
                       linhas_descartadas=planilha.descartadas, **resultado.para_dict())

    # ------------------------------------------------------------------- erros
    def _erro(status: int, mensagem: str):
        if request.path.startswith("/api/"):
            return jsonify(erro=mensagem), status
        return render_template("erro.html", status=status, mensagem=mensagem), status

    @app.errorhandler(404)
    def _nao_encontrado(_):
        return _erro(404, "Página ou processamento não encontrado.")

    @app.errorhandler(413)
    def _arquivo_grande(_):
        if request.path.startswith("/api/"):
            return jsonify(erro="Arquivo acima do limite de 4 MB."), 413
        return render_template("novo.html", erro="Arquivo acima do limite de 4 MB."), 413

    return app


if __name__ == "__main__":
    import os
    create_app().run(debug=False, host=os.environ.get("HOST", "127.0.0.1"),
                     port=int(os.environ.get("PORT", "5000")))
