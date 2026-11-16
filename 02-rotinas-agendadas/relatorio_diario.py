"""E-mail diário com o funil do dia: gera o HTML e o .eml e, com --enviar, manda por SMTP.

Os dados são fictícios, gerados aqui mesmo com semente fixa.

Uso:
    python relatorio_diario.py [--data AAAA-MM-DD] [--saida pasta] [--enviar]

Para --enviar: SMTP_HOST, SMTP_PORT (padrão 587), SMTP_USUARIO, SMTP_SENHA e
DESTINATARIOS (separados por vírgula) nas variáveis de ambiente.
"""

import argparse
import os
import random
import smtplib
import socket
import ssl
import sys
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from pathlib import Path

from rotina import PASTA, SAIDA_PASSAGEIRA

SEMENTE = 42
ETAPAS = ("Simulação", "Proposta enviada", "Crédito aprovado", "Contrato assinado", "Contrato pago")
PASSAGEM = (0.46, 0.62, 0.71, 0.93)  # chance de passar de cada etapa para a seguinte
CANAIS = {  # canal: (fatia das simulações, fator sobre a chance de passagem)
    "Aplicativo": (0.42, 1.00),
    "Site": (0.27, 0.85),
    "Parceiros": (0.21, 1.15),
    "Central de vendas": (0.10, 1.05),
}
DOMINIO = "fintechexemplo.example"  # o domínio .example é reservado para exemplos (RFC 2606)
VARIAVEIS_SMTP = ("SMTP_HOST", "SMTP_USUARIO", "SMTP_SENHA", "DESTINATARIOS")
ERROS_PASSAGEIROS = (
    ConnectionError,
    TimeoutError,
    socket.gaierror,
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
)

MARINHO, AREIA, BRONZE, CREME = "#1c2d42", "#d6b78a", "#8a6230", "#f7f0e5"
TINTA, CINZA, BRANCO = "#18212c", "#677282", "#ffffff"
FONTE = "'Inter','Segoe UI',Arial,sans-serif"
DIAS_DA_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


@dataclass(frozen=True)
class Simulacao:
    canal: str
    etapa: int  # índice da última etapa alcançada em ETAPAS
    valor: int  # em reais


@dataclass
class Canal:
    simulacoes: int = 0
    pagas: int = 0
    volume: int = 0


@dataclass
class Resumo:
    funil: list[int]  # quantas simulações chegaram a cada etapa
    canais: dict[str, Canal]

    @property
    def simulacoes(self) -> int:
        return self.funil[0]

    @property
    def pagas(self) -> int:
        return self.funil[-1]

    @property
    def volume(self) -> int:
        return sum(canal.volume for canal in self.canais.values())


# Dados

def gerar_simulacoes(rng: random.Random) -> list[Simulacao]:
    """Um dia fictício: cada simulação com o canal, a etapa a que chegou e o valor."""
    nomes = list(CANAIS)
    fatias = [CANAIS[nome][0] for nome in nomes]
    simulacoes = []
    for _ in range(rng.randint(1100, 1300)):
        canal = rng.choices(nomes, fatias)[0]
        etapa = 0
        while etapa < len(PASSAGEM) and rng.random() < min(PASSAGEM[etapa] * CANAIS[canal][1], 0.98):
            etapa += 1
        valor = min(max(round(rng.lognormvariate(8.6, 0.55) / 50) * 50, 500), 50_000)
        simulacoes.append(Simulacao(canal, etapa, valor))
    return simulacoes


def resumir(simulacoes: list[Simulacao]) -> Resumo:
    ultima = len(ETAPAS) - 1
    funil = [0] * len(ETAPAS)
    canais = {nome: Canal() for nome in CANAIS}
    for simulacao in simulacoes:
        for etapa in range(simulacao.etapa + 1):
            funil[etapa] += 1
        canal = canais[simulacao.canal]
        canal.simulacoes += 1
        if simulacao.etapa == ultima:
            canal.pagas += 1
            canal.volume += simulacao.valor
    return Resumo(funil, canais)


# Formatação brasileira

