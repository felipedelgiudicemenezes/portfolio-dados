"""Gera dados/carteira.sqlite: contratos de consignado, parcelas pela tabela Price e pagamentos.

Tudo sai de random.Random(42): rodar de novo produz exatamente a mesma carteira.
O banco é a "foto" da carteira na data-base: pagamento depois dela não aparece.
"""

import random
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
from math import log
from pathlib import Path

from comum import BANCO, centavos, data_br, fim_do_mes, numero, para_centavos, somar_meses

SEMENTE = 42
PRIMEIRA_SAFRA = date(2025, 1, 1)
QUANTIDADE_DE_SAFRAS = 18
DATA_BASE = fim_do_mes(somar_meses(PRIMEIRA_SAFRA, QUANTIDADE_DE_SAFRAS - 1))

PRAZOS = (12, 18, 24, 36, 48)
PESOS_DOS_PRAZOS = (10, 15, 30, 30, 15)
RISCO_MENSAL = 0.007  # chance de perder o emprego antes de cada vencimento, na 1ª safra
PIORA_POR_SAFRA = 0.08  # a carteira cresce afrouxando o critério: cada safra sai um pouco pior
CHANCE_DE_RECUPERAR = 0.5  # novo emprego ou acordo; quita os atrasados de uma vez
DIAS_MEDIOS_PARA_RECUPERAR = 45

ESQUEMA = """
CREATE TABLE parametros (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE contratos (
    id INTEGER PRIMARY KEY,
    data_originacao TEXT NOT NULL,
    valor_liberado_centavos INTEGER NOT NULL,
    prazo_meses INTEGER NOT NULL,
    taxa_mensal TEXT NOT NULL
);
CREATE TABLE parcelas (
    contrato_id INTEGER NOT NULL REFERENCES contratos (id),
    numero INTEGER NOT NULL,
    vencimento TEXT NOT NULL,
    valor_centavos INTEGER NOT NULL,
    juros_centavos INTEGER NOT NULL,
    amortizacao_centavos INTEGER NOT NULL,
    data_pagamento TEXT,  -- NULL: em aberto na data-base
    PRIMARY KEY (contrato_id, numero)
);
"""


def tabela_price(principal: Decimal, taxa: Decimal, prazo: int) -> list[tuple[Decimal, Decimal, Decimal]]:
    """Parcelas (valor, juros, amortização) da tabela Price, em centavos.

    Os juros de cada mês são arredondados; a última parcela absorve a sobra,
    para a soma das amortizações fechar o principal exatamente.
    """
    prestacao = centavos(principal * taxa / (1 - (1 + taxa) ** -prazo))
    saldo = principal
    parcelas = []
    for numero_da_parcela in range(1, prazo + 1):
        juros = centavos(saldo * taxa)
        amortizacao = saldo if numero_da_parcela == prazo else prestacao - juros
        parcelas.append((juros + amortizacao, juros, amortizacao))
        saldo -= amortizacao
    return parcelas


def primeiro_vencimento(originacao: date, dia: int) -> date:
    """Primeiro dia `dia` de um mês que fica a pelo menos 30 dias da originação."""
    minimo = originacao + timedelta(days=30)
    vencimento = minimo.replace(day=dia)
    return vencimento if vencimento >= minimo else somar_meses(vencimento, 1)


def simular_pagamentos(vencimentos: list[date], risco: float, rng: random.Random) -> list[date | None]:
    """Data de pagamento de cada parcela (None se nunca for paga).

    Com o desconto em folha, paga no vencimento. Se o cliente perde o emprego antes
    de um vencimento, os descontos param; parte volta a pagar semanas depois.
    """
    pagamentos: list[date | None] = [None] * len(vencimentos)
    atual = 0
    while atual < len(vencimentos):
        if rng.random() >= risco:
            pagamentos[atual] = vencimentos[atual]
            atual += 1
            continue
        if rng.random() >= CHANCE_DE_RECUPERAR:
            break
        espera = 3 + round(rng.expovariate(1 / DIAS_MEDIOS_PARA_RECUPERAR))
        volta = vencimentos[atual] + timedelta(days=espera)
        while atual < len(vencimentos) and vencimentos[atual] <= volta:
            pagamentos[atual] = volta
            atual += 1
    return pagamentos


def gerar(caminho: Path = BANCO) -> tuple[int, int]:
    """Grava a carteira em `caminho` (apaga a anterior) e devolve (contratos, parcelas)."""
    rng = random.Random(SEMENTE)
    contratos, parcelas = [], []
    for indice in range(QUANTIDADE_DE_SAFRAS):
        inicio = somar_meses(PRIMEIRA_SAFRA, indice)
        risco = RISCO_MENSAL * (1 + PIORA_POR_SAFRA * indice)
        for _ in range(350 + 10 * indice + rng.randint(-30, 30)):
            contrato_id = len(contratos) + 1
            originacao = inicio + timedelta(days=rng.randrange(fim_do_mes(inicio).day))
            valor = Decimal(100 * min(max(round(rng.lognormvariate(log(45), 0.6)), 10), 300))
            prazo = rng.choices(PRAZOS, PESOS_DOS_PRAZOS)[0]
            taxa = Decimal(rng.randint(160, 340)) / 10_000
            primeiro = primeiro_vencimento(originacao, rng.randint(1, 28))
            vencimentos = [somar_meses(primeiro, n) for n in range(prazo)]
            pagamentos = simular_pagamentos(vencimentos, risco, rng)
            contratos.append((contrato_id, originacao.isoformat(), para_centavos(valor), prazo, str(taxa)))
            for numero_da_parcela, (vencimento, pagamento, (valor_parcela, juros, amortizacao)) in enumerate(
                zip(vencimentos, pagamentos, tabela_price(valor, taxa, prazo)), start=1
            ):
                pago = pagamento.isoformat() if pagamento and pagamento <= DATA_BASE else None
                parcelas.append((
                    contrato_id, numero_da_parcela, vencimento.isoformat(), para_centavos(valor_parcela),
                    para_centavos(juros), para_centavos(amortizacao), pago,
                ))

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.unlink(missing_ok=True)
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.executescript(ESQUEMA)
        conexao.executemany(
            "INSERT INTO parametros VALUES (?, ?)",
            [("data_base", DATA_BASE.isoformat()), ("semente", str(SEMENTE))],
        )
        conexao.executemany("INSERT INTO contratos VALUES (?, ?, ?, ?, ?)", contratos)
        conexao.executemany("INSERT INTO parcelas VALUES (?, ?, ?, ?, ?, ?, ?)", parcelas)
        conexao.commit()
    return len(contratos), len(parcelas)


if __name__ == "__main__":
    total_contratos, total_parcelas = gerar()
    print(
        f"{numero(total_contratos)} contratos e {numero(total_parcelas)} parcelas "
        f"gravados em {BANCO} (data-base {data_br(DATA_BASE)})"
    )
