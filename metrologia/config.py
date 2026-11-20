"""Configuração da aplicação, lida de variáveis de ambiente.

Local (desenvolvimento): nada é obrigatório. Sem senha, o login fica desligado e
os dados ficam em memória.
Nuvem (AWS Lambda): senha, chave de sessão e tabela do DynamoDB são obrigatórias;
se faltar algo, a aplicação se recusa a subir em vez de abrir sem proteção.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field

LIMITE_UPLOAD_BYTES = 4 * 1024 * 1024   # o corpo de uma Function URL vai a ~6 MB em base64
MAX_HISTORICO = 50


class ConfigError(RuntimeError):
    """Configuração insegura ou incompleta para o ambiente em que roda."""


@dataclass
class Config:
    senha: str | None = None
    secret_key: str = field(default_factory=lambda: secrets.token_hex(32))
    armazenamento: str = "memoria"          # "memoria" | "dynamodb"
    tabela: str | None = None
    em_nuvem: bool = False
    max_historico: int = MAX_HISTORICO
    base_url: str | None = None             # endereço público para o QR Code (opcional)

    @property
    def auth_ativa(self) -> bool:
        return bool(self.senha)

    def validar(self) -> "Config":
        if self.armazenamento not in ("memoria", "dynamodb"):
            raise ConfigError(f"STORAGE_BACKEND inválido: {self.armazenamento!r}")
        if self.armazenamento == "dynamodb" and not self.tabela:
            raise ConfigError("STORAGE_BACKEND=dynamodb exige TABLE_NAME.")
        if self.em_nuvem:
            if not self.senha:
                raise ConfigError("APP_PASSWORD não definido: recusando subir sem login na nuvem.")
            if len(self.senha) < 12:
                raise ConfigError("APP_PASSWORD deve ter ao menos 12 caracteres.")
            if "SECRET_KEY" not in os.environ or len(os.environ["SECRET_KEY"]) < 32:
                raise ConfigError("SECRET_KEY ausente ou curta (mínimo 32 caracteres).")
            if self.armazenamento != "dynamodb":
                raise ConfigError("Na nuvem o armazenamento deve ser dynamodb (a memória se perde entre execuções).")
        return self

    @classmethod
    def do_ambiente(cls) -> "Config":
        env = os.environ
        cfg = cls(
            senha=env.get("APP_PASSWORD") or None,
            armazenamento=env.get("STORAGE_BACKEND", "memoria").lower(),
            tabela=env.get("TABLE_NAME") or None,
            em_nuvem=bool(env.get("AWS_LAMBDA_FUNCTION_NAME")),
            base_url=(env.get("PUBLIC_BASE_URL") or "").rstrip("/") or None,
        )
        if env.get("SECRET_KEY"):
            cfg.secret_key = env["SECRET_KEY"]
        return cfg.validar()
