"""Gera a dashboard: base -> consultas SQL -> payload por perfil -> páginas em saida/.

Uso:
    python build.py                      # diretoria e uma página por gerente
    python build.py --perfil gerente-2   # só um perfil
"""

import argparse
import os
from contextlib import closing
from pathlib import Path

import gerar_base
import kpis
import render

PASTA = Path(__file__).resolve().parent
PASTA_SAIDA = PASTA / "saida"


def construir(caminho_base=gerar_base.CAMINHO_BASE, pasta_saida=PASTA_SAIDA, perfil=None):
    """Escreve uma página por perfil (ou só a de `perfil`) e devolve os caminhos gerados."""
    if not Path(caminho_base).exists():
        gerar_base.gerar(caminho_base)
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    with closing(kpis.conectar(caminho_base)) as con:
        perfis = kpis.listar_perfis(con)
        if perfil:
            escolhidos = [p for p in perfis if p["id"] == perfil]
            if not escolhidos:
                opcoes = ", ".join(p["id"] for p in perfis)
                raise ValueError(f"perfil desconhecido: {perfil!r}. Opções: {opcoes}.")
            perfis = escolhidos
        gerados = []
        for item in perfis:
            html = render.gerar_html(kpis.montar_payload(con, item))
            destino = pasta_saida / f"{item['id']}.html"
            temporario = destino.with_suffix(".tmp")
            temporario.write_text(html, encoding="utf-8")
            os.replace(temporario, destino)  # quem abrir a página no meio da troca vê a versão inteira
            gerados.append(destino)
    return gerados


def main():
    parser = argparse.ArgumentParser(
        description="Gera a dashboard comercial da Fintech Exemplo, uma página por perfil.", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="mostra esta ajuda e sai")
    parser.add_argument("--perfil", help="gera só este perfil: diretoria ou gerente-<n>")
    argumentos = parser.parse_args()
    if not gerar_base.CAMINHO_BASE.exists():
        print("Base não encontrada: gerando dados/base.sqlite.")
    try:
        gerados = construir(perfil=argumentos.perfil)
    except ValueError as erro:
        raise SystemExit(f"Erro: {erro}") from None
    for caminho in gerados:
        print(f"ok  {caminho.relative_to(PASTA).as_posix()}")


if __name__ == "__main__":
    main()
