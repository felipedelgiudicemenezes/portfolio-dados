"""E-mail diário com o funil do dia: gera o HTML e o .eml e, com --enviar, manda por SMTP.

Os dados são fictícios, gerados aqui mesmo com semente fixa.

Uso:
    python relatorio_diario.py [--data AAAA-MM-DD] [--saida pasta] [--enviar]

Para --enviar: SMTP_HOST, SMTP_PORT (padrão 587), SMTP_USUARIO, SMTP_SENHA e
DESTINATARIOS (separados por vírgula) nas variáveis de ambiente.
"""

import argparse
import base64
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

# Visual: a paleta e a fonte da dashboard comercial
TEAL, TEAL_CLARO, TEAL_ESCURO, VERDE = "#2f7189", "#4a97b0", "#215a6b", "#45a870"
DEGRADE = "linear-gradient(105deg,#4cb27a 0%,#3a9a85 45%,#2f7189 100%)"  # o Outlook do Windows fica no TEAL
RAMPA_FUNIL = ("#1b4a5c", "#235769", "#296175", "#2f6b7f", "#347388", "#387b91")  # do escuro ao claro
FUNDO, CARTAO, SUPERFICIE, BORDA = "#eef1f4", "#ffffff", "#f6f8fa", "#e1e6eb"
TEXTO, TEXTO_2, APOIO = "#1e2a32", "#465662", "#626f79"
ATENCAO, BRANCO = "#f2c037", "#ffffff"
SOBRE_DEGRADE, FIO_DEGRADE = "#e3f1ec", "#86c0b3"  # texto de apoio e divisória dentro do cabeçalho
SOMBRA = "box-shadow:0 1px 3px rgba(30,42,50,0.07);"  # a dos cartões da tela; quem não desenha, ignora
FONTE = "Nunito,'Segoe UI',Arial,sans-serif"
ARQUIVO_FONTE = PASTA / "fontes" / "nunito-latin.woff2"
LARGURA = 640  # px do e-mail
RESPIRO = 22  # px entre a borda do cartão e o conteúdo
ALTURA_BARRA = 48  # px de cada barra do funil (nome em cima, quantidade embaixo)
RESERVA_CONVERSAO = 150  # px livres à direita das barras para a conversão
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

def estilo(tamanho: int, cor: str = TEXTO, peso: int = 400, altura: int | None = None) -> str:
    """Fonte repetida em cada célula: o Outlook não herda a fonte da tabela de fora."""
    altura = altura or round(tamanho * 1.45)
    return f"font-family:{FONTE};font-size:{tamanho}px;line-height:{altura}px;font-weight:{peso};color:{cor};"


def _estilo_rotulo() -> str:
    """Rótulo pequeno em caixa alta, com as letras afastadas, como os da dashboard."""
    return estilo(11, APOIO, 700, 16) + "letter-spacing:0.6px;text-transform:uppercase;"


def _tabela(linhas: str, atributos: str = "") -> str:
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"{atributos}>{linhas}</table>'


def _espaco(altura: int) -> str:
    """Linha vazia de altura exata (sem a regra de altura, o Outlook aumenta a célula vazia)."""
    return (
        f'<tr><td height="{altura}" style="height:{altura}px;font-size:1px;line-height:{altura}px;'
        f'mso-line-height-rule:exactly;">&nbsp;</td></tr>'
    )


def _parte_de_html(parte: int, total: int) -> str:
    """parte_de() com o percentual em negrito."""
    percentual, absoluto = parte_de(parte, total).split(" · ", 1)
    return f'<strong style="color:{TEXTO};font-weight:800;">{percentual}</strong> · {absoluto}'


def _fonte_embutida() -> str:
    """A Nunito em base64 num @font-face, dentro de @media screen.

    Quem aceita fonte web usa a Nunito. O Outlook do Windows não lê @media, não vê a fonte e fica com a
    reserva (Segoe UI); se a visse sem conseguir carregá-la, cairia em Times New Roman.
    """
    try:
        dados = base64.b64encode(ARQUIVO_FONTE.read_bytes()).decode("ascii")
    except FileNotFoundError:  # sem o arquivo, o e-mail sai com a fonte de reserva
        return ""
    return (
        "<style>\n@media screen {\n"
        "@font-face{font-family:'Nunito';font-style:normal;font-weight:200 1000;font-display:swap;"
        f"src:url(data:font/woff2;base64,{dados}) format('woff2');}}\n}}\n</style>"
    )


