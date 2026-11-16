"""Tabela Price e a carteira gerada."""

import hashlib
import random
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from carteira_de_teste import caminho_da_carteira
from comum import abrir_banco, ler_data_base
from gerar_carteira import gerar, tabela_price


def impressao_digital(caminho: Path) -> str:
    """Hash de todas as linhas, em ordem: muda se qualquer número da carteira mudar."""
    soma = hashlib.sha256()
    with abrir_banco(caminho) as conexao:
        for tabela in ("parametros", "contratos", "parcelas"):
            for linha in conexao.execute(f"SELECT * FROM {tabela} ORDER BY 1, 2"):
                soma.update(repr(linha).encode())
    return soma.hexdigest()


class TesteTabelaPrice(unittest.TestCase):
    def teste_exemplo_conhecido(self):
        valor, juros, amortizacao = tabela_price(Decimal("1000"), Decimal("0.01"), 12)[0]
        self.assertEqual((valor, juros, amortizacao), (Decimal("88.85"), Decimal("10.00"), Decimal("78.85")))

    def teste_amortizacoes_fecham_o_principal_ate_o_centavo(self):
        rng = random.Random(42)
        for _ in range(500):
            principal = Decimal(rng.randint(100_000, 3_000_000)) / 100
            taxa = Decimal(rng.randint(50, 500)) / 10_000
            prazo = rng.choice((6, 12, 18, 24, 36, 48, 60, 84))
            with self.subTest(principal=principal, taxa=taxa, prazo=prazo):
                parcelas = tabela_price(principal, taxa, prazo)
                self.assertEqual(len(parcelas), prazo)
                self.assertEqual(sum(amortizacao for _, _, amortizacao in parcelas), principal)

    def teste_parcela_e_juros_mais_amortizacao_em_centavos_exatos(self):
        for valor, juros, amortizacao in tabela_price(Decimal("5432.10"), Decimal("0.0237"), 36):
            self.assertEqual(valor, juros + amortizacao)
            for parte in (valor, juros, amortizacao):
                self.assertEqual(parte, parte.quantize(Decimal("0.01")))

    def teste_so_a_ultima_parcela_absorve_a_sobra(self):
        rng = random.Random(42)
        for _ in range(200):
            principal = Decimal(100 * rng.randint(10, 300))
            taxa = Decimal(rng.randint(160, 340)) / 10_000
            prazo = rng.choice((12, 18, 24, 36, 48))
            with self.subTest(principal=principal, taxa=taxa, prazo=prazo):
                valores = [valor for valor, _, _ in tabela_price(principal, taxa, prazo)]
                self.assertEqual(len(set(valores[:-1])), 1)
                self.assertLess(abs(valores[-1] - valores[0]), Decimal("1.00"))


class TesteCarteiraGerada(unittest.TestCase):
    def teste_mesma_semente_gera_a_mesma_carteira(self):
        with tempfile.TemporaryDirectory() as pasta:
            outra = Path(pasta) / "carteira.sqlite"
            gerar(outra)
            self.assertEqual(impressao_digital(outra), impressao_digital(caminho_da_carteira()))

    def teste_nenhum_pagamento_depois_da_data_base(self):
        with abrir_banco(caminho_da_carteira()) as conexao:
            data_base = ler_data_base(conexao).isoformat()
            (depois,) = conexao.execute(
                "SELECT COUNT(*) FROM parcelas WHERE data_pagamento > ?", (data_base,)
            ).fetchone()
        self.assertEqual(depois, 0)


if __name__ == "__main__":
    unittest.main()
