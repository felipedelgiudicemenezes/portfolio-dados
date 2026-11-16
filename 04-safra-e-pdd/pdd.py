"""PDD na data-base pela tabela de referência da Resolução CMN 2.682/99 (só para estudo).

O contrato inteiro vai para a faixa da parcela mais atrasada (arrasto), e o percentual
da faixa incide sobre o saldo devedor: parcelas a vencer trazidas a valor presente pela
taxa do contrato mais as parcelas vencidas em aberto, pelo valor de face.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import groupby
from operator import itemgetter

import graficos
from comum import (SAIDA, abrir_banco, centavos, data_br, de_centavos, ler_data_base, moeda, moeda_curta,
                   numero, percentual)


@dataclass(frozen=True)
class Faixa:
    nivel: str
    de: int
    ate: int | None  # None: sem limite
    provisao: Decimal

    @property
    def descricao(self) -> str:
        if self.de == 0:
            return f"em dia ou até {self.ate} dias"
        if self.ate is None:
            return f"mais de {self.de - 1} dias"
        return f"{self.de} a {self.ate} dias"


FAIXAS = (
    Faixa("A", 0, 14, Decimal("0.005")),
    Faixa("B", 15, 30, Decimal("0.01")),
    Faixa("C", 31, 60, Decimal("0.03")),
    Faixa("D", 61, 90, Decimal("0.10")),
    Faixa("E", 91, 120, Decimal("0.30")),
    Faixa("F", 121, 150, Decimal("0.50")),
    Faixa("G", 151, 180, Decimal("0.70")),
    Faixa("H", 181, None, Decimal("1.00")),
)


@dataclass(frozen=True)
class Avaliacao:
    """Um contrato em aberto na data-base."""
    atraso: int
    faixa: Faixa
    saldo: Decimal
    pdd: Decimal


@dataclass(frozen=True)
class LinhaDaFaixa:
    faixa: Faixa
    contratos: int
    saldo: Decimal
    pdd: Decimal


def classificar(dias_de_atraso: int) -> Faixa:
    if dias_de_atraso < 0:
        raise ValueError("dias de atraso não pode ser negativo")
    return next(f for f in FAIXAS if f.ate is None or dias_de_atraso <= f.ate)


def pior_atraso(parcelas_em_aberto: list[tuple[date, Decimal]], data_base: date) -> int:
    """Dias de atraso da parcela em aberto mais antiga (0 se nenhuma venceu)."""
    return max([0, *((data_base - vencimento).days for vencimento, _ in parcelas_em_aberto)])


def saldo_devedor(parcelas_em_aberto: list[tuple[date, Decimal]], taxa: Decimal, data_base: date) -> Decimal:
    """Vencidas pelo valor de face + a vencer descontadas a (1 + taxa) ^ (dias corridos / 30)."""
    fator_diario = (1 + taxa) ** (Decimal(1) / 30)  # (1 + taxa) ^ (dias / 30) = fator_diario ^ dias
    total = Decimal(0)
    for vencimento, valor in parcelas_em_aberto:
        dias = (vencimento - data_base).days
        total += valor if dias <= 0 else valor / fator_diario ** dias
    return centavos(total)


def avaliar(parcelas_em_aberto: list[tuple[date, Decimal]], taxa: Decimal, data_base: date) -> Avaliacao:
    """Classifica o contrato pelo pior atraso e calcula saldo e PDD (arredondados ao centavo)."""
    atraso = pior_atraso(parcelas_em_aberto, data_base)
    faixa = classificar(atraso)
    saldo = saldo_devedor(parcelas_em_aberto, taxa, data_base)
    return Avaliacao(atraso, faixa, saldo, centavos(saldo * faixa.provisao))


def carregar(conexao: sqlite3.Connection) -> tuple[date, list[Avaliacao]]:
    """Avalia cada contrato que ainda tem parcela em aberto na data-base."""
    data_base = ler_data_base(conexao)
    linhas = conexao.execute(
        """
        SELECT c.id, c.taxa_mensal, p.vencimento, p.valor_centavos
        FROM contratos AS c
        JOIN parcelas AS p ON p.contrato_id = c.id
        WHERE p.data_pagamento IS NULL OR p.data_pagamento > :data_base
        ORDER BY c.id, p.numero
        """,
        {"data_base": data_base.isoformat()},
    )
    avaliacoes = []
    for _, grupo in groupby(linhas, key=itemgetter(0)):
        grupo = list(grupo)
        parcelas = [(date.fromisoformat(vencimento), de_centavos(valor)) for _, _, vencimento, valor in grupo]
        avaliacoes.append(avaliar(parcelas, Decimal(grupo[0][1]), data_base))
    return data_base, avaliacoes


def por_faixa(avaliacoes: list[Avaliacao]) -> list[LinhaDaFaixa]:
    linhas = []
    for faixa in FAIXAS:
        grupo = [a for a in avaliacoes if a.faixa == faixa]
        saldo = sum((a.saldo for a in grupo), Decimal(0))
        provisao = sum((a.pdd for a in grupo), Decimal(0))
        linhas.append(LinhaDaFaixa(faixa, len(grupo), saldo, provisao))
    return linhas


def calcular(conexao: sqlite3.Connection) -> tuple[date, list[LinhaDaFaixa]]:
    data_base, avaliacoes = carregar(conexao)
    return data_base, por_faixa(avaliacoes)


def svg_pdd(linhas: list[LinhaDaFaixa], largura: int = 520) -> str:
    """Barras deitadas com a PDD de cada faixa e a fatia de cada uma no total."""
    total = sum(linha.pdd for linha in linhas)
    barras = []
    for linha in linhas:
        faixa = linha.faixa
        barras.append(graficos.Barra(
            rotulo=faixa.nivel,
            detalhe=faixa.descricao.removeprefix("em dia ou "),
            valor=float(linha.pdd),
            texto_do_valor=f"{moeda_curta(linha.pdd)} · {percentual(linha.pdd / total if total else 0)}",
            dica=(f"Faixa {faixa.nivel} ({faixa.descricao}): {numero(linha.contratos)} contratos, "
                  f"saldo {moeda(linha.saldo)}, PDD {moeda(linha.pdd)}"),
        ))
    conteudo, altura = graficos.barras_horizontais(
        barras, largura=largura,
        marcas_x=graficos.marcas(max(b.valor for b in barras), intervalos=3),
        formato_x=lambda valor: moeda_curta(Decimal(str(valor)), enxuto=True),
    )
    return graficos.documento(largura, altura, conteudo, "PDD por faixa de atraso, em reais")


def tabela_texto(linhas: list[LinhaDaFaixa]) -> str:
    cabecalho = f"{'faixa':<6}{'atraso':<24}{'provisão':>9}{'contratos':>11}{'saldo devedor':>20}{'PDD':>17}"
    corpo = []
    for linha in linhas:
        provisao = percentual(linha.faixa.provisao, 1, enxuto=True)
        corpo.append(f"{linha.faixa.nivel:<6}{linha.faixa.descricao:<24}{provisao:>9}"
                     f"{numero(linha.contratos):>11}{moeda(linha.saldo):>20}{moeda(linha.pdd):>17}")
    contratos = sum(linha.contratos for linha in linhas)
    saldo = sum(linha.saldo for linha in linhas)
    pdd = sum(linha.pdd for linha in linhas)
    total = (f"{'total':<30}{percentual(pdd / saldo):>9}{numero(contratos):>11}"
             f"{moeda(saldo):>20}{moeda(pdd):>17}")
    return "\n".join([cabecalho, *corpo, total])


def main() -> None:
    with abrir_banco() as conexao:
        data_base, linhas = calcular(conexao)
    print(f"PDD por faixa de atraso na data-base {data_br(data_base)} (tabela de referência da 2.682)\n")
    print(tabela_texto(linhas))
    SAIDA.mkdir(exist_ok=True)
    destino = SAIDA / "pdd_por_faixa.svg"
    destino.write_text(svg_pdd(linhas), encoding="utf-8")
    print(f"\nGráfico gravado em {destino}")


if __name__ == "__main__":
    main()
