"""Curvas de safra (vintage): quanto de cada safra já ficou 30, 60 ou 90 dias em atraso.

"Ever": o contrato passa a contar no mês em que alguma parcela completou o atraso
e continua contando mesmo que depois pague. Por isso as curvas nunca descem.
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from operator import itemgetter

import graficos
from comum import (SAIDA, abrir_banco, data_br, de_centavos, fim_do_mes, ler_data_base, mes_ano,
                   meses_entre, numero, parte_de, percentual, somar_meses)

ATRASOS = (30, 60, 90)
CORES_DAS_SAFRAS = graficos.RAMPA_TEAL[::-1]  # rampa de teal: da safra mais antiga (clara) à mais nova (escura)


@dataclass(frozen=True)
class Contrato:
    safra: date  # 1º dia do mês de originação
    valor: Decimal
    atingiu: dict[int, date | None]  # dias de atraso -> dia em que completou (None: nunca)


@dataclass(frozen=True)
class Ponto:
    """Uma safra ao fim de um mês de vida (MOB)."""
    mob: int
    contratos: int
    total_contratos: int
    valor: Decimal
    total_valor: Decimal

    @property
    def fracao_contratos(self) -> float:
        return self.contratos / self.total_contratos

    @property
    def fracao_valor(self) -> float:
        return float(self.valor / self.total_valor)


@dataclass(frozen=True)
class Safra:
    inicio: date
    contratos: int
    valor: Decimal
    curvas: dict[int, list[Ponto]]  # dias de atraso -> um ponto por MOB, do 0 até a data-base


def dia_em_que_atingiu(parcelas: list[tuple[date, date | None]], dias: int, data_base: date) -> date | None:
    """Primeiro dia em que alguma parcela completou `dias` de atraso, até a data-base.

    `parcelas`: pares (vencimento, pagamento) em ordem de vencimento; pagamento None = em aberto.
    Pagar exatamente no dia em que completa conta como atraso de `dias`.
    """
    for vencimento, pagamento in parcelas:
        marco = vencimento + timedelta(days=dias)
        if marco > data_base:
            return None
        if pagamento is None or pagamento >= marco:
            return marco
    return None


def montar_curvas(contratos: list[Contrato], data_base: date) -> list[Safra]:
    """Agrupa por safra e conta, ao fim de cada MOB, quem já tinha atingido cada atraso."""
    por_safra = defaultdict(list)
    for contrato in contratos:
        por_safra[contrato.safra].append(contrato)

    safras = []
    for inicio, grupo in sorted(por_safra.items()):
        total_valor = sum((c.valor for c in grupo), Decimal(0))
        curvas = {}
        for dias in ATRASOS:
            curvas[dias] = []
            for mob in range(meses_entre(inicio, data_base) + 1):
                fim = fim_do_mes(somar_meses(inicio, mob))
                atingiram = [c for c in grupo if c.atingiu[dias] is not None and c.atingiu[dias] <= fim]
                valor = sum((c.valor for c in atingiram), Decimal(0))
                curvas[dias].append(Ponto(mob, len(atingiram), len(grupo), valor, total_valor))
        safras.append(Safra(inicio, len(grupo), total_valor, curvas))
    return safras


def carregar(conexao: sqlite3.Connection) -> tuple[date, list[Contrato]]:
    """Lê contratos e parcelas já vencidas e marca quando cada contrato atingiu 30, 60 e 90 dias."""
    data_base = ler_data_base(conexao)
    linhas = conexao.execute(
        """
        SELECT c.id, c.data_originacao, c.valor_liberado_centavos, p.vencimento, p.data_pagamento
        FROM contratos AS c
        LEFT JOIN parcelas AS p ON p.contrato_id = c.id AND p.vencimento <= :data_base
        ORDER BY c.id, p.numero
        """,
        {"data_base": data_base.isoformat()},
    )
    contratos = []
    for _, grupo in groupby(linhas, key=itemgetter(0)):
        grupo = list(grupo)
        _, originacao, valor, _, _ = grupo[0]
        parcelas = [
            (date.fromisoformat(vencimento), date.fromisoformat(pago) if pago else None)
            for *_, vencimento, pago in grupo
            if vencimento
        ]
        contratos.append(Contrato(
            safra=date.fromisoformat(originacao).replace(day=1),
            valor=de_centavos(valor),
            atingiu={dias: dia_em_que_atingiu(parcelas, dias, data_base) for dias in ATRASOS},
        ))
    return data_base, contratos


def calcular(conexao: sqlite3.Connection) -> tuple[date, list[Safra]]:
    data_base, contratos = carregar(conexao)
    return data_base, montar_curvas(contratos, data_base)


def acumulado(safras: list[Safra], dias: int, mob: int) -> tuple[int, int]:
    """(contratos que atingiram `dias` até o `mob`, total de contratos), somando as safras dadas."""
    pontos = [s.curvas[dias][mob] for s in safras]
    return sum(p.contratos for p in pontos), sum(p.total_contratos for p in pontos)


def cores_das_safras(safras: list[Safra]) -> list[str]:
    """Uma cor por safra, na rampa de teal: a mais antiga é a mais clara."""
    return graficos.rampa(CORES_DAS_SAFRAS, len(safras))


def painel(safras: list[Safra], dias: int, *, x: float, y: float, largura: float, altura: float,
           titulo: str | None = None) -> str:
    """As curvas de um atraso (30, 60 ou 90 dias), uma linha por safra, como <g>.

    O eixo vertical é o mesmo nos três atrasos (vai até o maior 30+), para os painéis se compararem.
    """
    mob_maximo = max(len(s.curvas[ATRASOS[0]]) for s in safras) - 1
    maior = max(p.fracao_contratos for s in safras for p in s.curvas[ATRASOS[0]])
    marcas_y = graficos.marcas(maior)
    casas = 0 if all(round(m * 100, 9).is_integer() for m in marcas_y) else 1
    series = []
    for s, cor in zip(safras, cores_das_safras(safras)):
        pontos = s.curvas[dias][1:]
        if not pontos:
            continue
        series.append(graficos.Serie(
            nome=mes_ano(s.inicio),
            cor=cor,
            pontos=[(p.mob, p.fracao_contratos) for p in pontos],
            dicas=[f"Safra {mes_ano(s.inicio)} · MOB {p.mob}: "
                   f"{parte_de(p.contratos, p.total_contratos)} contratos" for p in pontos],
        ))
    return graficos.painel_linhas(
        series, x=x, y=y, largura=largura, altura=altura, titulo=titulo,
        eixo_x=(1, mob_maximo), rotulos_x=list(range(1, mob_maximo + 1, 2)),
        marcas_y=marcas_y, formato_y=lambda v: percentual(v, casas),
        titulo_x="meses de vida da safra (MOB)",
    )


def svg_painel(safras: list[Safra], dias: int, largura: int = 360, altura: int = 260) -> str:
    """Um painel só, sem título (no relatório, o título fica no cartão)."""
    return graficos.documento(
        largura, altura, painel(safras, dias, x=0, y=0, largura=largura, altura=altura),
        f"Curvas de safra: % dos contratos de cada safra que já tiveram parcela com {dias} dias "
        "ou mais de atraso, por mês de vida",
    )


def svg_curvas(safras: list[Safra]) -> str:
    """Três painéis (30, 60 e 90 dias) com uma linha por safra e a legenda das cores."""
    largura, alto_legenda, alto_painel, espaco = 1200, 64, 330, 30
    largura_painel = (largura - 2 * espaco) / 3
    partes = [graficos.texto(0, 14, "Safra (mês de originação)", cor=graficos.TEXTO, negrito=True),
              graficos.texto(0, 32, "da mais antiga (clara) à mais nova (escura)")]
    passo = 52
    inicio_legenda = largura - passo * len(safras)
    for i, (s, cor) in enumerate(zip(safras, cores_das_safras(safras))):
        x = inicio_legenda + i * passo
        partes.append(f'<rect x="{x:.1f}" y="4" width="{passo - 2}" height="6" rx="3" fill="{cor}"/>')
        partes.append(graficos.texto(x + (passo - 2) / 2, 28, mes_ano(s.inicio), ancora="middle",
                                     cor=graficos.TEXTO_2))
    for indice, dias in enumerate(ATRASOS):
        partes.append(painel(safras, dias, x=indice * (largura_painel + espaco), y=alto_legenda,
                             largura=largura_painel, altura=alto_painel,
                             titulo=f"{dias} dias ou mais de atraso"))
    estilo = (f"<style>.serie:hover .linha{{stroke:{graficos.SELECAO};stroke-width:3}}"
              f".serie:hover .ponta{{fill:{graficos.SELECAO}}}</style>")
    return graficos.documento(
        largura, alto_legenda + alto_painel, f'<rect width="100%" height="100%" fill="{graficos.FUNDO}"/>'
        + estilo + "".join(partes),
        "Curvas de safra: % dos contratos que já tiveram parcela com 30, 60 ou 90 dias ou mais de atraso",
    )


def tabela_texto(safras: list[Safra], dias: int = 30) -> str:
    """Matriz safra × MOB (% dos contratos) para o terminal."""
    mob_maximo = max(len(s.curvas[dias]) for s in safras) - 1
    linhas = [f"{'safra':<8}{'contratos':>10}" + "".join(f"{m:>7}" for m in range(1, mob_maximo + 1))]
    for s in safras:
        celulas = "".join(f"{percentual(p.fracao_contratos):>7}" for p in s.curvas[dias][1:])
        linhas.append(f"{mes_ano(s.inicio):<8}{numero(s.contratos):>10}{celulas}")
    return "\n".join(linhas)


def main() -> None:
    with abrir_banco() as conexao:
        data_base, safras = calcular(conexao)
    print("% dos contratos de cada safra que já tiveram parcela com 30 dias ou mais de atraso,")
    print(f"por mês de vida (MOB) — data-base {data_br(data_base)}\n")
    print(tabela_texto(safras))
    SAIDA.mkdir(exist_ok=True)
    destino = SAIDA / "curvas_safra.svg"
    destino.write_text(svg_curvas(safras), encoding="utf-8")
    print(f"\nGráfico gravado em {destino}")


if __name__ == "__main__":
    main()
