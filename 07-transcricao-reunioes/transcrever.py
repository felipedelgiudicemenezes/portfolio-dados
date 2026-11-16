"""Transcreve uma reunião gravada (áudio ou vídeo) com o faster-whisper, na própria máquina.

Gera dois arquivos na pasta da gravação (ou em --saida):
    <nome>.txt   um trecho por linha, com o [hh:mm:ss] de início
    <nome>.srt   legenda, para abrir junto do vídeo no player

Uso:
    python transcrever.py reuniao.mp4 [--modelo small] [--idioma pt] [--saida pasta]

Única dependência fora da biblioteca padrão: pip install faster-whisper
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

SEM_PACOTE = (
    "O faster-whisper não está instalado. Instale com:\n"
    "    pip install faster-whisper\n"
    "e rode de novo. O requisitos.py funciona sem ele."
)


@dataclass(frozen=True)
class Trecho:
    inicio: float  # segundos desde o começo da gravação
    fim: float
    texto: str


def hhmmss(segundos: float) -> str:
    """65,9 s vira 00:01:05: o segundo em que o trecho começa, sem arredondar para cima."""
    total = int(segundos)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def tempo_srt(segundos: float) -> str:
    """65,25 s vira 00:01:05,250, o formato de tempo do SubRip."""
    milissegundos = round(segundos * 1000)
    horas, resto = divmod(milissegundos, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    inteiros, milissegundos = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{inteiros:02d},{milissegundos:03d}"


def texto_txt(trechos: Iterable[Trecho]) -> str:
    return "".join(f"[{hhmmss(trecho.inicio)}] {trecho.texto}\n" for trecho in trechos)


def texto_srt(trechos: Iterable[Trecho]) -> str:
    return "".join(
        f"{numero}\n{tempo_srt(trecho.inicio)} --> {tempo_srt(trecho.fim)}\n{trecho.texto}\n\n"
        for numero, trecho in enumerate(trechos, start=1)
    )


def gravar(trechos: list[Trecho], pasta: Path, nome: str) -> tuple[Path, Path]:
    """Grava <nome>.txt e <nome>.srt em UTF-8, com quebra de linha \\n."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_txt, caminho_srt = pasta / f"{nome}.txt", pasta / f"{nome}.srt"
    caminho_txt.write_text(texto_txt(trechos), encoding="utf-8", newline="\n")
    caminho_srt.write_text(texto_srt(trechos), encoding="utf-8", newline="\n")
    return caminho_txt, caminho_srt


def carregar_modelo(nome: str):
    """Abre o modelo do Whisper; sem o pacote, encerra com a instrução de instalação."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(SEM_PACOTE) from None
    # int8 na CPU: roda em notebook sem placa de vídeo, com pouca perda de qualidade.
    return WhisperModel(nome, device="cpu", compute_type="int8")


def transcrever(gravacao: Path, modelo: str, idioma: str) -> Iterator[Trecho]:
    """Devolve os trechos à medida que o modelo avança na gravação."""
    # O filtro de voz (VAD) pula os silêncios, onde o Whisper costuma inventar texto.
    segmentos, _ = carregar_modelo(modelo).transcribe(str(gravacao), language=idioma, vad_filter=True)
    for segmento in segmentos:
        texto = segmento.text.strip()
        if texto:
            yield Trecho(segmento.start, segmento.end, texto)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transcreve áudio ou vídeo com o faster-whisper.")
    parser.add_argument("gravacao", type=Path, help="áudio ou vídeo (mp3, m4a, wav, mp4...)")
    parser.add_argument(
        "--modelo", default="small", help="tiny, base, small, medium, large-v3 ou a pasta de um modelo (padrão: small)"
    )
    parser.add_argument("--idioma", default="pt", help="idioma falado na gravação (padrão: pt)")
    parser.add_argument("--saida", type=Path, help="pasta dos arquivos gerados (padrão: a da gravação)")
    args = parser.parse_args(argv)
    if not args.gravacao.is_file():
        parser.error(f"arquivo não encontrado: {args.gravacao}")

    # O texto pode ter caractere que o console do Windows não mostra; melhor trocar do que parar.
    sys.stdout.reconfigure(errors="replace")
    trechos = []
    for trecho in transcrever(args.gravacao, args.modelo, args.idioma):
        print(f"[{hhmmss(trecho.inicio)}] {trecho.texto}", flush=True)
        trechos.append(trecho)
    caminho_txt, caminho_srt = gravar(trechos, args.saida or args.gravacao.parent, args.gravacao.stem)
    print(f"\n{len(trechos)} trechos gravados em {caminho_txt} e {caminho_srt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
