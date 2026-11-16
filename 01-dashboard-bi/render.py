"""Camada de apresentação: transforma o payload de um perfil numa página HTML autocontida.

O visual segue o do painel que inspirou o projeto: barra lateral em degradê, faixa de
filtros, cartões de origem, indicadores com ícone e funil em rampa. O CSS de estilo.css e a
fonte Nunito (fontes/) vão embutidos, e gráficos e ícones são SVG ou HTML gerados aqui: sem
JavaScript nem recurso externo, o arquivo abre offline e pode ser enviado como anexo.
"""

import base64
import math
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path

PASTA = Path(__file__).resolve().parent
FONTE_NUNITO = base64.b64encode((PASTA / "fontes" / "nunito-latin.woff2").read_bytes()).decode("ascii")
CSS = ("/* Nunito, sob a SIL Open Font License 1.1 (fontes/OFL.txt), embutida na própria página. */\n"
       '@font-face { font-family: "Nunito"; font-style: normal; font-weight: 400 800; font-display: swap;\n'
       f'  src: url(data:font/woff2;base64,{FONTE_NUNITO}) format("woff2"); }}\n'
       + (PASTA / "estilo.css").read_text(encoding="utf-8"))
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
ETAPAS = {"simulacao": "Simulação", "proposta": "Proposta", "analise": "Análise",
          "aprovada": "Aprovada", "assinada": "Assinada", "paga": "Paga"}
CANAIS = {"todos": "Todos", "digital": "Digital", "correspondente": "Correspondentes"}
CORES = {"todos": "#465662", "digital": "#2f7189", "correspondente": "#45a870"}  # as mesmas do estilo.css


# Formatação no padrão brasileiro ------------------------------------------------------

