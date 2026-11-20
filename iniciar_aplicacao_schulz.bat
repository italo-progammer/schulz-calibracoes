@echo off
setlocal EnableExtensions
rem ======================================================================
rem  Schulz S.A. - Plataforma de calibracoes (Projeto Aplicado III - AV05)
rem  Instala o necessario, inicia a API local e abre o navegador.
rem  Uso: de dois cliques neste arquivo (ou execute-o no Prompt de Comando).
rem ======================================================================
cd /d "%~dp0"
title Plataforma de Calibracoes - Schulz

set "PORTA=5000"
set "URL=http://127.0.0.1:%PORTA%"

echo.
echo [1/4] Verificando o Python 3.10 ou superior...
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo.
    echo ERRO: Python 3.10 ou superior nao foi encontrado no PATH.
    echo Instale em https://www.python.org/downloads/ e marque a opcao
    echo "Add python.exe to PATH" durante a instalacao. Depois execute este arquivo de novo.
    goto :falha
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo      Encontrado: %%v

echo.
echo [2/4] Preparando o ambiente virtual (.venv)...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERRO: nao foi possivel criar o ambiente virtual.
        goto :falha
    )
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERRO: nao foi possivel ativar o ambiente virtual.
    goto :falha
)

echo.
echo [3/4] Instalando as bibliotecas de requirements.txt...
if not exist "requirements.txt" (
    echo ERRO: requirements.txt nao encontrado. Execute este arquivo na raiz do projeto.
    goto :falha
)
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo ERRO: falha ao instalar as bibliotecas. Verifique a conexao com a internet.
    goto :falha
)

echo.
echo [4/4] Iniciando a aplicacao em %URL% ...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%URL%/health' | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo      A aplicacao ja esta em execucao. Abrindo o navegador.
    start "" "%URL%"
    goto :fim
)

rem Servico em uma janela propria (feche-a para encerrar a aplicacao).
start "Schulz API - feche esta janela para encerrar" cmd /k ""%CD%\.venv\Scripts\python.exe" app.py"

rem Aguarda a API responder (ate ~30 s) e entao abre o navegador padrao.
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%URL%/health' | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 1 } }; if($ok){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
    echo ERRO: a aplicacao nao respondeu em 30 segundos. Veja a janela "Schulz API".
    goto :falha
)
start "" "%URL%"
echo      Pronto. Para encerrar, feche a janela "Schulz API".
goto :fim

:falha
echo.
echo A execucao foi interrompida.
pause
exit /b 1

:fim
echo.
timeout /t 5 >nul
exit /b 0
