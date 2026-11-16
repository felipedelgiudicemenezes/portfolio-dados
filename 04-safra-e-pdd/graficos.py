"""SVG feito à mão: eixos, linhas, barras e rampas de cor, sem biblioteca."""

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from math import ceil, floor, log10

FONTE = "Nunito, system-ui, 'Segoe UI', sans-serif"

# Tokens do visual: os mesmos do CSS do relatório.
MARCA = "#2f7189"
TEXTO = "#1e2a32"
TEXTO_2 = "#465662"
APOIO = "#626f79"
GRADE = "#e8ecf0"
EIXO = "#c6d0d8"
FUNDO = "#ffffff"
SELECAO = "#3b82f6"

# Rampa sequencial de teal, do escuro ao claro. Até o tom mais claro tem 3,3:1 contra o branco,
# o mínimo para linhas e marcas finas (há teste).
RAMPA_TEAL = ("#1b4a5c", "#235769", "#296175", "#2f6b7f", "#347388", "#387b91", "#4a97b0")


@dataclass(frozen=True)
class Serie:
    nome: str
    cor: str
    pontos: list[tuple[float, float]]
    dicas: list[str]  # texto que aparece ao passar o mouse em cada ponto


@dataclass(frozen=True)
class Barra:
    rotulo: str
    detalhe: str
    valor: float
    texto_do_valor: str
    dica: str
    cor: str = MARCA
    apoio: str = ""  # texto mais claro depois do valor, na ponta da barra


