"""Camada de apresentação: transforma o payload de um perfil numa página HTML autocontida.

O CSS de estilo.css vai embutido e os gráficos são SVG gerados aqui; sem JavaScript nem
recurso externo, o arquivo abre offline e pode ser enviado como anexo.
"""

import math
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path

CSS = (Path(__file__).resolve().parent / "estilo.css").read_text(encoding="utf-8")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
ETAPAS = {"simulacao": "Simulação", "proposta": "Proposta", "analise": "Análise",
          "aprovada": "Aprovada", "assinada": "Assinada", "paga": "Paga"}


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


def percentual(valor, casas=1):
    """12.34 -> '12,3%'."""
    return "—" if valor is None else f"{numero(valor, casas)}%"


def percentual_com_absoluto(pct, parte, todo):
    """'12,3% · 98 de 800': percentual nenhum aparece sem os números de onde saiu."""
    return f"{percentual(pct)} · {numero(parte)} de {numero(todo)}"


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


KPIS = (  # chave no payload, rótulo, formato do valor, unidade da variação
    ("volume", "Volume liberado", moeda, "%"),
    ("contratos", "Contratos pagos", numero, "%"),
    ("ticket_medio", "Ticket médio", moeda, "%"),
    ("prazo_medio", "Prazo médio", em_meses, "mês"),
    ("taxa_media", "Taxa média ponderada", taxa_ao_mes, "p.p."),
)


# Gráficos em SVG ----------------------------------------------------------------------

LARGURA_GRAFICO = 1152  # gráfico de largura inteira (cartão de 1200 px menos o respiro)
LARGURA_PAINEL = 540  # gráficos dos cartões lado a lado
LARGURA_COLUNA = 24
PASSO_LINHA, ESPESSURA_BARRA = 46, 12


def _coluna(x, base, largura, altura, raio=4):
    """Coluna em pé: base reta, topo arredondado."""
    if altura <= 0:
        return ""
    r = min(raio, largura / 2, altura)
    topo = base - altura
    return (f"M{x:.1f},{base:.1f} V{topo + r:.1f} A{r},{r} 0 0 1 {x + r:.1f},{topo:.1f} "
            f"H{x + largura - r:.1f} A{r},{r} 0 0 1 {x + largura:.1f},{topo + r:.1f} V{base:.1f} Z")


def _barra(x, y, comprimento, espessura, raio=4):
    """Barra deitada: começo reto na linha de base, ponta arredondada."""
    if comprimento <= 0:
        return ""
    r = min(raio, espessura / 2, comprimento)
    fim = x + comprimento
    return (f"M{x:.1f},{y:.1f} H{fim - r:.1f} A{r},{r} 0 0 1 {fim:.1f},{y + r:.1f} "
            f"V{y + espessura - r:.1f} A{r},{r} 0 0 1 {fim - r:.1f},{y + espessura:.1f} H{x:.1f} Z")


def _passo_do_eixo(bruto):
    """Passo redondo (1; 2; 2,5 ou 5 × 10ⁿ) logo acima de `bruto`."""
    if bruto <= 0:
        return 1
    potencia = 10 ** math.floor(math.log10(bruto))
    return next(f * potencia for f in (1, 2, 2.5, 5, 10) if f * potencia >= bruto)


