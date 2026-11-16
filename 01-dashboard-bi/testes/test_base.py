"""A base fictícia: reproduzível e coerente."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import gerar_base


def despejar(caminho):
    with closing(sqlite3.connect(caminho)) as con:
        return "\n".join(con.iterdump())


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.caminho = Path(cls.pasta.name) / "base.sqlite"
        gerar_base.gerar(cls.caminho)

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def test_mesma_semente_gera_a_mesma_base(self):
        outra = Path(self.pasta.name) / "outra.sqlite"
        gerar_base.gerar(outra)
        self.assertEqual(despejar(self.caminho), despejar(outra))

    def test_regras_que_o_esquema_nao_garante(self):
        violacoes = {
            "contrato só de proposta paga":
                "SELECT COUNT(*) FROM contratos c JOIN propostas p ON p.id = c.proposta_id WHERE p.etapa <> 'paga'",
            "toda proposta paga tem contrato":
                "SELECT COUNT(*) FROM propostas p LEFT JOIN contratos c ON c.proposta_id = p.id "
                "WHERE p.etapa = 'paga' AND c.id IS NULL",
            "proposta paga não tem motivo de recusa":
                "SELECT COUNT(*) FROM propostas WHERE etapa = 'paga' AND motivo_recusa IS NOT NULL",
            "pagamento depois da criação e até a data de corte":
                "SELECT COUNT(*) FROM contratos c JOIN propostas p ON p.id = c.proposta_id "
                f"WHERE c.data_pagamento < p.data_criacao OR c.data_pagamento > '{gerar_base.FIM}'",
            "valor liberado positivo e no máximo o solicitado":
                "SELECT COUNT(*) FROM contratos c JOIN propostas p ON p.id = c.proposta_id "
                "WHERE c.valor_liberado <= 0 OR c.valor_liberado > p.valor_solicitado",
        }
        with closing(sqlite3.connect(self.caminho)) as con:
            for regra, sql in violacoes.items():
                with self.subTest(regra):
                    self.assertEqual(con.execute(sql).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
