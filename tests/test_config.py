"""A aplicação não pode subir aberta ou mal configurada na nuvem."""
import pytest

from metrologia.config import Config, ConfigError

SENHA = "uma-senha-bem-longa-123"
CHAVE = "k" * 40


def _nuvem(monkeypatch, **extra):
    base = {"AWS_LAMBDA_FUNCTION_NAME": "f", "APP_PASSWORD": SENHA, "SECRET_KEY": CHAVE,
            "STORAGE_BACKEND": "dynamodb", "TABLE_NAME": "t"}
    base.update(extra)
    for chave in ("AWS_LAMBDA_FUNCTION_NAME", "APP_PASSWORD", "SECRET_KEY", "STORAGE_BACKEND", "TABLE_NAME"):
        monkeypatch.delenv(chave, raising=False)
    for chave, valor in base.items():
        if valor is not None:
            monkeypatch.setenv(chave, valor)


def test_local_sem_nada_funciona_sem_login_e_em_memoria(monkeypatch):
    for chave in ("AWS_LAMBDA_FUNCTION_NAME", "APP_PASSWORD", "SECRET_KEY", "STORAGE_BACKEND", "TABLE_NAME"):
        monkeypatch.delenv(chave, raising=False)
    cfg = Config.do_ambiente()
    assert not cfg.auth_ativa and cfg.armazenamento == "memoria" and not cfg.em_nuvem


def test_nuvem_completa_e_valida(monkeypatch):
    _nuvem(monkeypatch)
    cfg = Config.do_ambiente()
    assert cfg.auth_ativa and cfg.em_nuvem and cfg.tabela == "t"


@pytest.mark.parametrize("extra, trecho", [
    ({"APP_PASSWORD": None}, "APP_PASSWORD não definido"),
    ({"APP_PASSWORD": "curta"}, "ao menos 12"),
    ({"SECRET_KEY": None}, "SECRET_KEY"),
    ({"SECRET_KEY": "curta"}, "SECRET_KEY"),
    ({"STORAGE_BACKEND": "memoria"}, "dynamodb"),
    ({"TABLE_NAME": None}, "TABLE_NAME"),
    ({"STORAGE_BACKEND": "outro"}, "inválido"),
])
def test_nuvem_insegura_e_recusada(monkeypatch, extra, trecho):
    _nuvem(monkeypatch, **extra)
    with pytest.raises(ConfigError, match=trecho):
        Config.do_ambiente()
