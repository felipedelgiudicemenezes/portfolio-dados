"""Separa as falas de uma transcrição que parecem pedido e monta uma lista de verificação em Markdown.

É uma heurística: procura expressões como "precisa", "quero", "tem que", "dá para", "seria bom"
e "falta", sem entender o contexto. Ela marca fala que não é pedido e deixa passar pedido dito de
outro jeito, então a lista é um rascunho para revisão humana, não a ata da reunião.

Uso:
    python requisitos.py reuniao.txt [-o requisitos.md]

Entrada: o .txt do transcrever.py, uma fala por linha, "[hh:mm:ss] texto" ou
"[hh:mm:ss] Falante: texto". Linha sem horário continua a fala anterior; "#" é comentário.
"""

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Rótulo mostrado na lista: padrão procurado no texto já sem acento e em minúsculas.
EXPRESSOES = {
    "precisa": r"precis(a|am|amos|o|ava|aria|ariamos)",
    "quero": r"quer(o|em|emos|ia|iamos)",
    "tem que": r"(tem|temos|tinha|teria|teriamos) que",
    "dá para": r"da (para|pra)",
    "seria bom": r"seria (bom|bem|legal|interessante|otimo|util|melhor)",
    "falta": r"falt(a|am|ou|aram|ando)",
    "gostaria": r"gostaria(mos)?",
}
_BUSCAS = [(rotulo, re.compile(rf"\b{padrao}\b")) for rotulo, padrao in EXPRESSOES.items()]
_FALA = re.compile(r"^\[(?P<hora>\d{1,2}:\d{2}:\d{2})\]\s*(?:(?P<falante>[^\W\d_][\w ]{0,29}):\s+)?(?P<texto>.*)$")


@dataclass
class Fala:
    hora: str
    falante: str | None
    texto: str


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(letra for letra in decomposto if unicodedata.category(letra) != "Mn")


def expressao_de_pedido(texto: str) -> str | None:
    """Rótulo da primeira expressão de pedido encontrada na fala, ou None."""
    normalizado = sem_acento(texto)
    for rotulo, busca in _BUSCAS:
        if busca.search(normalizado):
            return rotulo
    return None


def ler_falas(texto: str) -> list[Fala]:
    falas: list[Fala] = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        achado = _FALA.match(linha)
        if achado:
            falas.append(Fala(achado["hora"], achado["falante"], achado["texto"].strip()))
        elif falas:
            falas[-1].texto += " " + linha
    return falas


def numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def parte_de(parte: int, total: int) -> str:
    """34,0% · 16 de 47: o percentual sempre com o número absoluto."""
    percentual = Decimal(parte) * 100 / Decimal(total) if total else Decimal(0)
    arredondado = str(percentual.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)).replace(".", ",")
    return f"{arredondado}% · {numero(parte)} de {numero(total)}"


def montar_markdown(falas: list[Fala], origem: str) -> str:
    """Lista com horário, falante e o rótulo da expressão que fez a fala entrar."""
    pedidos = [(fala, rotulo) for fala in falas if (rotulo := expressao_de_pedido(fala.texto))]
    linhas = [
        "# Pedidos da reunião",
        "",
        f"Transcrição: `{origem}`. Falas que parecem pedido: {parte_de(len(pedidos), len(falas))}.",
        "",
        '> Lista feita por heurística: o script procura expressões como "precisa", "quero", "tem que", '
        '"dá para", "seria bom" e "falta", sem entender o contexto. Pode marcar fala que não é pedido e '
        "deixar passar pedido dito de outro jeito. Confira cada item com a gravação antes de repassar.",
        "",
    ]
    for fala, rotulo in pedidos:
        falante = f"**{fala.falante}:** " if fala.falante else ""
        linhas.append(f"- [ ] `{fala.hora}` {falante}{fala.texto} _({rotulo})_")
    if not pedidos:
        linhas.append("Nenhuma fala com as expressões procuradas.")
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Separa as falas que parecem pedido numa lista em Markdown.")
    parser.add_argument("transcricao", type=Path, help=".txt com uma fala por linha, começando por [hh:mm:ss]")
    parser.add_argument("-o", "--saida", type=Path, help="arquivo .md (padrão: <transcrição>-requisitos.md)")
    args = parser.parse_args(argv)
    if not args.transcricao.is_file():
        parser.error(f"arquivo não encontrado: {args.transcricao}")

    falas = ler_falas(args.transcricao.read_text(encoding="utf-8-sig"))
    destino = args.saida or args.transcricao.with_name(f"{args.transcricao.stem}-requisitos.md")
    destino.write_text(montar_markdown(falas, args.transcricao.name), encoding="utf-8", newline="\n")
    pedidos = sum(expressao_de_pedido(fala.texto) is not None for fala in falas)
    print(f"Falas que parecem pedido: {parte_de(pedidos, len(falas))}. Lista em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