def documento(largura: int, altura: int, conteudo: str, titulo: str) -> str:
    """Envolve os elementos num <svg> com título acessível."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" '
        f'width="{largura}" height="{altura}" font-family="{FONTE}" role="img" aria-label="{escape(titulo)}">'
        f"<title>{escape(titulo)}</title>{conteudo}</svg>"
    )


def texto(x: float, y: float, conteudo: str, *, tamanho: float = 12, cor: str = APOIO,
          ancora: str = "start", negrito: bool = False) -> str:
    peso = ' font-weight="700"' if negrito else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{tamanho}" fill="{cor}" '
        f'text-anchor="{ancora}"{peso}>{escape(conteudo)}</text>'
    )


def marcas(maximo: float, intervalos: int = 5) -> list[float]:
    """Marcas redondas de 0 até cobrir `maximo` (passo de 1, 2, 2,5 ou 5 × 10ⁿ)."""
    if maximo <= 0:
        return [0.0, 1.0]
    bruto = maximo / intervalos
    potencia = 10 ** floor(log10(bruto))
    passo = next(m * potencia for m in (1, 2, 2.5, 5, 10) if m * potencia >= bruto)
    return [passo * i for i in range(ceil(maximo / passo - 1e-9) + 1)]


def _rgb(cor: str) -> tuple[int, ...]:
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def misturar(cor_a: str, cor_b: str, t: float) -> str:
    """Mistura no sRGB. Com o branco, a matiz (HSL) não muda: a cor só clareia."""
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(_rgb(cor_a), _rgb(cor_b)))


def na_rampa(paradas: tuple[str, ...], t: float) -> str:
    """Cor na posição `t` (0 a 1) de uma rampa com uma ou mais paradas intermediárias."""
    t = min(max(t, 0.0), 1.0)
    trechos = len(paradas) - 1
    trecho = min(int(t * trechos), trechos - 1)
    return misturar(paradas[trecho], paradas[trecho + 1], t * trechos - trecho)


def rampa(paradas: tuple[str, ...], quantidade: int) -> list[str]:
    """`quantidade` cores em degraus iguais, da primeira parada à última."""
    return [na_rampa(paradas, i / max(quantidade - 1, 1)) for i in range(quantidade)]


def luminancia(cor: str) -> float:
    """Luminância relativa da WCAG."""
    def canal(valor: int) -> float:
        c = valor / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(cor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(cor_a: str, cor_b: str) -> float:
    """Razão de contraste da WCAG 2, de 1 (nenhum) a 21 (preto no branco)."""
    clara, escura = sorted((luminancia(cor_a), luminancia(cor_b)), reverse=True)
    return (clara + 0.05) / (escura + 0.05)


def texto_sobre(fundo: str) -> str:
    """Branco ou tinta: o que tiver mais contraste com o fundo."""
    return FUNDO if contraste(FUNDO, fundo) >= contraste(TEXTO, fundo) else TEXTO


def painel_linhas(series: list[Serie], *, x: float, y: float, largura: float, altura: float,
                  eixo_x: tuple[int, int], rotulos_x: list[int], marcas_y: list[float],
                  formato_y: Callable[[float], str], titulo_x: str, titulo: str | None = None) -> str:
    """Gráfico de linhas com canto superior esquerdo em (x, y), devolvido como <g>.

    Sem `titulo`, o gráfico começa no alto e quem chama põe o título fora do SVG.
    """
    esquerda, direita = x + 46, x + largura - 12
    topo, base = y + (36 if titulo else 10), y + altura - 42
    x_min, x_max = eixo_x

    def px(valor: float) -> float:
        return esquerda + (valor - x_min) / (x_max - x_min) * (direita - esquerda)

    def py(valor: float) -> float:
        return base - valor / marcas_y[-1] * (base - topo)

    partes = [texto(x, y + 15, titulo, tamanho=14, cor=TEXTO, negrito=True)] if titulo else []
    for marca in marcas_y:
        cor = EIXO if marca == 0 else GRADE
        partes.append(f'<line x1="{esquerda:.1f}" x2="{direita:.1f}" y1="{py(marca):.1f}" '
                      f'y2="{py(marca):.1f}" stroke="{cor}" stroke-width="1"/>')
        partes.append(texto(esquerda - 10, py(marca) + 4, formato_y(marca), ancora="end"))
    for rotulo in rotulos_x:
        partes.append(texto(px(rotulo), base + 19, str(rotulo), ancora="middle"))
    partes.append(texto((esquerda + direita) / 2, base + 37, titulo_x, ancora="middle"))

    for serie in series:
        pontos = [(px(a), py(b)) for a, b in serie.pontos]
        caminho = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pontos)
        alvos = "".join(
            f'<circle cx="{a:.1f}" cy="{b:.1f}" r="10" fill="transparent">'
            f"<title>{escape(dica)}</title></circle>"
            for (a, b), dica in zip(pontos, serie.dicas)
        )
        fim_x, fim_y = pontos[-1]
        partes.append(
            f'<g class="serie"><path class="linha" d="{caminho}" fill="none" stroke="{serie.cor}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle class="ponta" cx="{fim_x:.1f}" cy="{fim_y:.1f}" r="4" fill="{serie.cor}" '
            f'stroke="{FUNDO}" stroke-width="2"/>{alvos}</g>'
        )
    return f"<g>{''.join(partes)}</g>"


def _barra_arredondada(x0: float, y0: float, comprimento: float, espessura: float, raio: float = 4) -> str:
    """Caminho de uma barra deitada: reta na base, cantos de 4px na ponta."""
    r = min(raio, comprimento, espessura / 2)
    x1 = x0 + comprimento
    return (
        f"M{x0:.1f},{y0:.1f} H{x1 - r:.1f} Q{x1:.1f},{y0:.1f} {x1:.1f},{y0 + r:.1f} "
        f"V{y0 + espessura - r:.1f} Q{x1:.1f},{y0 + espessura:.1f} {x1 - r:.1f},{y0 + espessura:.1f} "
        f"H{x0:.1f} Z"
    )


def barras_horizontais(barras: list[Barra], *, largura: int, marcas_x: list[float],
                       formato_x: Callable[[float], str], linha: int = 38,
                       coluna_rotulo: int = 128, espaco_valor: int = 160) -> tuple[str, int]:
    """Uma barra deitada por item, com o valor na ponta. Devolve (elementos, altura)."""
    esquerda, direita = coluna_rotulo, largura - espaco_valor
    topo = 6
    base = topo + linha * len(barras)

    def px(valor: float) -> float:
        return esquerda + valor / marcas_x[-1] * (direita - esquerda)

    partes = []
    for marca in marcas_x:
        partes.append(f'<line x1="{px(marca):.1f}" x2="{px(marca):.1f}" y1="{topo}" y2="{base}" '
                      f'stroke="{EIXO if marca == 0 else GRADE}" stroke-width="1"/>')
        partes.append(texto(px(marca), base + 19, formato_x(marca), ancora="middle"))
    espessura = 20
    for i, barra in enumerate(barras):
        y0 = topo + i * linha + (linha - espessura) / 2
        meio = y0 + espessura / 2
        partes.append(texto(0, meio + 5, barra.rotulo, tamanho=14, cor=TEXTO, negrito=True))
        partes.append(texto(20, meio + 4, barra.detalhe))
        ponta = px(barra.valor)
        partes.append(
            f'<g><path d="{_barra_arredondada(esquerda, y0, ponta - esquerda, espessura)}" fill="{barra.cor}"/>'
            f'<rect x="0" y="{y0 - 6:.1f}" width="{largura}" height="{espessura + 12}" fill="transparent">'
            f"<title>{escape(barra.dica)}</title></rect></g>"
        )
        apoio = f'<tspan fill="{APOIO}" font-weight="400"> {escape(barra.apoio)}</tspan>' if barra.apoio else ""
        partes.append(
            f'<text x="{ponta + 8:.1f}" y="{meio + 4:.1f}" font-size="12" fill="{TEXTO}" font-weight="700">'
            f"{escape(barra.texto_do_valor)}{apoio}</text>"
        )
    return "".join(partes), base + 28
