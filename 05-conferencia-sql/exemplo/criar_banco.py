"""Monta o banco SQLite de exemplo da Fintech Exemplo a partir de schema.sql.

Uso: python exemplo/criar_banco.py [destino.sqlite]

Todos os dados são fictícios, gerados com semente fixa: o banco sai sempre igual.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).resolve().parent
DESTINO_PADRAO = PASTA / "fintech_exemplo.sqlite"
UFS = ["SP", "RJ", "MG", "PR", "RS", "BA", "PE", "GO"]
PRAZOS = [12, 18, 24, 36, 48]
PESO_DO_STATUS = {"aprovada": 45, "recusada": 35, "em_analise": 12, "cancelada": 8}
INICIO = datetime(2026, 1, 1)
MINUTOS_NO_SEMESTRE = 181 * 24 * 60


def criar(destino: Path = DESTINO_PADRAO, semente: int = 42) -> Path:
    """Recria `destino` com o esquema e linhas fictícias; devolve o caminho."""
    rng = random.Random(semente)
    parceiros = [(i, f"Parceiro {i:02d}", rng.choice(UFS), int(rng.random() < 0.75)) for i in range(1, 13)]
    propostas, contratos = [], []
    for id_proposta in range(1, 401):
        criada_em = INICIO + timedelta(minutes=rng.randrange(MINUTOS_NO_SEMESTRE))
        status = rng.choices(list(PESO_DO_STATUS), weights=list(PESO_DO_STATUS.values()))[0]
        valor = round(rng.uniform(1_000, 30_000), 2)
        propostas.append((id_proposta, rng.randint(1, 12), _texto(criada_em), status, valor, rng.choice(PRAZOS)))
        if status == "aprovada":
            pago_em = criada_em + timedelta(hours=rng.randint(2, 72))
            liberado = round(valor * rng.uniform(0.85, 1.0), 2)
            taxa = round(rng.uniform(1.6, 3.2), 2)
            contratos.append((len(contratos) + 1, id_proposta, _texto(pago_em), liberado, taxa))

    destino.unlink(missing_ok=True)
    with closing(sqlite3.connect(destino)) as conn:
        conn.executescript((PASTA / "schema.sql").read_text(encoding="utf-8"))
        conn.executemany("INSERT INTO parceiros VALUES (?, ?, ?, ?)", parceiros)
        conn.executemany("INSERT INTO propostas VALUES (?, ?, ?, ?, ?, ?)", propostas)
        conn.executemany("INSERT INTO contratos VALUES (?, ?, ?, ?, ?)", contratos)
        conn.commit()
    return destino


def _texto(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    destino = criar(Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO_PADRAO)
    print(f"Banco de exemplo criado: {destino}")
