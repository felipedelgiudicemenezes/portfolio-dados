"""PDD: limites das faixas, arrasto e saldo devedor."""

import unittest
from datetime import date, timedelta
from decimal import Decimal

import pdd
from carteira_de_teste import caminho_da_carteira
from comum import abrir_banco, centavos

DATA_BASE = date(2026, 6, 30)


def parcela(dias_desde_o_vencimento: int, valor: str = "100.00") -> tuple[date, Decimal]:
    """Parcela em aberto que venceu há tantos dias (negativo: ainda vai vencer)."""
    return DATA_BASE - timedelta(days=dias_desde_o_vencimento), Decimal(valor)


class TesteFaixas(unittest.TestCase):
    def teste_limites_das_faixas(self):
        casos = {0: "A", 14: "A", 15: "B", 30: "B", 31: "C", 60: "C", 61: "D", 90: "D", 91: "E",
                 120: "E", 121: "F", 150: "F", 151: "G", 180: "G", 181: "H", 1_000: "H"}
        for dias, nivel in casos.items():
            with self.subTest(dias=dias):
                self.assertEqual(pdd.classificar(dias).nivel, nivel)

    def teste_faixas_seguidas_sem_buraco(self):
        for anterior, seguinte in zip(pdd.FAIXAS, pdd.FAIXAS[1:]):
            self.assertEqual(seguinte.de, anterior.ate + 1)

    def teste_percentuais_da_tabela_de_referencia(self):
        esperado = {"A": "0.005", "B": "0.01", "C": "0.03", "D": "0.10",
                    "E": "0.30", "F": "0.50", "G": "0.70", "H": "1"}
        self.assertEqual({f.nivel: f.provisao for f in pdd.FAIXAS},
                         {nivel: Decimal(p) for nivel, p in esperado.items()})

    def teste_atraso_negativo_e_erro(self):
        with self.assertRaises(ValueError):
            pdd.classificar(-1)


class TesteArrasto(unittest.TestCase):
    def teste_contrato_inteiro_vai_para_a_faixa_da_parcela_mais_atrasada(self):
        parcelas = [parcela(200), parcela(10), parcela(-20), parcela(-50)]
        avaliacao = pdd.avaliar(parcelas, Decimal("0.02"), DATA_BASE)
        self.assertEqual(avaliacao.atraso, 200)
        self.assertEqual(avaliacao.faixa.nivel, "H")
        self.assertEqual(avaliacao.pdd, avaliacao.saldo)

    def teste_sem_a_parcela_antiga_o_mesmo_contrato_fica_em_a(self):
        avaliacao = pdd.avaliar([parcela(10), parcela(-20), parcela(-50)], Decimal("0.02"), DATA_BASE)
        self.assertEqual(avaliacao.faixa.nivel, "A")
        self.assertEqual(avaliacao.pdd, centavos(avaliacao.saldo * Decimal("0.005")))

    def teste_parcela_que_vence_na_data_base_ainda_nao_esta_atrasada(self):
        self.assertEqual(pdd.pior_atraso([parcela(0), parcela(-30)], DATA_BASE), 0)
        self.assertEqual(pdd.pior_atraso([], DATA_BASE), 0)


class TesteSaldoDevedor(unittest.TestCase):
    def teste_a_vencer_a_valor_presente_e_vencida_pelo_valor_de_face(self):
        parcelas = [parcela(45, "50.00"), parcela(-30, "102.00")]  # 102 / 1,02 = 100
        self.assertEqual(pdd.saldo_devedor(parcelas, Decimal("0.02"), DATA_BASE), Decimal("150.00"))

    def teste_desconto_pelos_dias_corridos(self):
        parcelas = [parcela(-60, "104.04")]  # dois meses: 104,04 / 1,02² = 100
        self.assertEqual(pdd.saldo_devedor(parcelas, Decimal("0.02"), DATA_BASE), Decimal("100.00"))


class TestePddDaCarteiraGerada(unittest.TestCase):
    def teste_cada_faixa_provisiona_o_seu_percentual_do_saldo(self):
        with abrir_banco(caminho_da_carteira()) as conexao:
            _, linhas = pdd.calcular(conexao)
        for linha in linhas:
            with self.subTest(faixa=linha.faixa.nivel):
                tolerancia = Decimal("0.005") * linha.contratos  # meio centavo por contrato arredondado
                self.assertLessEqual(abs(linha.pdd - linha.saldo * linha.faixa.provisao), tolerancia)
                self.assertLessEqual(linha.pdd, linha.saldo)


if __name__ == "__main__":
    unittest.main()
