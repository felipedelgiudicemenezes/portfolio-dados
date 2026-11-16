"""Executor de rotinas agendadas: trava, log com rotação, tempo limite, novas tentativas e estado.

Uso:
    python rotina.py <nome>                    usa o comando e os limites do rotinas.json
    python rotina.py <nome> -- <comando...>    roda o comando informado

Como função: executar("carga", ["python", "carga.py"], tentativas=3).
"""

import argparse
import ctypes
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Sequence

PASTA = Path(__file__).resolve().parent
CONFIGURACAO = PASTA / "rotinas.json"
PADROES = {"tempo_limite_s": 3600, "tentativas": 3, "espera_s": 30}

SAIDA_OK = 0
SAIDA_OCUPADA = 3  # a execução anterior da mesma rotina ainda está rodando
SAIDA_PASSAGEIRA = 75  # EX_TEMPFAIL do sysexits.h: falhou agora, mas vale tentar de novo
SAIDA_TEMPO_ESGOTADO = 124  # mesma convenção do comando timeout do GNU
SAIDA_NAO_INICIOU = 127  # comando inexistente ou sem permissão

logging.addLevelName(logging.WARNING, "AVISO")
logging.addLevelName(logging.ERROR, "ERRO")


def agora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def segundos(valor: float) -> str:
    """1,5 s"""
    return f"{valor:g} s".replace(".", ",")


def processo_vivo(pid: int | None) -> bool:
    """Diz se existe um processo rodando com esse PID."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        return _processo_vivo_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _processo_vivo_windows(pid: int) -> bool:
    # No Windows, os.kill(pid, 0) encerraria o processo; a pergunta vai direto à API do sistema.
    from ctypes import wintypes

    sincronizar = 0x00100000  # SYNCHRONIZE
    acesso_negado = 5  # ERROR_ACCESS_DENIED: o processo existe, mas é de outro usuário
    ainda_rodando = 0x102  # WAIT_TIMEOUT
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    alca = kernel32.OpenProcess(sincronizar, False, pid)
    if not alca:
        return ctypes.get_last_error() == acesso_negado
    try:
        return kernel32.WaitForSingleObject(alca, 0) == ainda_rodando
    finally:
        kernel32.CloseHandle(alca)


class Trava:
    """Trava por arquivo com o PID do dono; a de um processo que já morreu é liberada."""

    def __init__(self, caminho: Path, validade_s: float = 24 * 3600):
        self.caminho = Path(caminho)
        self.validade_s = validade_s

    def adquirir(self) -> bool:
        """Cria a trava; devolve False se outra execução viva já a tem."""
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                with open(self.caminho, "x", encoding="utf-8") as arquivo:
                    json.dump({"pid": os.getpid(), "desde": agora_iso()}, arquivo)
                return True
            except FileExistsError:
                if not self._velha():
                    return False
                self.caminho.unlink(missing_ok=True)
        return False

    def liberar(self) -> None:
        if self.dono() == os.getpid():
            self.caminho.unlink(missing_ok=True)

    def dono(self) -> int | None:
        """PID gravado na trava, ou None se ela não existe ou está ilegível."""
        try:
            return int(json.loads(self.caminho.read_text(encoding="utf-8"))["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _velha(self) -> bool:
        try:
            idade = time.time() - self.caminho.stat().st_mtime
        except FileNotFoundError:
            return True
        pid = self.dono()
        if pid is None:  # recém-criada (o PID ainda não foi escrito) ou corrompida
            return idade > 10
        # A validade cobre o caso de o Windows já ter dado o PID do dono morto a outro processo.
        return idade > self.validade_s or not processo_vivo(pid)


def carregar_rotinas(caminho: Path = CONFIGURACAO) -> dict[str, dict]:
    """Rotinas do rotinas.json, indexadas pelo nome."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {rotina["nome"]: rotina for rotina in dados["rotinas"]}


