"""Gera a base fictícia da Fintech Exemplo em dados/base.sqlite.

Doze meses de simulações de crédito consignado vindas do canal digital e de nove
correspondentes (parceiros), com sazonalidade, crescimento e conversão diferentes
por origem. A semente é fixa: a base sai idêntica em toda execução.

Uso: python gerar_base.py
"""

import math
import random
import sqlite3
import time
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

PASTA = Path(__file__).resolve().parent
CAMINHO_BASE = PASTA / "dados" / "base.sqlite"
SEMENTE = 42
INICIO = date(2025, 11, 1)
FIM = date(2026, 10, 31)  # data de corte: nada acontece depois dela

ETAPAS = ("simulacao", "proposta", "analise", "aprovada", "assinada", "paga")
AVANCO = {  # chance de passar de cada etapa para a seguinte
    "simulacao": 0.50,
    "proposta": 0.86,
    "analise": 0.66,
    "aprovada": 0.89,
    "assinada": 0.965,
}
MOTIVOS = {  # por que a proposta parou em cada etapa: (motivo, peso)
    "simulacao": (("Não seguiu após simular", 0.62), ("Sem margem consignável", 0.38)),
    "proposta": (("Documentação incompleta", 1.0),),
    "analise": (("Reprovada na política de crédito", 0.72), ("Empregador sem convênio", 0.28)),
    "aprovada": (("Não assinou no prazo", 1.0),),
    "assinada": (("Falha na averbação", 1.0),),
}
SAZONALIDADE = {1: 0.86, 2: 0.92, 3: 1.06, 4: 1.00, 5: 1.05, 6: 0.97,
                7: 1.08, 8: 1.07, 9: 0.99, 10: 1.06, 11: 1.03, 12: 0.82}
DIA_DA_SEMANA = (1.00, 1.04, 1.02, 0.98, 0.96, 0.42, 0.18)  # segunda a domingo
PRAZOS = ((12, 5), (24, 12), (36, 18), (48, 22), (60, 21), (72, 13), (84, 9))
DIAS_ATE_PAGAR = ((1, 24), (2, 30), (3, 20), (4, 13), (5, 8), (6, 5))

GERENTES = ("Gerente 1", "Gerente 2", "Gerente 3")


class Origem(NamedTuple):
    """De onde vêm as simulações: o canal digital ou um parceiro (correspondente)."""

    parceiro: str | None
    gerente_id: int | None
    simulacoes_dia: float  # média por dia útil no primeiro mês
    conversao: float  # multiplica a chance de passar da simulação e da análise
    ticket: int  # valor solicitado típico, em reais
    crescimento: float  # ao mês: 0.03 = +3%

    @property
    def canal(self):
        return "correspondente" if self.parceiro else "digital"


ORIGENS = (
    Origem(None, None, 44, 0.62, 4800, 0.035),
    Origem("Parceiro Aurora", 1, 24, 1.00, 6800, 0.020),
    Origem("Parceiro Brisa", 1, 13, 1.12, 5400, 0.040),
    Origem("Parceiro Cascata", 1, 7, 0.84, 4600, -0.015),
    Origem("Parceiro Duna", 2, 19, 0.95, 7600, 0.000),
    Origem("Parceiro Estrela", 2, 15, 1.15, 5900, 0.030),
    Origem("Parceiro Farol", 2, 8, 0.80, 4300, 0.010),
    Origem("Parceiro Garoa", 3, 16, 1.05, 6300, 0.050),
    Origem("Parceiro Horizonte", 3, 11, 0.90, 6000, -0.010),
    Origem("Parceiro Jangada", 3, 5, 1.20, 5100, 0.060),
)
PARCEIROS = tuple(origem for origem in ORIGENS if origem.parceiro)

ESQUEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE gerentes (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL
);

CREATE TABLE parceiros (
    id         INTEGER PRIMARY KEY,
    nome       TEXT NOT NULL UNIQUE,
    gerente_id INTEGER NOT NULL REFERENCES gerentes (id)
);

CREATE TABLE propostas (
    id               INTEGER PRIMARY KEY,
    canal            TEXT NOT NULL CHECK (canal IN ('digital', 'correspondente')),
    parceiro_id      INTEGER REFERENCES parceiros (id),
    data_criacao     TEXT NOT NULL,  -- AAAA-MM-DD
    etapa            TEXT NOT NULL CHECK (etapa IN
                     ('simulacao', 'proposta', 'analise', 'aprovada', 'assinada', 'paga')),
    motivo_recusa    TEXT,           -- preenchido só quando a proposta parou
    valor_solicitado REAL NOT NULL,
    prazo_meses      INTEGER NOT NULL,
    taxa_mensal      REAL NOT NULL,  -- em % ao mês
    CHECK ((canal = 'digital') = (parceiro_id IS NULL))
);

