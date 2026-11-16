"""Confere se as consultas SQL de uma dashboard ainda batem com o banco.

Para cada arquivo .sql da pasta:
  1. prepara a consulta com EXPLAIN, sem trazer dados, para achar tabela ou
     coluna que não existe;
  2. anota as colunas que ela lê de fato, pelo set_authorizer do sqlite3;
  3. compara com o que ela declara no topo (`-- usa: tabela.coluna, ...`);
  4. grava o relatório em Markdown e em HTML.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import relatorio

USO = """uso: python conferir.py <banco.sqlite> <pasta_de_consultas> [pasta_de_saida]

Confere cada .sql da pasta contra o banco e grava relatorio.md e relatorio.html
na pasta de saída (padrão: saida). Código de saída: 0 sem erro, 1 se alguma
consulta tem erro, 2 se o uso está errado."""

LINHA_USA = re.compile(r"--\s*usa\s*:(.*)", re.IGNORECASE)

TRADUCOES = [
    (re.compile(r"no such table: (.+)"), "tabela não existe: {}"),
    (re.compile(r"no such column: (.+)"), "coluna não existe: {}"),
    (re.compile(r"ambiguous column name: (.+)"), "coluna ambígua (existe em mais de uma tabela): {}"),
    (re.compile(r'near "(.*)": syntax error'), 'erro de sintaxe perto de "{}"'),
    (re.compile(r"incomplete input"), "SQL incompleto"),
    (re.compile(r"one statement at a time"), "o arquivo tem mais de um comando SQL"),
    (re.compile(r"Binding \d+ has no name"), "parâmetro com ? não é aceito; use :nome"),
]

GRAVIDADE = {"erro": 0, "aviso": 1, "ok": 2}


class _ParametrosNulos(dict):
    """Liga qualquer parâmetro nomeado (:inicio, :fim...) a NULL."""

    def __missing__(self, nome):
        return None


@dataclass(frozen=True)
class Conferencia:
    """O que a conferência achou em um arquivo .sql."""

    arquivo: str
    sql: str
    declarado: frozenset[str] | None  # None: o arquivo não tem a linha `-- usa:`
    usado: frozenset[str] = frozenset()
    erro: str | None = None

    @property
    def declarado_nao_usado(self) -> list[str]:
        return [] if self.erro else _sem_par(self.declarado or frozenset(), self.usado)

    @property
    def usado_nao_declarado(self) -> list[str]:
        return [] if self.erro else _sem_par(self.usado, self.declarado or frozenset())

    @property
    def status(self) -> str:
        if self.erro:
            return "erro"
        if self.declarado is None or self.declarado_nao_usado or self.usado_nao_declarado:
            return "aviso"
        return "ok"

    @property
    def resumo(self) -> str:
        """Uma linha que explica o status."""
        if self.erro:
            return self.erro
        partes = []
        if self.declarado is None:
            partes.append('sem a linha "-- usa:" no topo')
        if self.declarado_nao_usado:
            partes.append("declarado e não usado: " + ", ".join(self.declarado_nao_usado))
        if self.usado_nao_declarado:
            partes.append("usado e não declarado: " + ", ".join(self.usado_nao_declarado))
        return "; ".join(partes) or "declaração confere"


def _sem_par(itens: frozenset[str], outros: frozenset[str]) -> list[str]:
    """Itens sem par do outro lado; uma tabela sozinha casa com qualquer coluna dela."""
    tabelas = {item.split(".", 1)[0] for item in outros}
    return sorted(i for i in itens if i not in outros and ("." in i or i not in tabelas))


def ler_declaracao(sql: str) -> frozenset[str] | None:
    """Itens da linha `-- usa:` no bloco de comentários do topo; None se não houver."""
    linhas_usa = []
    for linha in sql.splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("--"):
            break
        achou = LINHA_USA.match(linha)
        if achou:
            linhas_usa.append(achou.group(1))
    if not linhas_usa:
        return None
    return frozenset(
        item.strip().lower() for linha in linhas_usa for item in linha.split(",") if item.strip()
    )


def colunas_lidas(conn: sqlite3.Connection, sql: str) -> frozenset[str]:
    """Prepara a consulta com EXPLAIN e devolve o que ela lê, como `tabela.coluna`.

    Tabela lida sem coluna nenhuma (um COUNT(*), por exemplo) entra só com o nome.
    O que uma visão lê por dentro não entra: conta a própria visão.
    """
    visoes = {nome.lower() for (nome,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}
    colunas, tabelas = set(), set()

    def anotar(acao, tabela, coluna, _banco, origem):
        if acao == sqlite3.SQLITE_READ and (origem or "").lower() not in visoes:
            tabelas.add(tabela.lower())
            if coluna:
                colunas.add(f"{tabela}.{coluna}".lower())
        return sqlite3.SQLITE_OK

    conn.set_authorizer(anotar)
    try:
        conn.execute("EXPLAIN " + sql, _ParametrosNulos())
    finally:
        conn.set_authorizer(None)
    tabelas_com_coluna = {c.split(".", 1)[0] for c in colunas}
    return frozenset(colunas | (tabelas - tabelas_com_coluna))


def traduzir(mensagem: str) -> str:
    """Mensagem do SQLite em português (as mais comuns)."""
    for padrao, texto in TRADUCOES:
        achou = padrao.search(mensagem)
        if achou:
            return texto.format(*achou.groups())
    return f"o SQLite recusou a consulta: {mensagem}"


def conferir_consulta(conn: sqlite3.Connection, arquivo: Path) -> Conferencia:
    """Confere um arquivo .sql com a conexão já aberta."""
    sql = arquivo.read_text(encoding="utf-8-sig")
    declarado = ler_declaracao(sql)
    try:
        usado = colunas_lidas(conn, sql)
    except (sqlite3.Error, sqlite3.Warning) as erro:
        return Conferencia(arquivo.name, sql, declarado, erro=traduzir(str(erro)))
    return Conferencia(arquivo.name, sql, declarado, usado)


def abrir_somente_leitura(banco: Path) -> sqlite3.Connection:
    """Abre o banco só para leitura e sem cache de comandos (com cache, o authorizer não roda de novo)."""
    return sqlite3.connect(banco.resolve().as_uri() + "?mode=ro", uri=True, cached_statements=0)


def conferir_pasta(banco: Path, pasta: Path) -> list[Conferencia]:
    """Confere todos os .sql da pasta, em ordem de nome."""
    with closing(abrir_somente_leitura(banco)) as conn:
        return [conferir_consulta(conn, arquivo) for arquivo in sorted(pasta.glob("*.sql"))]


def por_gravidade(conferencias: list[Conferencia]) -> list[Conferencia]:
    """Erros primeiro, depois avisos, depois ok; no empate, pelo nome do arquivo."""
    return sorted(conferencias, key=lambda c: (GRAVIDADE[c.status], c.arquivo))


def main(argv: list[str] | None = None) -> int:
    """Roda a conferência pela linha de comando e devolve o código de saída."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):
        print(USO, file=sys.stderr)
        return 2
    banco, pasta = Path(argv[0]), Path(argv[1])
    saida = Path(argv[2]) if len(argv) == 3 else Path("saida")
    if not banco.is_file():
        print(f"Banco não encontrado: {banco}", file=sys.stderr)
        return 2
    if not pasta.is_dir() or not any(pasta.glob("*.sql")):
        print(f"Nenhum arquivo .sql em: {pasta}", file=sys.stderr)
        return 2

    conferencias = por_gravidade(conferir_pasta(banco, pasta))
    md, html = relatorio.gravar(conferencias, banco.as_posix(), pasta.as_posix(), saida)

    print(f"Conferência de {len(conferencias)} consultas contra {banco.as_posix()}")
    for c in conferencias:
        print(f"  {c.status:<6} {c.arquivo}: {c.resumo}")
    total = Counter(c.status for c in conferencias)
    print(f"Total: {total['ok']} ok, {total['aviso']} com aviso, {total['erro']} com erro")
    print(f"Relatórios: {md.as_posix()} e {html.as_posix()}")
    return 1 if total["erro"] else 0


if __name__ == "__main__":
    sys.exit(main())
