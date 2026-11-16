"""Gera a carteira uma vez só, numa pasta temporária, para os testes que precisam dela."""

import atexit
import tempfile
from functools import cache
from pathlib import Path

from gerar_carteira import gerar


@cache
def caminho_da_carteira() -> Path:
    pasta = tempfile.TemporaryDirectory()
    atexit.register(pasta.cleanup)
    caminho = Path(pasta.name) / "carteira.sqlite"
    gerar(caminho)
    return caminho