def _cabecalho(dia: date) -> str:
    """Faixa no degradê da dashboard; o Outlook do Windows, que não desenha degradê, fica no teal sólido."""
    barras = "".join(
        f'<span style="display:inline-block;width:4px;height:{altura}px;margin-right:3px;'
        f'background-color:{BRANCO};border-radius:2px;"></span>'
        for altura in (7, 12, 17)
    )
    icone = f'<span style="display:inline-block;margin-right:9px;">{barras}</span>'
    linhas = (
        f'<tr><td style="{estilo(22, BRANCO, 800, 30)}">{icone}Fintech Exemplo · Funil do dia</td></tr>'
        f'<tr><td style="padding:4px 0 16px;{estilo(15, BRANCO, 700, 22)}">{por_extenso(dia)}</td></tr>'
        f'<tr><td style="border-top:1px solid {FIO_DEGRADE};padding-top:12px;{estilo(13, SOBRE_DEGRADE, 600)}">'
        "Da simulação ao contrato pago, por etapa e por canal.</td></tr>"
    )
    return (
        f'<td bgcolor="{TEAL}" style="background-color:{TEAL};background-image:{DEGRADE};'
        f'border-radius:12px;padding:24px 28px 18px;">{_tabela(linhas)}</td>'
    )


def _titulo_secao(ordem: int, texto: str) -> str:
    """Número num círculo e o nome da seção, como os títulos da dashboard."""
    selo = (
        f'<td width="24" height="24" align="center" bgcolor="{TEAL}" style="background-color:{TEAL};'
        f'background-image:{DEGRADE};border-radius:12px;{estilo(12, BRANCO, 800, 24)}">{ordem}</td>'
    )
    titulo = f'<td style="padding-left:10px;{estilo(17, TEXTO, 800, 24)}">{escape(texto)}</td>'
    return f'<td style="padding:26px 0 12px;">{_tabela(f"<tr>{selo}{titulo}</tr>")}</td>'


def _cartao(nome: str, valor: str, apoio: str, cor: str, largura: int) -> str:
    """Cartão de indicador: fio colorido no topo, número grande e o apoio (já em HTML) embaixo.

    `largura` é a do conteúdo: o cartão soma mais 18 px de respiro e 1 px de borda de cada lado.
    """
    ponto = (
        f'<span style="display:inline-block;width:7px;height:7px;margin:0 7px 1px 0;border-radius:4px;'
        f'background-color:{cor};"></span>'
    )
    linhas = (
        f'<tr><td style="{_estilo_rotulo()}">{ponto}{escape(nome)}</td></tr>'
        f'<tr><td style="padding:6px 0 3px;white-space:nowrap;{estilo(28, TEAL_ESCURO, 800, 34)}">{escape(valor)}</td></tr>'
        f'<tr><td style="{estilo(12, APOIO)}">{apoio}</td></tr>'
    )
    return (
        f'<td width="{largura}" valign="top" bgcolor="{CARTAO}" style="background-color:{CARTAO};'
        f'border:1px solid {BORDA};border-top:3px solid {cor};border-radius:12px;{SOMBRA}padding:16px 18px 17px;">'
        f"{_tabela(linhas)}</td>"
    )


def _cartoes(resumo: Resumo) -> str:
    """Os três indicadores, com 180, 180 e 256 px (o volume precisa de mais espaço) e 12 px entre eles."""
    ticket = resumo.volume / resumo.pagas if resumo.pagas else 0
    vao = '<td width="12" style="font-size:1px;line-height:1px;">&nbsp;</td>'
    cartoes = vao.join((
        _cartao("Simulações", numero(resumo.simulacoes), "entrada do funil", TEAL, 142),
        _cartao("Contratos pagos", numero(resumo.pagas), _parte_de_html(resumo.pagas, resumo.simulacoes), VERDE, 142),
        _cartao("Volume pago", moeda(resumo.volume), f"ticket médio {moeda(ticket)}", TEAL_CLARO, 218),
    ))
    return f'<td>{_tabela(f"<tr>{cartoes}</tr>")}</td>'


def _cartao_secao(conteudo: str, respiro: str) -> str:
    return (
        f'<td bgcolor="{CARTAO}" style="background-color:{CARTAO};border:1px solid {BORDA};'
        f'border-radius:12px;{SOMBRA}padding:{respiro};">{conteudo}</td>'
    )


def larguras_do_funil(funil: list[int], largura: int, reserva: int = RESERVA_CONVERSAO) -> list[int]:
    """Largura em px de cada barra do funil, proporcional à entrada.

    A primeira barra ocupa a largura toda, a menos que uma das seguintes deixe menos de `reserva` px
    livres à direita para a conversão: aí a escala inteira encolhe, e a proporção se mantém.
    """
    if not funil or funil[0] <= 0:
        return [0] * len(funil)
    maior_seguinte = max(funil[1:], default=0) / funil[0]
    escala = largura
    if maior_seguinte * largura > largura - reserva:
        escala = (largura - reserva) / maior_seguinte
    return [round(quantidade / funil[0] * escala) for quantidade in funil]