def numero(valor, casas: int = 0) -> str:
    """1.234,5 (meio arredonda para cima)"""
    arredondado = Decimal(str(valor)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    return f"{arredondado:,.{casas}f}".translate(str.maketrans(",.", ".,"))


def moeda(valor) -> str:
    """R$ 1.234,56"""
    return f"R$ {numero(valor, 2)}"


def parte_de(parte: int, total: int) -> str:
    """12,3% · 98 de 800: o percentual sempre acompanhado do número absoluto."""
    percentual = Decimal(parte) * 100 / Decimal(total) if total else Decimal(0)
    return f"{numero(percentual, 1)}% · {numero(parte)} de {numero(total)}"


def por_extenso(dia: date) -> str:
    """Segunda-feira, 16 de novembro de 2026"""
    return f"{DIAS_DA_SEMANA[dia.weekday()].capitalize()}, {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


# HTML do e-mail

def estilo(tamanho: int, cor: str = TINTA, peso: int = 400) -> str:
    """Fonte repetida em cada célula: o Outlook não herda a fonte da tabela de fora."""
    altura = round(tamanho * 1.45)
    return f"font-family:{FONTE};font-size:{tamanho}px;line-height:{altura}px;font-weight:{peso};color:{cor};"


def _tabela(linhas: str, atributos: str = "") -> str:
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"{atributos}>{linhas}</table>'


def _titulo(texto: str) -> str:
    return _tabela(f'<tr><td style="padding:0 0 10px;{estilo(16, TINTA, 700)}">{escape(texto)}</td></tr>')


def _cartao(rotulo: str, valor: str, detalhe: str, largura: int) -> str:
    linhas = (
        f'<tr><td style="padding:12px 14px 0;{estilo(12, CINZA)}">{escape(rotulo)}</td></tr>'
        f'<tr><td style="padding:2px 14px 0;white-space:nowrap;{estilo(21, TINTA, 700)}">{escape(valor)}</td></tr>'
        f'<tr><td style="padding:2px 14px 12px;{estilo(12, BRONZE)}">{escape(detalhe)}</td></tr>'
    )
    caixa = _tabela(linhas, f' bgcolor="{CREME}" style="background:{CREME};border-top:3px solid {AREIA};"')
    return f'<td width="{largura}%" valign="top" style="padding:0 6px;">{caixa}</td>'


def _cabecalho(colunas: list[tuple[str, int, str]]) -> str:
    base = f"padding:0 0 6px;border-bottom:2px solid {AREIA};{estilo(11, CINZA, 700)}"
    celulas = "".join(
        f'<td width="{largura}" align="{alinhamento}" style="{base}text-transform:uppercase;letter-spacing:0.5px;">'
        f"{escape(texto)}</td>"
        for texto, largura, alinhamento in colunas
    )
    return f"<tr>{celulas}</tr>"


def _barra(fracao: float, cor: str) -> str:
    """Barra horizontal feita de células de tabela, que o Outlook desenha sem CSS moderno."""
    cheio = max(1, min(100, round(fracao * 100)))
    vazio = 100 - cheio
    celula = "font-size:0;line-height:0;"
    resto = f'<td width="{vazio}%" bgcolor="{CREME}" style="background:{CREME};{celula}">&nbsp;</td>' if vazio else ""
    return _tabela(
        f'<tr><td width="{cheio}%" height="12" bgcolor="{cor}" style="background:{cor};height:12px;{celula}">'
        f"&nbsp;</td>{resto}</tr>"
    )


def _funil(resumo: Resumo) -> str:
    linhas = [_cabecalho([("Etapa", 150, "left"), ("", 200, "left"), ("Quantidade", 70, "right"),
                          ("Da etapa anterior", 164, "right")])]
    celula = f"padding:9px 0;border-bottom:1px solid {CREME};{estilo(13)}"
    for i, (etapa, quantidade) in enumerate(zip(ETAPAS, resumo.funil)):
        anterior = parte_de(quantidade, resumo.funil[i - 1]) if i else "—"
        cor = BRONZE if i == len(ETAPAS) - 1 else MARINHO
        linhas.append(
            f'<tr><td style="{celula}">{escape(etapa)}</td>'
            f'<td style="{celula}padding-right:14px;">{_barra(quantidade / resumo.simulacoes, cor)}</td>'
            f'<td align="right" style="{celula}font-weight:700;">{numero(quantidade)}</td>'
            f'<td align="right" style="{celula}color:{CINZA};white-space:nowrap;">{anterior}</td></tr>'
        )
    return _tabela("".join(linhas))


def _linha_canal(nome: str, simulacoes: int, pagas: int, volume: int, total: bool = False) -> str:
    borda = f"border-top:2px solid {MARINHO};" if total else f"border-bottom:1px solid {CREME};"
    celula = f"padding:9px 0;{borda}{estilo(13, TINTA, 700 if total else 400)}"
    valores = (numero(simulacoes), numero(pagas), parte_de(pagas, simulacoes), moeda(volume))
    numeros = "".join(f'<td align="right" style="{celula}white-space:nowrap;">{valor}</td>' for valor in valores)
    return f'<tr><td style="{celula}">{escape(nome)}</td>{numeros}</tr>'


def _canais(resumo: Resumo) -> str:
    linhas = [_cabecalho([("Canal", 140, "left"), ("Simulações", 90, "right"), ("Pagos", 70, "right"),
                          ("Conversão", 150, "right"), ("Volume pago", 134, "right")])]
    linhas += [_linha_canal(nome, c.simulacoes, c.pagas, c.volume) for nome, c in resumo.canais.items()]
    linhas.append(_linha_canal("Total", resumo.simulacoes, resumo.pagas, resumo.volume, total=True))
    return _tabela("".join(linhas))


def montar_html(resumo: Resumo, dia: date) -> str:
    """E-mail só com tabelas e CSS inline, sem JavaScript: o Outlook desenha com o motor do Word."""
    ticket = resumo.volume / resumo.pagas if resumo.pagas else 0
    cartoes = _tabela(
        "<tr>"
        + _cartao("Simulações", numero(resumo.simulacoes), "entrada do funil", 28)
        + _cartao("Contratos pagos", numero(resumo.pagas), parte_de(resumo.pagas, resumo.simulacoes), 32)
        + _cartao("Volume pago", moeda(resumo.volume), f"ticket médio {moeda(ticket)}", 40)
        + "</tr>"
    )
    topo = _tabela(
        f'<tr><td style="{estilo(12, AREIA, 700)}letter-spacing:1.5px;text-transform:uppercase;">'
        "Fintech Exemplo · Funil do dia</td></tr>"
        f'<tr><td style="padding-top:6px;{estilo(24, BRANCO, 700)}">{por_extenso(dia)}</td></tr>'
        f'<tr><td style="padding-top:4px;{estilo(13, CREME)}">Da simulação ao contrato pago, por etapa e por canal.</td></tr>'
    )
    fim_a_fim = _tabela(
        f'<tr><td style="padding:12px 0 0;{estilo(13, CINZA)}">Do início ao fim: '
        f'<strong style="color:{TINTA};">{parte_de(resumo.pagas, resumo.simulacoes)}</strong> '
        "simulações viraram contrato pago.</td></tr>"
    )
    previa = f"{numero(resumo.pagas)} contratos pagos · {moeda(resumo.volume)}"
    rodape = "Enviado automaticamente pela rotina relatorio_diario. Dados fictícios, gerados por script."
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Funil do dia · {dia:%d/%m/%Y}</title>
</head>
<body style="margin:0;padding:0;background:{CREME};">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{escape(previa)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{CREME}" style="background:{CREME};">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" bgcolor="{BRANCO}" style="width:640px;background:{BRANCO};">
<tr><td bgcolor="{MARINHO}" style="background:{MARINHO};padding:24px 28px;">{topo}</td></tr>
<tr><td style="padding:22px 22px 4px;">{cartoes}</td></tr>
<tr><td style="padding:22px 28px 0;">{_titulo("Funil")}{_funil(resumo)}{fim_a_fim}</td></tr>
<tr><td style="padding:28px 28px 30px;">{_titulo("Por canal")}{_canais(resumo)}</td></tr>
</table>
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="width:640px;">
<tr><td align="center" style="padding:14px 28px 0;{estilo(12, CINZA)}">{rodape}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


# Texto, e-mail e envio

def montar_texto(resumo: Resumo, dia: date) -> str:
    """Versão em texto puro, para quem lê o e-mail sem HTML."""
    linhas = [f"Fintech Exemplo · Funil do dia · {dia:%d/%m/%Y}", ""]
    for i, (etapa, quantidade) in enumerate(zip(ETAPAS, resumo.funil)):
        anterior = f"   {parte_de(quantidade, resumo.funil[i - 1])} da etapa anterior" if i else ""
        linhas.append(f"{etapa:<18} {numero(quantidade):>6}{anterior}")
    linhas += ["", f"Volume pago: {moeda(resumo.volume)}", "", "Conversão por canal:"]
    for nome, canal in resumo.canais.items():
        linhas.append(f"  {nome:<18} {parte_de(canal.pagas, canal.simulacoes):<20} {moeda(canal.volume):>15}")
    linhas += ["", "Dados fictícios, gerados por script."]
    return "\n".join(linhas) + "\n"


def montar_email(resumo: Resumo, dia: date, html: str, remetente: str, destinatarios: list[str]) -> EmailMessage:
    mensagem = EmailMessage()
    mensagem["Subject"] = f"Funil do dia {dia:%d/%m/%Y}: {numero(resumo.pagas)} contratos pagos, {moeda(resumo.volume)}"
    mensagem["From"] = remetente
    mensagem["To"] = ", ".join(destinatarios)
    mensagem["Date"] = formatdate(localtime=True)
    mensagem["Message-ID"] = make_msgid(domain=DOMINIO)
    mensagem.set_content(montar_texto(resumo, dia))
    mensagem.add_alternative(html, subtype="html")
    return mensagem


def salvar(html: str, mensagem: EmailMessage, dia: date, pasta: Path) -> tuple[Path, Path]:
    """Grava saida/relatorio-AAAA-MM-DD.html e o .eml (abre no Outlook com duplo clique)."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_html = pasta / f"relatorio-{dia:%Y-%m-%d}.html"
    caminho_eml = caminho_html.with_suffix(".eml")
    caminho_html.write_text(html, encoding="utf-8")
    caminho_eml.write_bytes(mensagem.as_bytes(policy=mensagem.policy.clone(linesep="\r\n")))
    return caminho_html, caminho_eml


class ConfiguracaoIncompleta(Exception):
    """Falta alguma variável de ambiente do SMTP."""


def enviar(mensagem: EmailMessage, ambiente) -> None:
    """Envia pelo SMTP das variáveis de ambiente: porta 465 com SSL direto, as outras com STARTTLS."""
    faltando = [nome for nome in VARIAVEIS_SMTP if not ambiente.get(nome)]
    if faltando:
        raise ConfiguracaoIncompleta("Faltam variáveis de ambiente para o envio: " + ", ".join(faltando))
    porta = int(ambiente.get("SMTP_PORT") or 587)
    contexto = ssl.create_default_context()
    if porta == 465:
        servidor = smtplib.SMTP_SSL(ambiente["SMTP_HOST"], porta, timeout=30, context=contexto)
    else:
        servidor = smtplib.SMTP(ambiente["SMTP_HOST"], porta, timeout=30)
    with servidor:
        if porta != 465:
            servidor.starttls(context=contexto)
        servidor.login(ambiente["SMTP_USUARIO"], ambiente["SMTP_SENHA"])
        servidor.send_message(mensagem)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o e-mail do funil do dia (dados fictícios).")
    parser.add_argument("--data", type=date.fromisoformat, default=date.today(), help="dia do relatório (padrão: hoje)")
    parser.add_argument("--saida", type=Path, default=PASTA / "saida", help="pasta dos arquivos (padrão: saida/)")
    parser.add_argument("--enviar", action="store_true", help="envia por SMTP, com as variáveis de ambiente")
    args = parser.parse_args(argv)

    resumo = resumir(gerar_simulacoes(random.Random(SEMENTE)))
    destinatarios = [e.strip() for e in os.environ.get("DESTINATARIOS", "").split(",") if e.strip()]
    remetente = os.environ.get("SMTP_USUARIO") or f"relatorios@{DOMINIO}"
    html = montar_html(resumo, args.data)
    mensagem = montar_email(resumo, args.data, html, remetente, destinatarios or [f"diretoria@{DOMINIO}"])
    caminho_html, caminho_eml = salvar(html, mensagem, args.data, args.saida)
    print(f"Gerados {caminho_html.name} e {caminho_eml.name} em {caminho_html.parent}")
    if not args.enviar:
        return 0

    try:
        enviar(mensagem, os.environ)
    except ConfiguracaoIncompleta as erro:
        print(erro, file=sys.stderr)
        return 2
    except ERROS_PASSAGEIROS as erro:
        print(f"Falha passageira no envio: {erro}", file=sys.stderr)
        return SAIDA_PASSAGEIRA
    except OSError as erro:  # inclui a recusa do servidor (SMTPException) e erro de SSL
        print(f"Erro no envio: {erro}", file=sys.stderr)
        return 1
    print(f"Enviado para {len(destinatarios)} destinatário(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
