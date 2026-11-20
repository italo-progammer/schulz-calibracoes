"""Ponto de entrada do AWS Lambda (Function URL, payload v2).

O apig-wsgi traduz o evento HTTP do Lambda para uma chamada WSGI ao Flask e a
resposta de volta. binary_support=True é necessário para enviar o PDF e receber
o upload multipart (o Lambda entrega o corpo binário em base64).

A configuração (senha, chave, tabela) vem das variáveis de ambiente definidas em
template.yaml. Se algo faltar, Config.validar() interrompe o início da função.
"""
from apig_wsgi import make_lambda_handler

from app import create_app

app = create_app()
handler = make_lambda_handler(app, binary_support=True)