def _rotulo_cabe(etapa: str, quantidade: str, largura: int) -> bool:
    """O nome (12 px) em cima da quantidade (15 px) cabe dentro da barra?

    Conta com folga sobre a largura medida na Nunito em negrito: 6,2 px por letra a 12 px e 9,2 px por
    algarismo a 15 px, mais 14 px de respiro (10 à esquerda e 4 à direita).
    """
    return max(len(etapa) * 6.2, len(quantidade) * 9.2) + 14 <= largura


def _barra_do_funil(ordem: int, etapa: str, quantidade: int, anterior: int | None, largura: int, util: int) -> str:
    """Barra na rampa de teal com o nome e a quantidade em branco; se não couberem, vão para a direita dela.

    A barra corre sobre um trilho claro da largura toda, que a liga à conversão no fim da linha.
    """
    cor = RAMPA_FUNIL[min(ordem, len(RAMPA_FUNIL) - 1)]
    dentro = _rotulo_cabe(etapa, numero(quantidade), largura)
    tinta = BRANCO if dentro else TEXTO
    nome_e_quantidade = _tabela(
        f'<tr><td style="padding:7px 4px 0 10px;{estilo(12, tinta, 700, 15)}">{escape(etapa)}</td></tr>'
        f'<tr><td style="padding:0 4px 7px 10px;{estilo(15, tinta, 800, 19)}">{numero(quantidade)}</td></tr>'
    )
    celulas = []
    if largura:
        celulas.append(
            f'<td width="{largura}" height="{ALTURA_BARRA}" bgcolor="{cor}" style="background-color:{cor};'
            f'border-radius:6px;">{nome_e_quantidade if dentro else "&nbsp;"}</td>'
        )
    if not dentro:
        celulas.append(f'<td style="white-space:nowrap;">{nome_e_quantidade}</td>')
    if anterior is not None:
        celulas.append(
            f'<td align="right" style="padding:0 14px 0 12px;white-space:nowrap;{estilo(13, APOIO)}">'
            f"{_parte_de_html(quantidade, anterior)}</td>"
        )
    elif largura < util:
        celulas.append("<td>&nbsp;</td>")
    trilho = f' bgcolor="{SUPERFICIE}" style="background-color:{SUPERFICIE};border-radius:6px;"'
    return _tabela(f"<tr>{''.join(celulas)}</tr>", trilho)


def _funil(resumo: Resumo) -> str:
    util = LARGURA - 2 - 2 * RESPIRO  # o cartão sem a borda e o respiro
    larguras = larguras_do_funil(resumo.funil, util)
    cabecalho = (
        f'<tr><td style="padding-bottom:10px;{_estilo_rotulo()}">Etapa</td>'
        f'<td align="right" style="padding:0 14px 10px 0;{_estilo_rotulo()}">Da etapa anterior</td></tr>'
    )
    linhas = [f"<tr><td>{_tabela(cabecalho)}</td></tr>"]
    for i, (etapa, quantidade, largura) in enumerate(zip(ETAPAS, resumo.funil, larguras)):
        if i:
            linhas.append(_espaco(6))
        anterior = resumo.funil[i - 1] if i else None
        linhas.append(f"<tr><td>{_barra_do_funil(i, etapa, quantidade, anterior, largura, util)}</td></tr>")
    nota = (
        f'<td bgcolor="{SUPERFICIE}" style="background-color:{SUPERFICIE};border-left:3px solid {ATENCAO};'
        f'border-radius:8px;padding:11px 14px;{estilo(13, TEXTO_2)}">Do início ao fim: '
        f"{_parte_de_html(resumo.pagas, resumo.simulacoes)} simulações viraram contrato pago.</td>"
    )
    linhas.append(f'<tr><td style="padding-top:16px;">{_tabela(f"<tr>{nota}</tr>")}</td></tr>')
    return _tabela("".join(linhas))


def _mini_barra(fracao: float, cor: str = TEAL_CLARO, altura: int = 5) -> str:
    """Barra de células de tabela (o Outlook não desenha barra de CSS): trilho cinza e o trecho na cor."""
    cheio = max(0, min(100, round(fracao * 100)))
    celula = f"font-size:1px;line-height:{altura}px;mso-line-height-rule:exactly;"
    trecho = (
        f'<td width="{cheio}%" height="{altura}" bgcolor="{cor}" style="background-color:{cor};'
        f'border-radius:{altura}px;{celula}">&nbsp;</td>'
    ) if cheio else ""
    resto = f'<td height="{altura}" style="{celula}">&nbsp;</td>' if cheio < 100 else ""
    return _tabela(
        f"<tr>{trecho}{resto}</tr>", f' bgcolor="{BORDA}" style="background-color:{BORDA};border-radius:{altura}px;"'
    )


