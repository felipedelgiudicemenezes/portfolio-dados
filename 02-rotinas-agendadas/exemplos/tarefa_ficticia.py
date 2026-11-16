"""Tarefa de mentira para exercitar o executor: espera um pouco e termina bem ou com falha.

Uso:
    python exemplos/tarefa_ficticia.py "carga de propostas" [--segundos 1] [--falha passageira|definitiva]
"""

import argparse
import sys
import time

SAIDA_PASSAGEIRA = 75  # o código que o rotina.py repete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simula uma rotina.")
    parser.add_argument("descricao", help="o que a tarefa finge fazer")
    parser.add_argument("--segundos", type=float, default=1, help="duração simulada (padrão: 1)")
    parser.add_argument("--falha", choices=("passageira", "definitiva"), help="termina com esse tipo de falha")
    args = parser.parse_args(argv)

    print(f"Começando: {args.descricao}.")
    time.sleep(args.segundos)
    if args.falha == "passageira":
        print("Servidor de origem ocupado; vale tentar de novo.", file=sys.stderr)
        return SAIDA_PASSAGEIRA
    if args.falha == "definitiva":
        print("Coluna 'valor' não encontrada no arquivo de entrada.", file=sys.stderr)
        return 1
    print(f"Concluída: {args.descricao}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