def _arredondar(valor, casas):
    """Arredonda meio para cima (12,25 -> 12,3), como a planilha de quem confere o número."""
    return Decimal(str(valor)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


def numero(valor, casas=0):
    """1234.5 -> '1.234,5'."""
    if valor is None:
        return "—"
    arredondado = _arredondar(valor, casas)
    if arredondado == 0:
        arredondado = abs(arredondado)  # evita "-0,0"
    return f"{arredondado:,.{casas}f}".replace(",", "#").replace(".", ",").replace("#", ".")


def moeda(valor):
    """1234.56 -> 'R$ 1.234,56'."""
    if valor is None:
        return "—"
    texto = numero(valor, 2)
    return f"-R$ {texto[1:]}" if texto.startswith("-") else f"R$ {texto}"


def moeda_compacta(valor, casas=1):
    """Para eixos e rótulos curtos: 'R$ 0', 'R$ 500 mil', 'R$ 2 mi', 'R$ 7,01 mi'."""
    for divisor, sufixo in ((1_000_000, "mi"), (1_000, "mil")):
        if valor >= divisor:
            texto = numero(valor / divisor, casas)
            if "," in texto:
                texto = texto.rstrip("0").rstrip(",")
            return f"R$ {texto} {sufixo}"
    return f"R$ {numero(valor)}"


def moeda_curta(valor):
    """Para legendas, com três algarismos: 'R$ 667 mil', 'R$ 1,17 mi', 'R$ 7,01 mi'."""
    for divisor in (1_000_000, 1_000):
        if valor >= divisor:
            return moeda_compacta(valor, max(0, 2 - int(math.log10(valor / divisor))))
    return moeda(valor)


def percentual(valor, casas=1):
    """12.34 -> '12,3%'."""
    return "—" if valor is None else f"{numero(valor, casas)}%"


def percentual_com_absoluto(pct, parte, todo):
    """'12,3% · 98 de 800': percentual nenhum aparece sem os números de onde saiu."""
    return f"{percentual(pct)} · {numero(parte)} de {numero(todo)}"


def fatia_do_volume(pct, parte, todo):
    """'9,5% · R$ 667 mil de R$ 7,01 mi': a mesma regra, para uma fatia do volume em reais."""
    return f"{percentual(pct)} · {moeda_curta(parte)} de {moeda_curta(todo)}"


def em_meses(valor):
    return "—" if valor is None else f"{numero(valor, 1)} meses"


def taxa_ao_mes(valor):
    return "—" if valor is None else f"{numero(valor, 2)}% a.m."


def texto_variacao(valor, unidade):
    """'▲ 8,4%', '▼ 0,4 mês', '▲ 0,02 p.p.' ou '= 0,0%' quando o arredondado é zero."""
    if valor is None:
        return "sem mês anterior"
    casas = 2 if unidade == "p.p." else 1
    arredondado = _arredondar(valor, casas)
    seta = "▲" if arredondado > 0 else "▼" if arredondado < 0 else "="
    if unidade == "mês" and abs(arredondado) >= 2:
        unidade = "meses"
    separador = "" if unidade == "%" else " "
    return f"{seta} {numero(abs(arredondado), casas)}{separador}{unidade}"


def mes_abreviado(mes):
    """'2026-10' -> 'out/2026'."""
    ano, mm = mes.split("-")
    return f"{MESES[int(mm) - 1][:3]}/{ano}"


def mes_curto(mes):
    """'2026-10' -> 'out/26'."""
    ano, mm = mes.split("-")
    return f"{MESES[int(mm) - 1][:3]}/{ano[2:]}"


def mes_por_extenso(mes):
    """'2026-10' -> 'outubro de 2026'."""
    ano, mm = mes.split("-")
    return f"{MESES[int(mm) - 1]} de {ano}"


def data_br(iso):
    """'2026-10-31' -> '31/10/2026'."""
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


KPIS = (  # chave no payload, rótulo, formato do valor, unidade da variação, ícone, subir é bom?
    ("volume", "Volume liberado", moeda, "%", "volume", True),
    ("contratos", "Contratos pagos", numero, "%", "contratos", True),
    ("ticket_medio", "Ticket médio", moeda, "%", "ticket", True),
    ("prazo_medio", "Prazo médio", em_meses, "mês", "prazo", None),  # None: nem melhor, nem pior
    ("taxa_media", "Taxa média ponderada", taxa_ao_mes, "p.p.", "taxa", None),
)
SECOES = (  # âncora, título e ícone na barra lateral; o número é a ordem
    ("originacao", "Originação", "origem"),
    ("performance", "Performance", "performance"),
    ("funil", "Funil de análise de crédito", "funil"),
    ("ranking", "Ranking de parceiros", "ranking"),
)


# Ícones: traço de 24 × 24 no estilo Feather/Lucide, desenhados à mão -------------------

ICONES = {
    "origem": '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/>'
              '<path d="m8.2 10.8 7.6-4.5M8.2 13.2l7.6 4.5"/>',
    "performance": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M8 17v-4M13 17V8M18 17v-7"/>',
    "funil": '<path d="M3 4h18l-7 8.5V19l-4 2v-8.5z"/>',
    "ranking": '<path d="M8 21h8M12 17v4"/><path d="M7 4h10v5a5 5 0 0 1-10 0z"/>'
               '<path d="M17 6h2.5a2.5 2.5 0 0 1 0 5H17M7 6H4.5a2.5 2.5 0 0 0 0 5H7"/>',
    "perfil": '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.3 7.5 9.5 4.3-1.2 7.5-4.9 7.5-9.5V6z"/><path d="m9 12 2 2 4-4"/>',
    "banco": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
             '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "ajustes": '<path d="M4 8h16M4 16h16"/><circle class="cheio" cx="9" cy="8" r="2.2"/>'
               '<circle class="cheio" cx="15" cy="16" r="2.2"/>',
    "lua": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
    "grafico": '<path d="M3 21h18"/><path d="M6 17v-3M10 17V7M14 17v-6M18 17v-9"/>',
    "busca": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "abrir": '<path d="m6 9 6 6 6-6"/>',
    "codigo": '<path d="m9 8-4 4 4 4M15 8l4 4-4 4"/>',
    "volume": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>'
              '<path d="M6 12h.01M18 12h.01"/>',
    "contratos": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'
                 '<path d="m9 15 2 2 4-4"/>',
    "ticket": '<path d="M12 3H5a2 2 0 0 0-2 2v7l9 9 9-9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "prazo": '<rect x="3.5" y="5" width="17" height="16" rx="2"/><path d="M16 3v4M8 3v4M3.5 10h17"/>',
    "taxa": '<path d="M19 5 5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
}


def icone(nome):
    return f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{ICONES[nome]}</svg>'


# Gráfico de volume por mês, em SVG ----------------------------------------------------

LARGURA_GRAFICO, ALTURA_GRAFICO = 1280, 300  # o cartão de largura inteira numa tela de 1440 px
LARGURA_COLUNA = 44


def _coluna(x, base, largura, altura, raio=6):
    """Coluna em pé: base reta, topo arredondado (ou reto, com raio 0)."""
    if altura <= 0:
        return ""
    topo = base - altura
    r = min(raio, largura / 2, altura)
    if r <= 0:
        return f"M{x:.1f},{base:.1f} V{topo:.1f} H{x + largura:.1f} V{base:.1f} Z"
    return (f"M{x:.1f},{base:.1f} V{topo + r:.1f} A{r},{r} 0 0 1 {x + r:.1f},{topo:.1f} "
            f"H{x + largura - r:.1f} A{r},{r} 0 0 1 {x + largura:.1f},{topo + r:.1f} V{base:.1f} Z")


def _passo_do_eixo(bruto):
    """Passo redondo (1; 2; 2,5 ou 5 × 10ⁿ) logo acima de `bruto`."""
    if bruto <= 0:
        return 1
    potencia = 10 ** math.floor(math.log10(bruto))
    return next(f * potencia for f in (1, 2, 2.5, 5, 10) if f * potencia >= bruto)


def grafico_vendas(serie, por_canal, canais, mes_referencia):
    """Colunas de volume por mês, empilhadas por canal; o melhor mês leva o verde de recorde."""
    largura, altura = LARGURA_GRAFICO, ALTURA_GRAFICO
    esquerda, direita, topo, rodape = 64, 8, 46, 34
    area_largura, area_altura = largura - esquerda - direita, altura - topo - rodape
    base = topo + area_altura
    maximo = max((m["volume"] for m in serie), default=0)
    passo = _passo_do_eixo(maximo / 4)
    teto = passo * max(1, math.ceil(maximo / passo))
    melhor = max(serie, key=lambda m: m["volume"])["mes"] if maximo > 0 else None

    def medida(valor):
        return area_altura * valor / teto

    partes = []
    for i in range(round(teto / passo) + 1):
        y = base - medida(passo * i)
        partes.append(f'<line class="{"base" if i == 0 else "grade"}" x1="{esquerda}" x2="{largura - direita}" '
                      f'y1="{y:.1f}" y2="{y:.1f}"/><text x="{esquerda - 12}" y="{y + 4:.1f}" text-anchor="end">'
                      f'{moeda_compacta(passo * i)}</text>')

    faixa = area_largura / len(serie)
    for i, (item, do_mes) in enumerate(zip(serie, por_canal)):
        centro = esquerda + faixa * (i + 0.5)
        x, topo_coluna = centro - LARGURA_COLUNA / 2, base - medida(item["volume"])
        valores = [do_mes["canais"][canal]["volume"] for canal in canais]
        de_cima = max((j for j, valor in enumerate(valores) if valor > 0), default=None)
        segmentos, chao = [], base
        for j, (canal, valor) in enumerate(zip(canais, valores)):
            if valor > 0:
                caminho = _coluna(x, chao, LARGURA_COLUNA, medida(valor), raio=6 if j == de_cima else 0)
                segmentos.append(f'<path class="seg seg-{canal}" data-canal="{canal}" d="{caminho}"/>')
            chao -= medida(valor)

        fundo = rotulos = ""
        if item["mes"] == melhor:
            fundo = (f'<rect class="melhor-fundo" x="{centro - faixa / 2 + 8:.1f}" y="{topo_coluna - 42:.1f}" '
                     f'width="{faixa - 16:.1f}" height="{base - topo_coluna + 42:.1f}" rx="10"/>')
            rotulos = (f'<text class="melhor-rotulo" x="{centro:.1f}" y="{topo_coluna - 26:.1f}" '
                       f'text-anchor="middle">melhor</text>')
        if item["mes"] in (melhor, mes_referencia):
            classe_valor = "valor recorde" if item["mes"] == melhor else "valor"
            rotulos += (f'<text class="{classe_valor}" x="{centro:.1f}" y="{topo_coluna - 9:.1f}" '
                        f'text-anchor="middle">{moeda_compacta(item["volume"], 2)}</text>')

        por_canal_texto = "; ".join(f"{CANAIS[canal]} {moeda(valor)}" for canal, valor in zip(canais, valores))
        dica = escape(f"{mes_abreviado(item['mes'])}: {moeda(item['volume'])} · "
                      f"{numero(item['contratos'])} contratos ({por_canal_texto})")
        classe_mes = "mes atual" if item["mes"] == mes_referencia else "mes"
        partes.append(
            f'<g class="coluna"><title>{dica}</title>{fundo}'
            f'<rect class="alvo" x="{centro - faixa / 2:.1f}" y="0" width="{faixa:.1f}" height="{altura}"/>'
            f'{"".join(segmentos)}{rotulos}<text class="{classe_mes}" x="{centro:.1f}" y="{altura - 10}" '
            f'text-anchor="middle">{mes_curto(item["mes"])}</text></g>')
    descricao = (f"Volume liberado por mês e canal, de {mes_abreviado(serie[0]['mes'])} "
                 f"a {mes_abreviado(serie[-1]['mes'])}")
    return (f'<div class="rolavel"><svg class="grafico" viewBox="0 0 {largura} {altura}" role="img" '
            f'aria-label="{descricao}">{"".join(partes)}</svg></div>')


# Peças comuns ---------------------------------------------------------------------------

def _literal_sql(valor):
    if valor is None:
        return "NULL"
    return f"'{valor}'" if isinstance(valor, str) else str(valor)


def _celula(valor):
    if valor is None:
        return "NULL"
    if isinstance(valor, float):
        return numero(valor, 2)
    if isinstance(valor, int):
        return numero(valor)
    return escape(str(valor))


def _tabela_de_linhas(linhas):
    """As linhas cruas da consulta, com os números alinhados à direita."""
    colunas = list(linhas[0])
    numericas = {c for c in colunas if any(isinstance(linha[c], (int, float)) for linha in linhas)}

    def classe(coluna):
        return ' class="num"' if coluna in numericas else ""

    cabecalho = "".join(f"<th{classe(c)}>{escape(c)}</th>" for c in colunas)
    corpo = "".join("<tr>" + "".join(f"<td{classe(c)}>{_celula(linha[c])}</td>" for c in colunas) + "</tr>"
                    for linha in linhas)
    return (f'<div class="rolavel"><table class="linhas"><thead><tr>{cabecalho}</tr></thead>'
            f'<tbody>{corpo}</tbody></table></div>')


def bloco_fonte(fonte):
    """O "fonte" de um quadro: um link discreto que abre o arquivo, os parâmetros, o SQL e as linhas."""
    parametros = " · ".join(f":{nome} = {_literal_sql(valor)}" for nome, valor in fonte["parametros"].items())
    linhas = fonte["linhas"]
    tabela = _tabela_de_linhas(linhas) if linhas else ""
    plural = "linha" if len(linhas) == 1 else "linhas"
    return (f'<details class="fonte"><summary>{icone("codigo")}fonte<code>{escape(fonte["arquivo"])}</code>'
            f'</summary><div class="fonte-corpo"><p class="fonte-meta">Parâmetros: '
            f'<code>{escape(parametros or "nenhum")}</code></p>'
            f'<pre><code>{escape(fonte["sql"].strip())}</code></pre>'
            f'<p class="fonte-meta">A consulta devolveu {numero(len(linhas))} {plural}:</p>{tabela}</div></details>')


def como_ler(itens):
    """O "Como ler esta seção": as regras do quadro, fechadas até alguém pedir."""
    lista = "".join(f"<li>{item}</li>" for item in itens)
    return (f'<details class="como-ler"><summary><span class="interrogacao" aria-hidden="true">?</span>'
            f'Como ler esta seção</summary><ul>{lista}</ul></details>')


def pe_da_secao(*blocos):
    """A linha de pé de uma seção: "Como ler" e "fonte" lado a lado; o que for aberto ocupa a linha toda."""
    return f'<div class="secao-pe">{"".join(blocos)}</div>'


def secao(numero_secao, ancora, titulo, corpo):
    """Cabeçalho (número em degradê, título e a chave "Mostrar fontes") e o conteúdo da seção."""
    return (f'<section class="secao" id="{ancora}" aria-labelledby="{ancora}-titulo">'
            f'<div class="secao-cabeca"><span class="secao-num" aria-hidden="true">{numero_secao}</span>'
            f'<h2 id="{ancora}-titulo">{escape(titulo)}</h2>'
            f'<label class="chave"><input type="checkbox" role="switch" checked>'
            f'<span class="chave-trilho" aria-hidden="true"></span>Mostrar fontes</label></div>{corpo}</section>')


def cartao(titulo, subtitulo, corpo, fonte, largo=False):
    """Um quadro branco: título, subtítulo, conteúdo e, no pé, o "fonte" da consulta que o alimenta."""
    classe = "cartao quadro largo" if largo else "cartao quadro"
    return (f'<article class="{classe}"><h3 class="cartao-titulo">{escape(titulo)}</h3>'
            f'<p class="cartao-sub">{subtitulo}</p><div class="cartao-corpo">{corpo}</div>'
            f'{bloco_fonte(fonte)}</article>')


# Barra lateral, saudação, faixa de filtros e nota do perfil ----------------------------

def _item_lateral(ancora, titulo, nome_icone, ativo=False):
    atual = ' class="ativo" aria-current="location"' if ativo else ""
    return (f'<li><a href="#{ancora}"{atual} title="{escape(titulo)}">{icone(nome_icone)}'
            f'<span class="sr">{escape(titulo)}</span></a></li>')


def barra_lateral(empresa):
    """Monograma, uma âncora por seção e, no pé, os ícones de ajustes e de tema."""
    secoes = "".join(_item_lateral(ancora, titulo, nome, ativo=i == 0)
                     for i, (ancora, titulo, nome) in enumerate(SECOES))
    extras = _item_lateral("perfil", "Recorte do perfil", "perfil") + _item_lateral("fontes", "Fontes", "banco")
    return (f'<nav class="lateral" aria-label="Seções da página">'
            f'<a class="monograma" href="#topo" aria-label="{escape(empresa)}: voltar ao início">FE</a>'
            f'<ul class="lateral-menu">{secoes}</ul><hr class="lateral-sep">'
            f'<ul class="lateral-menu">{extras}</ul>'
            f'<div class="lateral-pe" aria-hidden="true">{icone("ajustes")}{icone("lua")}</div></nav>')


def topo_da_pagina(payload, diretoria):
    """A saudação com o período e a faixa em degradê: título, busca, filtros e contador."""
    perfil, empresa = payload["perfil"], escape(payload["empresa"])
    mes, anterior = payload["mes_referencia"], payload["mes_anterior"]
    inicio, fim = payload["periodo"]["inicio"], payload["periodo"]["fim"]
    dias = (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1
    quantos = len(payload["ranking"]["parceiros"])
    filtros = (("Período", mes_por_extenso(mes).capitalize()),
               ("Canal", "Todos" if diretoria else CANAIS["correspondente"]),
               ("Parceiro", "Todos" if diretoria else f"Os {quantos} da carteira"),
               ("Gerente", "Todos" if diretoria else perfil["nome"]))
    lista = "".join(f'<div class="filtro"><dt>{rotulo}</dt><dd><span>{escape(valor)}</span>'
                    f'{icone("abrir")}</dd></div>' for rotulo, valor in filtros)
    contratos, no_ano = payload["kpis"]["contratos"]["atual"], payload["contratos_no_ano"]
    primeiro_mes = payload["vendas_por_mes"][0]["mes"]
    contador = (f'<p class="contador" title="Contratos pagos em {mes_abreviado(mes)}, de {numero(no_ano)} pagos de '
                f'{mes_abreviado(primeiro_mes)} a {mes_abreviado(mes)}">'
                f'{numero(contratos)} de {numero(no_ano)} contratos</p>')
    comparacao = f" · comparação com {mes_por_extenso(anterior)}" if anterior else ""
    periodo = f"<strong>{data_br(inicio)}</strong> até <strong>{data_br(fim)}</strong> · {dias} dias{comparacao}"
    dado_ate = data_br(payload["data_dado"])
    return f"""<header class="saudacao">
  <p>Olá! Você está no <strong>Dashboard {empresa}</strong> · {data_br(inicio)} até {data_br(fim)}</p>
  <p class="atualizado" title="Dados até o fim do dia {dado_ate}">Atualizado <strong>{dado_ate} 23:59</strong></p>
</header>
<section class="faixa" aria-labelledby="titulo-pagina">
  <div class="faixa-titulo">
    <h1 id="titulo-pagina">{icone("grafico")}Dashboard {empresa}</h1>
    <p class="faixa-perfil">Perfil <strong>{escape(perfil["nome"])}</strong></p>
  </div>
  <div class="busca" aria-hidden="true">{icone("busca")}<span>Buscar parceiro, gerente ou canal…</span></div>
  <div class="filtros">
    <dl class="filtros-lista" aria-label="Filtros desta página">{lista}</dl>
    <div class="filtros-acoes"><span class="limpar" aria-hidden="true">Limpar</span>{contador}</div>
  </div>
  <p class="faixa-periodo">{periodo}</p>
</section>"""


def nota_do_perfil(payload, diretoria):
    """A nota de fio amarelo: o que esta página contém e onde o recorte acontece."""
    perfil, parceiros = payload["perfil"], payload["ranking"]["parceiros"]
    if diretoria:
        gerentes = len({parceiro["gerente"] for parceiro in parceiros})
        texto = (f"<strong>Página da diretoria: canal digital e os {len(parceiros)} parceiros dos {gerentes} "
                 "gerentes, somados.</strong> O canal digital não tem parceiro nem gerente; no ranking, ele fica "
                 "numa linha à parte, abaixo dos parceiros. Cada gerente recebe outra página, só com a própria "
                 "carteira: o recorte é feito na consulta SQL, antes de a página existir.")
    else:
        texto = (f"<strong>Página de {escape(perfil['nome'])}: só os {len(parceiros)} parceiros da sua "
                 f"carteira.</strong> O recorte é feito na consulta SQL, com "
                 f"<code>:gerente_id = {perfil['gerente_id']}</code>, antes de a página existir: o canal digital "
                 "e as carteiras dos outros gerentes não estão neste arquivo, nem escondidos.")
    return f'<aside class="nota" id="perfil" aria-label="Recorte desta página"><p>{texto}</p></aside>'


# 1. Originação ------------------------------------------------------------------------

def _tons_de_verde(quantos):
    """Um verde por parceiro, do escuro ao claro, para a barra e os cartões da carteira."""
    escuro, claro = (0x2b, 0x80, 0x52), (0x8e, 0xcf, 0xab)
    if quantos == 1:
        return [CORES["correspondente"]]
    return ["#%02x%02x%02x" % tuple(round(e + (c - e) * i / (quantos - 1)) for e, c in zip(escuro, claro))
            for i in range(quantos)]


def _grade_da_origem(item):
    conversao = (f'{percentual(item["conversao"])}<small> · {numero(item["pagas"])} de '
                 f'{numero(item["simulacoes"])}</small>')
    celulas = (("Contratos", numero(item["contratos"])), ("Ticket médio", moeda(item["ticket_medio"])),
               ("Propostas", numero(item["simulacoes"])), ("Conversão", conversao))
    return ('<dl class="origem-grade">'
            + "".join(f"<div><dt>{rotulo}</dt><dd>{valor}</dd></div>" for rotulo, valor in celulas) + "</dl>")


def cartao_origem(item, nome, cor, canto, barra, destaque=False):
    """Um cartão de origem: ponto e nome, valor liberado em destaque, barra de proporção e a grade."""
    classe = "cartao origem destaque" if destaque else "cartao origem"
    return (f'<article class="{classe}" style="--cor: {cor}" data-canal="{item["canal"]}">'
            f'<header class="origem-cabeca"><h3><span class="ponto" aria-hidden="true"></span>{escape(nome)}</h3>'
            f'<span class="origem-canto">{canto}</span></header>'
            f'<p class="origem-valor">{moeda(item["volume"])}</p>{barra}{_grade_da_origem(item)}</article>')


def secao_originacao(payload, diretoria):
    """O todo da página e as partes que o somam: canais na diretoria, parceiros na página do gerente."""
    todo, partes = payload["origens"]["todo"], payload["origens"]["partes"]
    if diretoria:
        quantos = len(payload["ranking"]["parceiros"])
        nomes = [CANAIS[parte["canal"]] for parte in partes]
        cores = [CORES[parte["canal"]] for parte in partes]
        cantos = [{"digital": "sem parceiro", "correspondente": f"{quantos} parceiros"}[parte["canal"]]
                  for parte in partes]
        nome_do_todo, canto_do_todo, cor_do_todo = CANAIS["todos"], " + ".join(nomes), CORES["todos"]
    else:
        nomes = [parte["parceiro"] for parte in partes]
        cores = _tons_de_verde(len(partes))
        cantos = [f"{parte['posicao']}º no volume" for parte in partes]
        nome_do_todo, canto_do_todo = CANAIS["correspondente"], f"{len(partes)} parceiros da carteira"
        cor_do_todo = CORES["correspondente"]

    def item_da_legenda(parte, nome, cor):
        # Na diretoria, a legenda traz a fatia de cada canal; na carteira, só os nomes: cada
        # parceiro tem o próprio cartão ao lado, com a fatia e o valor.
        fatia = f' {percentual(parte["participacao"])} · {moeda_curta(parte["volume"])}' if diretoria else ""
        return f'<li><i style="background: {cor}"></i>{escape(nome)}{fatia}</li>'

    segmentos = "".join(f'<span style="width: {parte["participacao"] or 0:.2f}%; background: {cor}"></span>'
                        for parte, cor in zip(partes, cores))
    legenda = "".join(item_da_legenda(parte, nome, cor) for parte, nome, cor in zip(partes, nomes, cores))
    barra_do_todo = (f'<div class="barra" role="img" aria-label="Divisão do volume liberado">{segmentos}</div>'
                     f'<ul class="legenda">{legenda}</ul>')
    cartoes = [cartao_origem(todo, nome_do_todo, cor_do_todo, escape(canto_do_todo), barra_do_todo, destaque=True)]
    for parte, nome, cor, canto in zip(partes, nomes, cores, cantos):
        barra = (f'<div class="barra"><span style="width: {parte["participacao"] or 0:.2f}%; background: {cor}">'
                 f'</span></div><p class="barra-legenda">'
                 f'{fatia_do_volume(parte["participacao"], parte["volume"], todo["volume"])}</p>')
        cartoes.append(cartao_origem(parte, nome, cor, escape(canto), barra))

    explicacao = ("Volume, contratos e ticket médio: contratos pagos no mês, pela data de pagamento. Propostas: "
                  "criadas no mês, a partir da simulação; a conversão é quantas delas já foram pagas.")
    regras = [f"<strong>{nome_do_todo}</strong> é a soma dos cartões ao lado; a barra mostra a fatia de cada "
              f"{'canal' if diretoria else 'parceiro'} no volume liberado do mês.",
              "Ticket médio é o volume liberado dividido pelos contratos pagos."]
    if payload["mes_anterior"]:
        mes, anterior = (MESES[int(m[5:7]) - 1] for m in (payload["mes_referencia"], payload["mes_anterior"]))
        regras.insert(1, f"As duas datas não se misturam: uma proposta criada em {anterior} e paga em {mes} entra "
                         f"no volume de {mes}, mas na conversão de {anterior}.")
    return secao(1, "originacao", "Originação",
                 f'<div class="origens">{"".join(cartoes)}</div><p class="secao-nota">{explicacao}</p>'
                 + pe_da_secao(como_ler(regras), bloco_fonte(payload["fontes"]["ranking_parceiros"])))


# 2. Performance ------------------------------------------------------------------------

def _estado_da_variacao(variacao, subir_e_bom):
    if variacao is None or subir_e_bom is None or _arredondar(variacao, 1) == 0:
        return "neutro"
    return "bom" if (variacao > 0) == subir_e_bom else "ruim"


def linha_de_kpis(payload):
    """Os cinco indicadores do mês, cada um com a variação e o valor do mês anterior."""
    anterior = payload["mes_anterior"]
    blocos = []
    for chave, rotulo, formatar, unidade, nome_icone, subir_e_bom in KPIS:
        kpi = payload["kpis"][chave]
        base = f"{mes_abreviado(anterior)}: {formatar(kpi['anterior'])}" if anterior else ""
        blocos.append(
            f'<div class="cartao kpi"><span class="kpi-icone">{icone(nome_icone)}</span><div>'
            f'<p class="kpi-rotulo">{rotulo}</p><p class="kpi-valor">{formatar(kpi["atual"])}</p>'
            f'<p class="kpi-var {_estado_da_variacao(kpi["variacao"], subir_e_bom)}">'
            f'{texto_variacao(kpi["variacao"], unidade)}</p><p class="kpi-base">{base}</p></div></div>')
    return f'<div class="kpis">{"".join(blocos)}</div>'


def secao_performance(payload):
    serie, mes, canais = payload["vendas_por_mes"], payload["mes_referencia"], payload["canais"]
    legenda = "".join(f'<li data-canal="{canal}"><i class="amostra seg-{canal}"></i>{CANAIS[canal]}</li>'
                      for canal in canais) + '<li><i class="amostra melhor"></i>melhor mês</li>'
    periodo = f"{mes_abreviado(serie[0]['mes'])} a {mes_abreviado(serie[-1]['mes'])}"
    grafico = cartao(
        "Volume liberado por mês",
        f"Contratos pagos de {periodo}, pela data de pagamento, empilhados por canal. Passe o mouse numa coluna "
        "para ver os valores exatos.",
        f'<ul class="legenda grafico-legenda">{legenda}</ul>'
        + grafico_vendas(serie, payload["vendas_por_canal"], canais, mes),
        payload["fontes"]["vendas_por_mes_canal"], largo=True)
    anterior = payload["mes_anterior"]
    comparacao = f", comparado com {mes_abreviado(anterior)}" if anterior else ""
    regras = [f"A variação compara com {mes_abreviado(anterior) if anterior else 'o mês anterior'}: em percentual "
              "para volume, contratos e ticket; em diferença para prazo (meses) e taxa (pontos percentuais).",
              "A taxa média é ponderada pelo valor liberado: o contrato maior pesa mais.",
              ("No gráfico, cada coluna empilha os canais e a soma é o volume do mês; "
               if len(canais) > 1 else "No gráfico, cada coluna é o volume da carteira no mês; ")
              + "o fundo verde marca o melhor mês do período e o rótulo em negrito, o mês de referência."]
    return secao(2, "performance", "Performance",
                 linha_de_kpis(payload)
                 + f'<p class="secao-nota">Indicadores de {mes_por_extenso(mes)}{comparacao}. Volume, contratos e '
                   'ticket ficam em verde quando sobem e em vermelho quando caem; prazo e taxa não têm lado bom e '
                   'ficam em cinza.</p>'
                 + pe_da_secao(como_ler(regras), bloco_fonte(payload["fontes"]["vendas_por_mes"])) + grafico)


# 3. Funil de análise de crédito ---------------------------------------------------------

def funil_em_rampa(funil):
    """Uma barra por etapa, do tom mais escuro ao mais claro; comprimento sobre as simulações."""
    simulacoes = funil[0]["quantidade"]
    linhas = []
    for etapa in funil:
        largura = 100 * etapa["quantidade"] / simulacoes if simulacoes else 0
        if etapa["base"] is None:
            conversao = '<span class="funil-base">base do funil</span>'
        else:
            conversao = (f'<strong>{percentual(etapa["conversao"])}</strong> · '
                         f'{numero(etapa["quantidade"])} de {numero(etapa["base"])}')
        linhas.append(f'<li class="etapa-{etapa["etapa"]}"><div class="funil-trilho">'
                      f'<div class="funil-barra" style="width: {largura:.1f}%"><span>{ETAPAS[etapa["etapa"]]}</span>'
                      f'<strong>{numero(etapa["quantidade"])}</strong></div></div>'
                      f'<p class="funil-conv">{conversao}</p></li>')
    return f'<ol class="funil" aria-label="Etapas do funil e conversão sobre a etapa anterior">{"".join(linhas)}</ol>'


def lista_de_motivos(motivos):
    """Motivos em ordem de quantidade; a barra fina é a fatia do total de propostas que pararam."""
    if not motivos["itens"]:
        return '<p class="secao-nota">Nenhuma proposta criada no mês parou antes do pagamento.</p>'
    itens = []
    for item in motivos["itens"]:
        itens.append(f'<li><div class="motivo-topo"><span class="motivo-nome">{escape(item["motivo"])}'
                     f'<span class="motivo-etapa">{ETAPAS[item["parou_em"]]}</span></span><span class="motivo-num">'
                     f'{percentual_com_absoluto(item["percentual"], item["quantidade"], motivos["total"])}</span></div>'
                     f'<div class="trilho"><span style="width: {item["percentual"] or 0:.1f}%"></span></div></li>')
    return f'<ul class="motivos">{"".join(itens)}</ul>'


def secao_funil(payload):
    funil, motivos, mes = payload["funil"], payload["motivos"], payload["mes_referencia"]
    simulacoes, pagas = funil[0]["quantidade"], funil[-1]["quantidade"]
    quadro_funil = cartao(
        f"Funil de {mes_por_extenso(mes)}",
        "Propostas criadas no mês, por etapa alcançada; à direita, a conversão sobre a etapa anterior.",
        funil_em_rampa(funil)
        + f'<p class="resumo">Da simulação ao pagamento: <strong>'
          f'{percentual_com_absoluto(payload["conversao_total"], pagas, simulacoes)}</strong>.</p>'
          f'<p class="resumo apoio">Em andamento em {data_br(payload["data_dado"])}: '
          f'{numero(payload["em_andamento"])} propostas (nem pagas, nem recusadas).</p>',
        payload["fontes"]["funil"])
    quadro_motivos = cartao(
        "Motivos de recusa",
        f"Por que as propostas criadas em {mes_abreviado(mes)} pararam; a etiqueta diz em que etapa.",
        lista_de_motivos(motivos)
        + f'<p class="resumo">Pararam antes do pagamento: <strong>'
          f'{percentual_com_absoluto(motivos["percentual_das_criadas"], motivos["total"], motivos["criadas"])}'
          f'</strong> propostas criadas no mês.</p>',
        payload["fontes"]["motivos_recusa"])
    regras = ["Cada proposta conta na etapa mais avançada que alcançou; quem chegou a uma etapa passou por todas "
              "as anteriores.",
              "A conversão de cada etapa é sobre a etapa anterior; a da simulação ao pagamento, sobre o total.",
              "Proposta assinada e ainda não paga está em andamento: não é perda e não entra nos motivos.",
              "Nos motivos, a fatia é sobre o total das propostas que pararam antes do pagamento."]
    return secao(3, "funil", "Funil de análise de crédito",
                 f'<div class="dupla">{quadro_funil}{quadro_motivos}</div>' + pe_da_secao(como_ler(regras)))


# 4. Ranking de parceiros ----------------------------------------------------------------

def tabela_ranking(ranking, com_gerente):
    """Parceiros por volume, com a barra do volume na linha; no rodapé, o canal digital (se houver) e o total."""
    titulos = ["#", "Parceiro"] + (["Gerente"] if com_gerente else [])
    numericos = ["Contratos", "Volume liberado", "Ticket médio", "Conversão do mês"]
    cabecalho = ("".join(f"<th>{t}</th>" for t in titulos)
                 + "".join(f'<th class="num">{t}</th>' for t in numericos))
    linhas_com_barra = ranking["parceiros"] + ([ranking["digital"]] if ranking["digital"] else [])
    maior = max((linha["volume"] for linha in linhas_com_barra), default=0)

    def linha(item, posicao, nome, classe="", barra=True):
        conversao = percentual_com_absoluto(item["conversao"], item["pagas"], item["simulacoes"])
        trilho = ""
        if barra and maior:
            trilho = f'<span class="trilho"><span style="width: {100 * item["volume"] / maior:.1f}%"></span></span>'
        celulas = [f'<td class="pos">{posicao}</td>', f'<td class="nome">{escape(nome)}</td>']
        if com_gerente:
            celulas.append(f"<td>{escape(item.get('gerente') or '')}</td>")
        celulas += [f'<td class="num">{numero(item["contratos"])}</td>',
                    f'<td class="num volume"><div>{trilho}<span>{moeda(item["volume"])}</span></div></td>',
                    f'<td class="num">{moeda(item["ticket_medio"])}</td>',
                    f'<td class="num">{conversao}</td>']
        atributos = f' class="{classe}"' if classe else ""
        if classe == "digital":
            atributos += ' data-canal="digital"'
        return f'<tr{atributos}>{"".join(celulas)}</tr>'

    corpo = "".join(linha(p, p["posicao"], p["parceiro"]) for p in ranking["parceiros"])
    rodape = ""
    if ranking["digital"]:
        rodape += linha(ranking["digital"], "", f"{ranking['digital']['parceiro']} (sem parceiro)", "digital")
    rodape += linha(ranking["total"], "", "Total", "total", barra=False)
    return (f'<div class="rolavel"><table class="ranking"><thead><tr>{cabecalho}</tr></thead>'
            f'<tbody>{corpo}</tbody><tfoot>{rodape}</tfoot></table></div>')


def secao_ranking(payload, diretoria):
    mes = payload["mes_referencia"]
    quadro = cartao(
        f"Parceiros em {mes_por_extenso(mes)}",
        "Ordenados pelo volume liberado no mês; a barra compara cada linha com a maior.",
        tabela_ranking(payload["ranking"], com_gerente=diretoria)
        + '<p class="secao-nota">Contratos, volume e ticket: contratos pagos no mês. Conversão: das propostas '
          "criadas no mês, quantas já foram pagas.</p>",
        payload["fontes"]["ranking_parceiros"], largo=True)
    regras = ["A posição é pelo volume liberado no mês, não pela quantidade de contratos.",
              ("O canal digital não tem parceiro nem gerente: fica no rodapé da tabela, fora da ordem, e só aparece "
               "na página da diretoria." if diretoria else
               "O total é o da carteira: soma só os parceiros desta página.")]
    return secao(4, "ranking", "Ranking de parceiros", quadro + pe_da_secao(como_ler(regras)))


# Página --------------------------------------------------------------------------------

def rodape(payload, gerada_em):
    tabelas = ", ".join(f'<code class="chip">{tabela}</code>'
                        for tabela in ("propostas", "contratos", "parceiros", "gerentes"))
    empresa = escape(payload["empresa"])
    return f"""<footer class="rodape" id="fontes">
  <div class="rodape-linha">
    <span class="rodape-marca"><span class="mono-mini" aria-hidden="true">FE</span>{empresa}</span>
    <span>Fonte: {tabelas} · SQLite local, aberto só para leitura</span>
    <span>Venda = data de pagamento · funil e conversão = data de criação da proposta</span>
  </div>
  <p>Página gerada em {gerada_em:%d/%m/%Y} às {gerada_em:%H:%M}. {empresa} é uma empresa fictícia e todos os dados
  desta página são fictícios, gerados por script. Cada número sai de uma consulta em <code>sql/</code>, aberta no
  “fonte” do quadro.</p>
</footer>"""


def gerar_html(payload, gerada_em=None):
    """A página inteira de um perfil, como texto HTML."""
    gerada_em = gerada_em or datetime.now()
    perfil = payload["perfil"]
    diretoria = perfil["gerente_id"] is None
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(payload["empresa"])} · Dashboard comercial · {escape(perfil["nome"])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="fio-topo" aria-hidden="true"></div>
{barra_lateral(payload["empresa"])}
<div class="pagina" id="topo">
{topo_da_pagina(payload, diretoria)}
{nota_do_perfil(payload, diretoria)}
<main>
{secao_originacao(payload, diretoria)}
{secao_performance(payload)}
{secao_funil(payload)}
{secao_ranking(payload, diretoria)}
</main>
{rodape(payload, gerada_em)}
</div>
</body>
</html>
"""
