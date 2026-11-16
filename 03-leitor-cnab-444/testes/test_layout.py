"""O layout cobre as 444 posições de cada registro, sem buraco nem sobreposição."""

import unittest

from layout import (OCORRENCIAS, REGISTROS, SEQUENCIAL, TAMANHO_LINHA, TIPO_REGISTRO, Campo,
                    Tipo, brancos, conferir_cobertura)


def campo(nome, inicio, fim):
    return Campo(nome, inicio, fim, Tipo.NUMERICO)


class TestLayout(unittest.TestCase):
    def test_cada_registro_cobre_as_posicoes_1_a_444(self):
        for registro in REGISTROS.values():
            with self.subTest(registro=registro.nome):
                self.assertEqual(conferir_cobertura(registro.campos), [])
                ocupadas = [p for c in registro.campos for p in range(c.inicio, c.fim + 1)]
                self.assertEqual(ocupadas, list(range(1, TAMANHO_LINHA + 1)))

    def test_tipo_na_posicao_1_e_sequencial_em_439_a_444(self):
        self.assertEqual((SEQUENCIAL.inicio, SEQUENCIAL.fim), (439, 444))
        for registro in REGISTROS.values():
            with self.subTest(registro=registro.nome):
                self.assertIs(registro.campos[0], TIPO_REGISTRO)
                self.assertIs(registro.campos[-1], SEQUENCIAL)

    def test_tabela_de_ocorrencias(self):
        self.assertEqual(set(OCORRENCIAS), {"01", "06", "09", "14"})


class TestConferirCobertura(unittest.TestCase):
    def test_acusa_buraco_no_meio(self):
        problemas = conferir_cobertura([campo("a", 1, 10), campo("b", 12, 444)])
        self.assertEqual(problemas, ["buraco: posição 11 sem campo (antes de b)"])

    def test_acusa_buraco_no_fim(self):
        problemas = conferir_cobertura([campo("a", 1, 400), brancos(401, 438)])
        self.assertEqual(problemas, ["buraco: posições 439 a 444 sem campo (no fim da linha)"])

    def test_acusa_sobreposicao(self):
        problemas = conferir_cobertura([campo("a", 1, 10), campo("b", 10, 444)])
        self.assertEqual(len(problemas), 1)
        self.assertIn("sobreposição: b começa na posição 10", problemas[0])

    def test_acusa_campo_alem_da_posicao_444(self):
        problemas = conferir_cobertura([campo("a", 1, 440), campo("b", 441, 450)])
        self.assertEqual(problemas, ["os campos passam da posição 444 e vão até a 450"])


if __name__ == "__main__":
    unittest.main()
