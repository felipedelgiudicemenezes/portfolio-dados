"""Gerador: mesmos bytes a cada execução, exemplos versionados em dia e documentos fictícios."""

import random
import tempfile
import unittest
from pathlib import Path

import gerar_exemplo as gerador
from layout import TAMANHO_LINHA

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"

# Pesos do cálculo dos dígitos verificadores, escritos aqui à parte do gerador.
PESOS = {
    11: ([10, 9, 8, 7, 6, 5, 4, 3, 2], [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]),
    14: ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
}


def digitos_conferem(numero: str) -> bool:
    """Confere os dois dígitos verificadores de um CPF (11 dígitos) ou CNPJ (14)."""
    for pesos in PESOS[len(numero)]:
        resto = sum(int(d) * p for d, p in zip(numero, pesos)) % 11
        if int(numero[len(pesos)]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


class TestGerador(unittest.TestCase):
    def test_documentos_dos_sacados_nao_passam_na_conferencia(self):
        self.assertTrue(digitos_conferem("0" * 11))  # controle: só zeros passa no cálculo
        for titulo in gerador.gerar_titulos(random.Random(gerador.SEMENTE)):
            tamanho = 11 if titulo["tipo_inscricao_sacado"] == "01" else 14
            numero = titulo["numero_inscricao_sacado"][-tamanho:]
            with self.subTest(numero=numero):
                self.assertFalse(digitos_conferem(numero))

    def test_retorno_so_tem_ocorrencias_ate_a_data_do_arquivo(self):
        rng = random.Random(gerador.SEMENTE)
        retorno = gerador.gerar_retorno(rng, gerador.gerar_titulos(rng))
        self.assertLessEqual(max(d["data_ocorrencia"] for d in retorno), gerador.DATA_RETORNO)

    def test_mesma_semente_mesmos_arquivos(self):
        with tempfile.TemporaryDirectory() as uma, tempfile.TemporaryDirectory() as outra:
            primeira = gerador.gerar_exemplos(Path(uma))
            segunda = gerador.gerar_exemplos(Path(outra))
        self.assertEqual(primeira, segunda)

    def test_linhas_de_444_posicoes_terminadas_em_crlf(self):
        with tempfile.TemporaryDirectory() as pasta:
            gerador.gerar_exemplos(Path(pasta))
            for nome in ("remessa.rem", "retorno.ret"):
                linhas = (Path(pasta) / nome).read_bytes().split(b"\r\n")
                with self.subTest(arquivo=nome):
                    self.assertEqual(linhas.pop(), b"")
                    self.assertEqual({len(linha) for linha in linhas}, {TAMANHO_LINHA})

    def test_exemplos_versionados_estao_em_dia(self):
        with tempfile.TemporaryDirectory() as pasta:
            for nome in gerador.gerar_exemplos(Path(pasta)):
                with self.subTest(arquivo=nome):
                    # O git pode trocar CRLF por LF no checkout; o conteúdo é o que importa.
                    novo = (Path(pasta) / nome).read_bytes().replace(b"\r\n", b"\n")
                    versionado = (EXEMPLOS / nome).read_bytes().replace(b"\r\n", b"\n")
                    self.assertEqual(versionado, novo, "rode python gerar_exemplo.py")


if __name__ == "__main__":
    unittest.main()