def grafico_vendas(serie, mes_referencia):
    """Colunas de volume por mês; o mês de referência em destaque e com o valor no topo."""
    largura, altura = LARGURA_GRAFICO, 270
    esquerda, direita, topo, rodape = 70, 4, 26, 32
    area_largura, area_altura = largura - esquerda - direita, altura - topo - rodape
    base = topo + area_altura
    maximo = max((m["volume"] for m in serie), default=0)
    passo = _passo_do_eixo(maximo / 4)
    teto = passo * max(1, math.ceil(maximo / passo))

    def y(valor):
        return base - area_altura * valor / teto

    partes = []
    for i in range(round(teto / passo) + 1):
        altura_linha = y(passo * i)
        classe = "base" if i == 0 else "grade"
        partes.append(f'<line class="{classe}" x1="{esquerda}" x2="{largura - direita}" '
                      f'y1="{altura_linha:.1f}" y2="{altura_linha:.1f}"/>'
                      f'<text x="{esquerda - 10}" y="{altura_linha + 4:.1f}" text-anchor="end">'
                      f'{moeda_compacta(passo * i)}</text>')

    faixa = area_largura / len(serie)
    com_rotulo = {mes_referencia, max(serie, key=lambda m: m["volume"])["mes"]}
    for i, item in enumerate(serie):
        centro = esquerda + faixa * (i + 0.5)
        topo_coluna = y(item["volume"])
        classe = "coluna atual" if item["mes"] == mes_referencia else "coluna"
        dica = escape(f"{mes_abreviado(item['mes'])}: {moeda(item['volume'])} · "
                      f"{numero(item['contratos'])} contratos")
        rotulo = (f'<text class="valor" x="{centro:.1f}" y="{topo_coluna - 8:.1f}" text-anchor="middle">'
                  f'{moeda_compacta(item["volume"], 2)}</text>') if item["mes"] in com_rotulo else ""
        partes.append(
            f'<g class="{classe}"><title>{dica}</title>'
            f'<rect class="alvo" x="{centro - faixa / 2:.1f}" y="0" width="{faixa:.1f}" height="{altura}"/>'
            f'<path d="{_coluna(centro - LARGURA_COLUNA / 2, base, LARGURA_COLUNA, base - topo_coluna)}"/>'
            f'{rotulo}<text class="mes" x="{centro:.1f}" y="{altura - 8}" text-anchor="middle">'
            f'{mes_curto(item["mes"])}</text></g>')
    descricao = f"Volume liberado por mês, de {mes_abreviado(serie[0]['mes'])} a {mes_abreviado(serie[-1]['mes'])}"
    return (f'<div class="rolavel"><svg class="grafico largo" viewBox="0 0 {largura} {altura}" role="img" '
            f'aria-label="{descricao}">{"".join(partes)}</svg></div>')


def _barras_horizontais(linhas, classe, descricao):
    """Uma linha por item: rótulo e números em cima, barra embaixo sobre um trilho de 100%."""
    partes = []
    for i, linha in enumerate(linhas):
        y = i * PASSO_LINHA
        comprimento = LARGURA_PAINEL * min(max(linha["fracao"], 0), 1)
        partes.append(
            f'<g class="{linha.get("classe", "")}"><title>{escape(linha["dica"])}</title>'
            f'<rect class="alvo" x="0" y="{y}" width="{LARGURA_PAINEL}" height="{PASSO_LINHA}"/>'
            f'<text class="rotulo" x="0" y="{y + 15}">{linha["rotulo"]}</text>'
            f'<text class="numeros" x="{LARGURA_PAINEL}" y="{y + 15}" text-anchor="end">'
            f'{escape(linha["numeros"])}</text>'
            f'<rect class="trilho" x="0" y="{y + 23}" width="{LARGURA_PAINEL}" height="{ESPESSURA_BARRA}" rx="4"/>'
            f'<path class="barra" d="{_barra(0, y + 23, comprimento, ESPESSURA_BARRA)}"/></g>')
    altura = PASSO_LINHA * (len(linhas) - 1) + 23 + ESPESSURA_BARRA
    return (f'<svg class="grafico {classe}" viewBox="0 0 {LARGURA_PAINEL} {altura}" role="img" '
            f'aria-label="{escape(descricao)}">{"".join(partes)}</svg>')


def grafico_funil(funil):
    """Funil em barras deitadas: comprimento pelo total de simulações, texto com a conversão."""
    simulacoes = funil[0]["quantidade"]
    linhas = []
    for etapa in funil:
        nome = ETAPAS[etapa["etapa"]]
        if etapa["base"] is None:
            numeros = f"{numero(etapa['quantidade'])} simulações"
        else:
            numeros = percentual_com_absoluto(etapa["conversao"], etapa["quantidade"], etapa["base"])
        linhas.append({"rotulo": escape(nome), "numeros": numeros, "dica": f"{nome}: {numeros}",
                       "fracao": etapa["quantidade"] / simulacoes if simulacoes else 0,
                       "classe": "final" if etapa["etapa"] == "paga" else ""})
    return _barras_horizontais(linhas, "funil", "Funil do mês, da simulação ao pagamento")


