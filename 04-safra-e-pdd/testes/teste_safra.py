"""Curvas de safra: a regra do "ever", percentuais entre 0 e 1 e curvas que nunca descem."""

import unittest
from datetime import date
from decimal import Decimal

import safra
from carteira_de_teste import caminho_da_carteira
from comum import abrir_banco, mes_ano, meses_entre

DATA_BASE = date(2026, 6, 30)


class TesteRegraDoEver(unittest.TestCase):
    def teste_quem_atrasou_e_depois_pagou_continua_contando(self):
        parcelas = [(date(2025, 2, 10), date(2025, 4, 1))]  # pagou com 50 dias de atraso
        self.assertEqual(safra.dia_em_que_atingiu(parcelas, 30, DATA_BASE), date(2025, 3, 12))
        self.assertIsNone(safra.dia_em_que_atingiu(parcelas, 60, DATA_BASE))

    def teste_pagar_no_dia_em_que_completa_conta_como_atraso(self):
        parcelas = [(date(2025, 2, 10), date(2025, 3, 12))]
        self.assertEqual(safra.dia_em_que_atingiu(parcelas, 30, DATA_BASE), date(2025, 3, 12))

    def teste_atraso_que_nao_completou_ate_a_data_base_nao_conta(self):
        self.assertIsNone(safra.dia_em_que_atingiu([(date(2026, 6, 10), None)], 30, DATA_BASE))

    def teste_vale_a_primeira_parcela_que_completou(self):
        parcelas = [
            (date(2025, 2, 10), date(2025, 2, 10)),
            (date(2025, 3, 10), None),
            (date(2025, 4, 10), None),
        ]
        self.assertEqual(safra.dia_em_que_atingiu(parcelas, 30, DATA_BASE), date(2025, 4, 9))

    def teste_mob_e_o_fim_de_cada_mes_de_vida(self):
        nunca = {dias: None for dias in safra.ATRASOS}
        contratos = [
            safra.Contrato(date(2025, 1, 1), Decimal("1000"), {**nunca, 30: date(2025, 3, 12)}),
            safra.Contrato(date(2025, 1, 1), Decimal("3000"), nunca),
        ]
        (unica,) = safra.montar_curvas(contratos, date(2025, 6, 30))
        curva = unica.curvas[30]
        self.assertEqual([p.contratos for p in curva], [0, 0, 1, 1, 1, 1])
        self.assertEqual((curva[2].fracao_contratos, curva[2].fracao_valor), (0.5, 0.25))


class TesteCurvasDaCarteiraGerada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with abrir_banco(caminho_da_carteira()) as conexao:
            cls.data_base, cls.safras = safra.calcular(conexao)

    def curvas(self):
        for s in self.safras:
            for dias in safra.ATRASOS:
                yield f"{mes_ano(s.inicio)} {dias}+", s.curvas[dias]

    def teste_percentuais_entre_zero_e_um(self):
        for nome, curva in self.curvas():
            for ponto in curva:
                with self.subTest(curva=nome, mob=ponto.mob):
                    self.assertTrue(0 <= ponto.fracao_contratos <= 1)
                    self.assertTrue(0 <= ponto.fracao_valor <= 1)

    def teste_curvas_ever_nunca_diminuem_com_o_mob(self):
        for nome, curva in self.curvas():
            for anterior, seguinte in zip(curva, curva[1:]):
                with self.subTest(curva=nome, mob=seguinte.mob):
                    self.assertLessEqual(anterior.contratos, seguinte.contratos)
                    self.assertLessEqual(anterior.valor, seguinte.valor)

    def teste_quem_tem_90_dias_tambem_tem_60_e_30(self):
        for s in self.safras:
            for p30, p60, p90 in zip(s.curvas[30], s.curvas[60], s.curvas[90]):
                with self.subTest(safra=mes_ano(s.inicio), mob=p30.mob):
                    self.assertGreaterEqual(p30.contratos, p60.contratos)
                    self.assertGreaterEqual(p60.contratos, p90.contratos)

    def teste_cada_safra_vai_do_mob_0_ate_a_data_base(self):
        for s in self.safras:
            self.assertEqual(len(s.curvas[30]), meses_entre(s.inicio, self.data_base) + 1)


if __name__ == "__main__":
    unittest.main()