CREATE TABLE contratos (
    id             INTEGER PRIMARY KEY,
    proposta_id    INTEGER NOT NULL UNIQUE REFERENCES propostas (id),
    data_pagamento TEXT NOT NULL,    -- AAAA-MM-DD
    valor_liberado REAL NOT NULL,
    prazo_meses    INTEGER NOT NULL,
    taxa_mensal    REAL NOT NULL     -- em % ao mês
);

CREATE INDEX idx_propostas_data_criacao ON propostas (data_criacao);
CREATE INDEX idx_contratos_data_pagamento ON contratos (data_pagamento);
"""


def _sortear(rng, opcoes):
    """Escolhe um valor de uma lista de pares (valor, peso)."""
    valores, pesos = zip(*opcoes)
    return rng.choices(valores, pesos)[0]


def _limitar(valor, minimo, maximo):
    return min(max(valor, minimo), maximo)


def _jornada(rng, origem):
    """Etapa alcançada e motivo da parada (None quando chega a paga)."""
    for atual, seguinte in zip(ETAPAS, ETAPAS[1:]):
        chance = AVANCO[atual]
        if atual in ("simulacao", "analise"):
            chance = min(chance * origem.conversao, 0.97)
        if rng.random() >= chance:
            return atual, _sortear(rng, MOTIVOS[atual])
    return "paga", None


def _gerar_linhas(rng):
    """Linhas das tabelas propostas e contratos, dia a dia, de INICIO a FIM."""
    ids_parceiro = {origem.parceiro: i for i, origem in enumerate(PARCEIROS, start=1)}
    propostas, contratos = [], []
    dia = INICIO
    while dia <= FIM:
        meses = (dia.year - INICIO.year) * 12 + dia.month - INICIO.month
        fator_dia = SAZONALIDADE[dia.month] * DIA_DA_SEMANA[dia.weekday()]
        for origem in ORIGENS:
            media = origem.simulacoes_dia * fator_dia * (1 + origem.crescimento) ** meses
            for _ in range(max(0, round(rng.gauss(media, math.sqrt(media))))):
                etapa, motivo = _jornada(rng, origem)
                valor = round(_limitar(rng.lognormvariate(math.log(origem.ticket), 0.42), 1000, 35000), -2)
                prazo = _sortear(rng, PRAZOS)
                taxa = round(_limitar(1.58 + 0.045 * prazo / 12 - 0.01 * meses + rng.gauss(0, 0.14), 1.2, 2.9), 2)
                pagamento = dia + timedelta(days=_sortear(rng, DIAS_ATE_PAGAR)) if etapa == "paga" else None
                if pagamento and pagamento > FIM:
                    etapa, pagamento = "assinada", None  # em andamento: assinada, ainda sem pagamento
                propostas.append((len(propostas) + 1, origem.canal, ids_parceiro.get(origem.parceiro),
                                  dia.isoformat(), etapa, motivo, valor, prazo, taxa))
                if pagamento:  # parte sai com valor menor, recalculado pela parcela que cabe na margem
                    liberado = valor if rng.random() < 0.78 else round(valor * rng.uniform(0.60, 0.95), 2)
                    contratos.append((len(contratos) + 1, len(propostas), pagamento.isoformat(),
                                      liberado, prazo, taxa))
        dia += timedelta(days=1)
    return propostas, contratos


def gerar(caminho=CAMINHO_BASE, semente=SEMENTE):
    """Cria (ou recria) a base em `caminho` e devolve quantas linhas cada tabela recebeu."""
    propostas, contratos = _gerar_linhas(random.Random(semente))
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.unlink(missing_ok=True)
    with closing(sqlite3.connect(caminho)) as con:
        con.executescript(ESQUEMA)
        con.executemany("INSERT INTO gerentes VALUES (?, ?)", enumerate(GERENTES, start=1))
        con.executemany("INSERT INTO parceiros VALUES (?, ?, ?)",
                        [(i, origem.parceiro, origem.gerente_id) for i, origem in enumerate(PARCEIROS, start=1)])
        con.executemany("INSERT INTO propostas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", propostas)
        con.executemany("INSERT INTO contratos VALUES (?, ?, ?, ?, ?, ?)", contratos)
        con.commit()
    return {"gerentes": len(GERENTES), "parceiros": len(PARCEIROS),
            "propostas": len(propostas), "contratos": len(contratos)}


def main():
    inicio = time.perf_counter()
    contagem = gerar()
    resumo = ", ".join(f"{n:,} {tabela}".replace(",", ".") for tabela, n in contagem.items())
    segundos = f"{time.perf_counter() - inicio:.1f}".replace(".", ",")
    print(f"Base gerada em {CAMINHO_BASE.relative_to(PASTA).as_posix()}: {resumo} ({segundos} s).")


if __name__ == "__main__":
    main()