def grafico_motivos(motivos):
    """Motivos em ordem de quantidade; a barra é a fatia do total de propostas que pararam."""
    if not motivos["itens"]:
        return '<p class="resumo">Nenhuma proposta criada no mês parou antes do pagamento.</p>'
    linhas = []
    for item in motivos["itens"]:
        numeros = percentual_com_absoluto(item["percentual"], item["quantidade"], motivos["total"])
        etapa = ETAPAS[item["parou_em"]]
        linhas.append({"rotulo": f'{escape(item["motivo"])}<tspan class="etapa" dx="8">{etapa.upper()}</tspan>',
                       "numeros": numeros, "dica": f"{item['motivo']} (parou em {etapa}): {numeros}",
                       "fracao": (item["percentual"] or 0) / 100})
    return _barras_horizontais(linhas, "motivos", "Motivos de recusa do mês")


# Blocos da página ---------------------------------------------------------------------

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
    """O <details> "fonte": arquivo, parâmetros, o SQL e as linhas que a consulta devolveu."""
    parametros = " · ".join(f":{nome} = {_literal_sql(valor)}" for nome, valor in fonte["parametros"].items())
    linhas = fonte["linhas"]
    tabela = _tabela_de_linhas(linhas) if linhas else ""
    plural = "linha" if len(linhas) == 1 else "linhas"
    return (f'<details class="fonte"><summary>fonte</summary>'
            f'<p class="fonte-meta"><code>{escape(fonte["arquivo"])}</code> · parâmetros: '
            f'{escape(parametros or "nenhum")}</p>'
            f'<pre><code>{escape(fonte["sql"].strip())}</code></pre>'
            f'<p class="fonte-meta">A consulta devolveu {numero(len(linhas))} {plural}:</p>{tabela}</details>')


def cartao(titulo, subtitulo, corpo, fonte):
    """Um quadro: título, subtítulo, conteúdo e, no pé, o "fonte" da consulta que o alimenta."""
    return (f'<section class="cartao"><h2>{escape(titulo)}</h2><p class="sub">{subtitulo}</p>'
            f'<div class="corpo">{corpo}</div>{bloco_fonte(fonte)}</section>')


def linha_de_kpis(payload):
    """Os cinco indicadores do mês, cada um com a variação e o valor do mês anterior."""
    anterior = payload["mes_anterior"]
    blocos = []
    for chave, rotulo, formatar, unidade in KPIS:
        kpi = payload["kpis"][chave]
        base = f"{mes_abreviado(anterior)}: {formatar(kpi['anterior'])}" if anterior else ""
        classe = "kpi destaque" if chave == "volume" else "kpi"
        blocos.append(f'<div class="{classe}"><div class="kpi-rotulo">{rotulo}</div>'
                      f'<div class="kpi-valor">{formatar(kpi["atual"])}</div>'
                      f'<div class="kpi-var">{texto_variacao(kpi["variacao"], unidade)}</div>'
                      f'<div class="kpi-base">{base}</div></div>')
    return f'<div class="kpis">{"".join(blocos)}</div>'


def tabela_ranking(ranking, com_gerente):
    """Parceiros por volume; no rodapé, o canal digital (se o perfil o recebe) e o total."""
    titulos = ["#", "Parceiro"] + (["Gerente"] if com_gerente else [])
    numericos = ["Contratos", "Volume liberado", "Ticket médio", "Conversão do mês"]
    cabecalho = ("".join(f"<th>{t}</th>" for t in titulos)
                 + "".join(f'<th class="num">{t}</th>' for t in numericos))

    def linha(item, posicao, nome, classe=""):
        conversao = percentual_com_absoluto(item["conversao"], item["pagas"], item["simulacoes"])
        celulas = [f'<td class="pos">{posicao}</td>', f"<td>{escape(nome)}</td>"]
        if com_gerente:
            celulas.append(f"<td>{escape(item.get('gerente') or '')}</td>")
        celulas += [f'<td class="num">{numero(item["contratos"])}</td>',
                    f'<td class="num">{moeda(item["volume"])}</td>',
                    f'<td class="num">{moeda(item["ticket_medio"])}</td>',
                    f'<td class="num">{conversao}</td>']
        return f'<tr class="{classe}">{"".join(celulas)}</tr>'

    corpo = "".join(linha(p, p["posicao"], p["parceiro"]) for p in ranking["parceiros"])
    rodape = ""
    if ranking["digital"]:
        rodape += linha(ranking["digital"], "", f"{ranking['digital']['parceiro']} (sem parceiro)", "digital")
    rodape += linha(ranking["total"], "", "Total", "total")
    return (f'<div class="rolavel"><table class="ranking"><thead><tr>{cabecalho}</tr></thead>'
            f'<tbody>{corpo}</tbody><tfoot>{rodape}</tfoot></table></div>')


