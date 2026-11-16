"""Painel de saúde das rotinas: lê estado/*.json e compara com a agenda do rotinas.json.

Uso:
    python painel.py                            situação agora
    python painel.py --agora 2026-11-17T09:00   como estará nesse horário, se nada mais rodar

Sai com código 1 se alguma rotina não estiver em ordem, para servir de alarme em outra rotina.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from rotina import CONFIGURACAO, PASTA, carregar_rotinas, processo_vivo

FOLGA = timedelta(minutes=10)
DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
EM_ORDEM = ("em dia", "rodando")
COLUNAS = ("ROTINA", "AGENDA", "ÚLTIMO INÍCIO", "DURAÇÃO", "TENTATIVAS", "RESULTADO", "SITUAÇÃO")


def prazo(config: dict, agora: datetime) -> datetime | None:
    """Início mais antigo aceitável para a última execução; None se a rotina não tem agenda."""
    limite = agora - FOLGA
    if "intervalo_min" in config:
        return limite - timedelta(minutes=config["intervalo_min"])
    if "horario" in config:
        hora, minuto = map(int, config["horario"].split(":"))
        dias = config.get("dias") or DIAS
        for atras in range(8):
            ocorrencia = (limite - timedelta(days=atras)).replace(hour=hora, minute=minuto, second=0, microsecond=0)
            if ocorrencia <= limite and DIAS[ocorrencia.weekday()] in dias:
                return ocorrencia
    return None


def situacao(config: dict, estado: dict | None, agora: datetime) -> str:
    """em dia, atrasada, com erro, rodando, interrompida ou nunca rodou."""
    if estado is None:
        return "nunca rodou"
    if estado.get("resultado") == "rodando":
        return "rodando" if processo_vivo(estado.get("pid")) else "interrompida"
    if estado.get("resultado") != "ok":
        return "com erro"
    limite = prazo(config, agora)
    if limite and datetime.fromisoformat(estado["inicio"]) < limite:
        return "atrasada"
    return "em dia"


def agenda(config: dict) -> str:
    """a cada 15 min · seg a sex 08:30 · todo dia 02:00"""
    if "intervalo_min" in config:
        return f"a cada {config['intervalo_min']} min"
    if "horario" not in config:
        return "sem agenda"
    dias = [dia for dia in DIAS if dia in (config.get("dias") or DIAS)]
    inicio = DIAS.index(dias[0])
    if len(dias) == len(DIAS):
        quando = "todo dia"
    elif len(dias) > 2 and tuple(dias) == DIAS[inicio : inicio + len(dias)]:
        quando = f"{dias[0]} a {dias[-1]}"
    else:
        quando = ", ".join(dias)
    return f"{quando} {config['horario']}"


def duracao(segundos: float | None) -> str:
    """0,4 s · 2 min 05 s · 1 h 03 min"""
    if segundos is None:
        return "—"
    if segundos < 60:
        return f"{segundos:.1f} s".replace(".", ",")
    minutos, resto = divmod(round(segundos), 60)
    if minutos < 60:
        return f"{minutos} min {resto:02d} s"
    horas, minutos = divmod(minutos, 60)
    return f"{horas} h {minutos:02d} min"


def linha(nome: str, config: dict, estado: dict | None, agora: datetime) -> tuple[str, ...]:
    if estado is None:
        return (nome, agenda(config), "—", "—", "—", "—", "nunca rodou")
    resultado = estado.get("resultado", "—")
    if resultado == "erro":
        resultado = f"erro {estado.get('codigo_saida')}"
    return (
        nome,
        agenda(config),
        datetime.fromisoformat(estado["inicio"]).strftime("%d/%m/%Y %H:%M"),
        duracao(estado.get("duracao_s")),
        str(estado.get("tentativas") or "—"),
        resultado,
        situacao(config, estado, agora),
    )


def ler_estados(pasta: Path) -> dict[str, dict]:
    """Último estado de cada rotina; arquivo ilegível fica de fora."""
    estados = {}
    for arquivo in sorted(pasta.glob("*.json")):
        try:
            estados[arquivo.stem] = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return estados


def imprimir_tabela(linhas: list[tuple[str, ...]]) -> None:
    larguras = [max(map(len, coluna)) for coluna in zip(COLUNAS, *linhas)]
    for valores in (COLUNAS, *linhas):
        print("  ".join(valor.ljust(largura) for valor, largura in zip(valores, larguras)).rstrip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mostra a saúde das rotinas a partir de estado/*.json.")
    parser.add_argument("--pasta", type=Path, default=PASTA, help="pasta que contém estado/ (padrão: a do projeto)")
    parser.add_argument("--config", type=Path, default=CONFIGURACAO, help="arquivo de rotinas (padrão: rotinas.json)")
    parser.add_argument(
        "--agora", type=datetime.fromisoformat, metavar="AAAA-MM-DDTHH:MM", help="avalia como se fosse este horário"
    )
    args = parser.parse_args(argv)

    agora = (args.agora or datetime.now()).astimezone()
    rotinas = carregar_rotinas(args.config)
    estados = ler_estados(args.pasta / "estado")
    nomes = list(rotinas) + sorted(set(estados) - set(rotinas))
    linhas = [linha(nome, rotinas.get(nome, {}), estados.get(nome), agora) for nome in nomes]
    imprimir_tabela(linhas)

    erros = [nome for nome in nomes if estados.get(nome, {}).get("resultado") == "erro"]
    if erros:
        print("\nErro da última execução:")
        for nome in erros:
            print(f"  {nome}: {estados[nome].get('erro')}")
    em_ordem = sum(valores[-1] in EM_ORDEM for valores in linhas)
    print(f"\nEm ordem: {em_ordem} de {len(linhas)} rotinas (avaliado em {agora:%d/%m/%Y %H:%M}).")
    return 0 if em_ordem == len(linhas) else 1


if __name__ == "__main__":
    sys.exit(main())