def executar(
    nome: str,
    comando: Sequence[str],
    *,
    tempo_limite_s: float = PADROES["tempo_limite_s"],
    tentativas: int = PADROES["tentativas"],
    espera_s: float = PADROES["espera_s"],
    pasta: Path = PASTA,
    eco: bool = False,
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Roda `comando` como a rotina `nome` e devolve o código de saída.

    Só repete o comando quando ele sai com SAIDA_PASSAGEIRA; a espera dobra a cada nova tentativa.
    """
    pasta = Path(pasta)
    comando = list(comando)
    tentativas = max(1, int(tentativas))
    caminho_estado = pasta / "estado" / f"{nome}.json"
    validade = tentativas * tempo_limite_s + espera_s * 2**tentativas + 60
    trava = Trava(pasta / "estado" / f"{nome}.trava", validade)

    with ExitStack() as ao_sair:
        log = _abrir_log(nome, pasta / "logs", eco)
        ao_sair.callback(_fechar_log, log)
        if not trava.adquirir():
            log.warning("Pulada: a execução anterior (PID %s) ainda está rodando.", trava.dono())
            return SAIDA_OCUPADA
        ao_sair.callback(trava.liberar)

        estado = {
            "rotina": nome,
            "comando": comando,
            "pid": os.getpid(),
            "inicio": agora_iso(),
            "fim": None,
            "duracao_s": None,
            "resultado": "rodando",
            "codigo_saida": None,
            "tentativas": 0,
            "erro": None,
        }
        _gravar_estado(caminho_estado, estado)
        log.info("Início: %s", subprocess.list2cmdline(comando))
        relogio = time.monotonic()
        for tentativa in range(1, tentativas + 1):
            codigo, erro = _rodar(_com_este_python(comando), tempo_limite_s, log)
            if codigo != SAIDA_PASSAGEIRA or tentativa == tentativas:
                break
            espera = espera_s * 2 ** (tentativa - 1)
            log.warning(
                "Falha passageira (tentativa %d de %d); nova tentativa em %s.", tentativa, tentativas, segundos(espera)
            )
            dormir(espera)

        estado.update(
            fim=agora_iso(),
            duracao_s=round(time.monotonic() - relogio, 1),
            resultado="ok" if codigo == SAIDA_OK else "erro",
            codigo_saida=codigo,
            tentativas=tentativa,
            erro=erro,
        )
        _gravar_estado(caminho_estado, estado)
        if codigo == SAIDA_OK:
            log.info("Fim: ok em %s.", segundos(estado["duracao_s"]))
        else:
            log.error("Fim: erro (código %d, %d tentativa(s)): %s", codigo, tentativa, erro)
        return codigo


def _com_este_python(comando: list[str]) -> list[str]:
    """Troca um "python" no início pelo interpretador atual (o da venv, se houver)."""
    if comando and comando[0] == "python":
        return [sys.executable, *comando[1:]]
    return comando


def _rodar(comando: list[str], tempo_limite_s: float, log: logging.Logger) -> tuple[int, str | None]:
    """Roda o comando uma vez e devolve (código, mensagem de erro).

    A saída vai para um arquivo temporário, não para um pipe: comando que escreve muito não trava
    esperando leitura, e stdout e stderr chegam juntos ao log. A mensagem de erro é a última linha
    (num traceback do Python, a da exceção); o resto fica no log.
    """
    # Sem buffer, um filho em Python escreve stdout e stderr na ordem em que acontecem.
    ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    estourou = False
    with tempfile.TemporaryFile() as saida:
        try:
            codigo = subprocess.run(
                comando,
                stdin=subprocess.DEVNULL,
                stdout=saida,
                stderr=subprocess.STDOUT,
                timeout=tempo_limite_s,
                env=ambiente,
            ).returncode
        except subprocess.TimeoutExpired:
            codigo, estourou = SAIDA_TEMPO_ESGOTADO, True
        except OSError as erro:
            return SAIDA_NAO_INICIOU, f"O comando não iniciou: {erro}"
        saida.seek(0)
        linhas = [linha for linha in _decodificar(saida.read()).splitlines() if linha.strip()]

    for linha in linhas:
        log.info("| %s", linha)
    if estourou:
        return codigo, f"Tempo limite de {segundos(tempo_limite_s)} estourado."
    if codigo == SAIDA_OK:
        return codigo, None
    return codigo, (linhas[-1].strip()[:500] if linhas else f"Saiu com o código {codigo}.")


def _decodificar(dados: bytes) -> str:
    """UTF-8 ou, se não for, a página de código do console (a saída do PowerShell 5.1, por exemplo)."""
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        pagina = f"cp{ctypes.windll.kernel32.GetOEMCP()}" if os.name == "nt" else "latin-1"
        return dados.decode(pagina, errors="replace")


def _gravar_estado(caminho: Path, estado: dict) -> None:
    """Grava em arquivo temporário e troca de uma vez: o painel nunca lê um JSON pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    for _ in range(4):
        try:
            os.replace(temporario, caminho)
            return
        except PermissionError:  # no Windows, a troca falha se alguém estiver lendo o arquivo
            time.sleep(0.25)
    os.replace(temporario, caminho)


def _abrir_log(nome: str, pasta: Path, eco: bool) -> logging.Logger:
    """Log em logs/<nome>.log, com rotação (até 5 arquivos antigos de 1 MB)."""
    pasta.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger(f"rotina.{nome}")
    log.setLevel(logging.INFO)
    log.propagate = False
    saidas: list[logging.Handler] = [
        RotatingFileHandler(pasta / f"{nome}.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    ]
    if eco:
        saidas.append(logging.StreamHandler())
    formato = logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%Y-%m-%d %H:%M:%S")
    for saida in saidas:
        saida.setFormatter(formato)
        log.addHandler(saida)
    return log


def _fechar_log(log: logging.Logger) -> None:
    for saida in list(log.handlers):
        log.removeHandler(saida)
        saida.close()


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    comando: list[str] = []
    if "--" in argv:
        corte = argv.index("--")
        argv, comando = argv[:corte], argv[corte + 1 :]

    parser = argparse.ArgumentParser(description="Roda uma rotina com trava, log, tempo limite e novas tentativas.")
    parser.add_argument("nome", help="nome da rotina (dá nome à trava, ao log e ao estado)")
    parser.add_argument("--tempo-limite", type=float, metavar="S", help="segundos por tentativa")
    parser.add_argument("--tentativas", type=int, metavar="N", help="máximo de tentativas para erro passageiro")
    parser.add_argument("--espera", type=float, metavar="S", help="espera antes da 2ª tentativa; dobra a cada nova")
    parser.add_argument("--pasta", type=Path, default=PASTA, help="onde ficam estado/ e logs/")
    parser.add_argument("--config", type=Path, default=CONFIGURACAO, help="arquivo de rotinas (padrão: rotinas.json)")
    args = parser.parse_args(argv)

    config = carregar_rotinas(args.config).get(args.nome, {}) if args.config.exists() else {}
    comando = comando or config.get("comando", [])
    if not comando:
        parser.error(f"a rotina {args.nome!r} não está em {args.config.name}; informe o comando depois de --")

    def opcao(valor, campo):
        return valor if valor is not None else config.get(campo, PADROES[campo])

    return executar(
        args.nome,
        comando,
        tempo_limite_s=opcao(args.tempo_limite, "tempo_limite_s"),
        tentativas=opcao(args.tentativas, "tentativas"),
        espera_s=opcao(args.espera, "espera_s"),
        pasta=args.pasta,
        eco=True,
    )


if __name__ == "__main__":
    sys.exit(main())
