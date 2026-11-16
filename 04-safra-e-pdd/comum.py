"""Caminhos, datas, dinheiro e formatação brasileira usados por todos os scripts."""

import sqlite3
from calendar import monthrange
from contextlib import closing
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PASTA = Path(__file__).resolve().parent
BANCO = PASTA / "dados" / "carteira.sqlite"
SAIDA = PASTA / "saida"
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


# Dinheiro: centavos inteiros no banco, Decimal no Python.

def centavos(valor: Decimal) -> Decimal:
    """Arredonda para o centavo (meio centavo arredonda para cima)."""
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def para_centavos(valor: Decimal) -> int:
    return int(centavos(valor) * 100)


def de_centavos(quantia: int) -> Decimal:
    return Decimal(quantia) / 100


def somar_meses(dia: date, meses: int) -> date:
    """A mesma data `meses` depois; se o dia não existir no mês, fica o último."""
    ano, mes = divmod(dia.year * 12 + dia.month - 1 + meses, 12)
    return date(ano, mes + 1, min(dia.day, monthrange(ano, mes + 1)[1]))


def fim_do_mes(dia: date) -> date:
    return dia.replace(day=monthrange(dia.year, dia.month)[1])


def meses_entre(inicio: date, fim: date) -> int:
    return (fim.year - inicio.year) * 12 + fim.month - inicio.month


def numero(valor, casas: int = 0, enxuto: bool = False) -> str:
    """1.234,5 — com `enxuto`, some com os zeros finais (10,0 vira 10)."""
    arredondado = Decimal(str(valor)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    texto = f"{arredondado:,.{casas}f}".translate(str.maketrans(",.", ".,"))
    if enxuto and casas:
        texto = texto.rstrip("0").rstrip(",")
    return texto


def moeda(valor: Decimal) -> str:
    """R$ 1.234,56"""
    return f"R$ {numero(valor, 2)}"


def moeda_curta(valor: Decimal, enxuto: bool = False) -> str:
    """R$ 35,7 mi · R$ 98,1 mil · R$ 950 — com `enxuto` (eixos), R$ 250 mil em vez de R$ 250,0 mil."""
    if valor >= 1_000_000:
        return f"R$ {numero(valor / 1_000_000, 1, enxuto)} mi"
    if valor >= 1_000:
        return f"R$ {numero(valor / 1_000, 1, enxuto)} mil"
    return f"R$ {numero(valor)}"


def percentual(fracao, casas: int = 1, enxuto: bool = False) -> str:
    """0.123 vira 12,3%"""
    return f"{numero(Decimal(str(fracao)) * 100, casas, enxuto)}%"


def parte_de(parte: int, total: int) -> str:
    """4,1% · 33 de 800"""
    fracao = parte / total if total else 0
    return f"{percentual(fracao)} · {numero(parte)} de {numero(total)}"


def mes_ano(dia: date) -> str:
    """jan/25"""
    return f"{MESES[dia.month - 1]}/{dia.year % 100:02d}"


def data_br(dia: date) -> str:
    return f"{dia:%d/%m/%Y}"


def abrir_banco(caminho: Path = BANCO):
    """Conexão com a carteira gerada; avisa se ela ainda não existe."""
    if not caminho.exists():
        raise SystemExit(f"Não achei {caminho}. Rode antes: python gerar_carteira.py")
    return closing(sqlite3.connect(caminho))


def ler_data_base(conexao: sqlite3.Connection) -> date:
    (valor,) = conexao.execute("SELECT valor FROM parametros WHERE chave = 'data_base'").fetchone()
    return date.fromisoformat(valor)
