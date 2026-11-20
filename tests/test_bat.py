"""Guarda estrutural do iniciar_aplicacao_schulz.bat (não executa cmd: roda em qualquer SO)."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BAT = RAIZ / "iniciar_aplicacao_schulz.bat"


def _texto():
    return BAT.read_bytes()


def test_bat_na_raiz_com_arquivos_exigidos_pelo_roteiro():
    assert BAT.exists()
    for nome in ("requirements.txt", "app.py"):
        assert (RAIZ / nome).exists(), nome


def test_bat_usa_crlf_e_apenas_ascii():
    dados = _texto()
    assert b"\r\n" in dados and re.search(rb"(?<!\r)\n", dados) is None
    dados.decode("ascii")          # acentos quebrariam em páginas de código do Windows


def test_bat_cumpre_os_requisitos_funcionais():
    t = _texto().decode("ascii")
    assert "sys.version_info >= (3,10)" in t              # checagem do Python 3.10+
    assert "-m venv .venv" in t and "activate.bat" in t    # criação e ativação da venv
    assert "pip install" in t and "-r requirements.txt" in t
    assert "app.py" in t and 'start "" "%URL%"' in t       # API + navegador padrão
    assert "/health" in t                                  # espera a API subir antes de abrir


def test_bat_tem_parenteses_balanceados_nos_blocos():
    linhas = [l for l in _texto().decode("ascii").splitlines()
              if not l.strip().lower().startswith("rem") and "powershell" not in l]
    abre = sum(1 for l in linhas if l.rstrip().endswith("("))
    fecha = sum(1 for l in linhas if l.strip() == ")")
    assert abre == fecha


def test_requirements_da_raiz_cobrem_o_que_o_app_importa():
    reqs = (RAIZ / "requirements.txt").read_text().lower()
    for pacote in ("flask", "pandas", "openpyxl", "reportlab"):
        assert pacote in reqs