def _linha_canal(nome: str, canal: Canal, volume_do_dia: int) -> str:
    celula = f"padding:11px 0 10px;border-bottom:1px solid {FUNDO};{estilo(13)}"
    numeros = (numero(canal.simulacoes), numero(canal.pagas), parte_de(canal.pagas, canal.simulacoes))
    volume = _tabela(
        f'<tr><td align="right" style="white-space:nowrap;{estilo(13)}">{moeda(canal.volume)}</td></tr>'
        f'<tr><td style="padding-top:6px;">{_mini_barra(canal.volume / volume_do_dia if volume_do_dia else 0)}</td></tr>'
    )
    return (
        f'<tr><td valign="top" style="{celula}">{escape(nome)}</td>'
        + "".join(f'<td align="right" valign="top" style="{celula}white-space:nowrap;">{valor}</td>' for valor in numeros)
        + f'<td valign="top" style="{celula}padding-left:24px;">{volume}</td></tr>'
    )


def _linha_total(resumo: Resumo) -> str:
    celula = f"padding:13px 0 2px;border-top:1px solid {BORDA};{estilo(13, TEXTO, 800)}"
    valores = (numero(resumo.simulacoes), numero(resumo.pagas), parte_de(resumo.pagas, resumo.simulacoes), moeda(resumo.volume))
    numeros = "".join(f'<td align="right" style="{celula}white-space:nowrap;">{valor}</td>' for valor in valores)
    return f'<tr><td style="{celula}">Total</td>{numeros}</tr>'


def _canais(resumo: Resumo) -> str:
    colunas = (("Canal", 140, "left"), ("Simulações", 80, "right"), ("Pagos", 56, "right"),
               ("Conversão", 154, "right"), ("Volume pago", 164, "right"))
    base = f"padding-bottom:9px;border-bottom:1px solid {BORDA};{_estilo_rotulo()}"
    cabecalho = "".join(
        f'<td width="{largura}" align="{alinhamento}" style="{base}">{escape(texto)}</td>'
        for texto, largura, alinhamento in colunas
    )
    linhas = [f"<tr>{cabecalho}</tr>"]
    linhas += [_linha_canal(nome, canal, resumo.volume) for nome, canal in resumo.canais.items()]
    linhas.append(_linha_total(resumo))
    nota = f'<tr><td style="padding-top:14px;{estilo(12, APOIO)}">A barra mostra a parte de cada canal no volume pago do dia.</td></tr>'
    return _tabela("".join(linhas)) + _tabela(nota)


def _rodape() -> str:
    return (
        f'<td style="padding:24px 2px 0;{estilo(12, APOIO)}">'
        f'<strong style="color:{TEXTO_2};font-weight:800;">Fintech Exemplo</strong> · '
        "Enviado automaticamente pela rotina relatorio_diario · dados fictícios, gerados por script</td>"
    )


def montar_html(resumo: Resumo, dia: date) -> str:
    """E-mail só com tabelas e CSS inline, sem JavaScript: o Outlook desenha com o motor do Word.

    O único <style> fica no <head> e só traz a fonte; o resto da aparência vai em cada célula.
    """
    blocos = (
        _cabecalho(dia),
        _titulo_secao(1, "Resumo do dia"),
        _cartoes(resumo),
        _titulo_secao(2, "Funil por etapa"),
        _cartao_secao(_funil(resumo), f"20px {RESPIRO}px {RESPIRO}px"),
        _titulo_secao(3, "Por canal"),
        _cartao_secao(_canais(resumo), f"18px {RESPIRO}px 16px"),
        _rodape(),
    )
    corpo = "\n".join(f"<tr>{bloco}</tr>" for bloco in blocos)
    previa = f"{numero(resumo.pagas)} contratos pagos · {moeda(resumo.volume)}"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>Funil do dia · {dia:%d/%m/%Y}</title>
{_fonte_embutida()}
<!--[if mso]><style>table,td,span,strong{{font-family:'Segoe UI',Arial,sans-serif !important;}}</style><![endif]-->
</head>
<body bgcolor="{FUNDO}" style="margin:0;padding:0;background-color:{FUNDO};">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{escape(previa)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{FUNDO}" style="background-color:{FUNDO};">
<tr><td align="center" style="padding:28px 12px 32px;">
<table role="presentation" width="{LARGURA}" cellpadding="0" cellspacing="0" border="0" style="width:{LARGURA}px;">
{corpo}
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