def gerar_html(payload, gerada_em=None):
    """A página inteira de um perfil, como texto HTML."""
    gerada_em = gerada_em or datetime.now()
    perfil, fontes, ranking = payload["perfil"], payload["fontes"], payload["ranking"]
    mes, anterior, serie = payload["mes_referencia"], payload["mes_anterior"], payload["vendas_por_mes"]
    funil, motivos = payload["funil"], payload["motivos"]
    simulacoes, pagas = funil[0]["quantidade"], funil[-1]["quantidade"]
    diretoria = perfil["gerente_id"] is None
    quantos = len(ranking["parceiros"])
    escopo = f"canal digital e {quantos} parceiros" if diretoria else f"carteira com {quantos} parceiros"

    comparacao = f", comparados com {mes_por_extenso(anterior)}" if anterior else ""
    secao_kpis = cartao(f"Resultado de {mes_por_extenso(mes)}",
                        f"Contratos pagos no mês (pela data de pagamento){comparacao}.",
                        linha_de_kpis(payload), fontes["vendas_por_mes"])
    secao_vendas = cartao("Volume liberado por mês",
                          f"Contratos pagos de {mes_abreviado(serie[0]['mes'])} a {mes_abreviado(serie[-1]['mes'])}. "
                          "Em bronze, o mês de referência; passe o mouse numa coluna para ver o valor exato.",
                          grafico_vendas(serie, mes), fontes["vendas_por_mes"])
    secao_funil = cartao(
        f"Funil de {mes_por_extenso(mes)}",
        "Propostas criadas no mês; à direita, a conversão sobre a etapa anterior.",
        grafico_funil(funil)
        + f'<p class="resumo">Da simulação ao pagamento: <strong>'
          f'{percentual_com_absoluto(payload["conversao_total"], pagas, simulacoes)}</strong></p>'
          f'<p class="resumo">Em andamento em {data_br(payload["data_dado"])}: '
          f'{numero(payload["em_andamento"])} propostas (nem pagas, nem recusadas).</p>',
        fontes["funil"])
    secao_motivos = cartao(
        "Motivos de recusa",
        f"Por que as propostas criadas em {mes_abreviado(mes)} pararam; a etiqueta diz em que etapa.",
        grafico_motivos(motivos)
        + f'<p class="resumo">Pararam antes do pagamento: <strong>'
          f'{percentual_com_absoluto(motivos["percentual_das_criadas"], motivos["total"], motivos["criadas"])}'
          f'</strong> propostas criadas no mês.</p>',
        fontes["motivos_recusa"])
    secao_ranking = cartao(
        f"Ranking de parceiros em {mes_por_extenso(mes)}",
        "Ordenado pelo volume liberado no mês.",
        tabela_ranking(ranking, com_gerente=diretoria)
        + '<p class="nota">Contratos, volume e ticket: contratos pagos no mês. Conversão: das propostas '
          "criadas no mês, quantas já foram pagas.</p>",
        fontes["ranking_parceiros"])

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(payload["empresa"])} · Dashboard comercial · {escape(perfil["nome"])}</title>
<style>{CSS}</style>
</head>
<body>
<header class="topo">
  <div class="topo-conteudo">
    <div>
      <p class="marca">{escape(payload["empresa"])} · crédito consignado</p>
      <h1>Dashboard comercial</h1>
      <p class="datas">Mês de referência: <strong>{mes_por_extenso(mes)}</strong>
        · dados até {data_br(payload["data_dado"])}
        · página gerada em {gerada_em:%d/%m/%Y} às {gerada_em:%H:%M}</p>
    </div>
    <div class="perfil"><small>Perfil</small><strong>{escape(perfil["nome"])}</strong><span>{escopo}</span></div>
  </div>
</header>
<main>
{secao_kpis}
{secao_vendas}
<div class="dupla">
{secao_funil}
{secao_motivos}
</div>
{secao_ranking}
</main>
<footer>
  <p>{escape(payload["empresa"])} é uma empresa fictícia e todos os dados desta página são fictícios,
  gerados por script. Cada número sai de uma consulta em <code>sql/</code>, aberta no “fonte” do quadro.</p>
</footer>
</body>
</html>
"""
