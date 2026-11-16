"""As regras do kpis.py conferidas com contas feitas direto no SQLite."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import gerar_base
import kpis

MES = gerar_base.FIM.strftime("%Y-%m")
MES_ANTERIOR = (gerar_base.FIM.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def contas_diretas(con, gerente_id=None, mes=None):
    """Contratos, volume, prazo médio e taxa ponderada contados sem passar pelos arquivos de sql/."""
    sql = ("SELECT COUNT(*), TOTAL(valor_liberado), AVG(prazo_meses), "
           "TOTAL(taxa_mensal * valor_liberado) / TOTAL(valor_liberado) FROM contratos WHERE 1 = 1")
    argumentos = []
    if gerente_id is not None:
        sql += (" AND proposta_id IN (SELECT p.id FROM propostas p "
                "JOIN parceiros pa ON pa.id = p.parceiro_id WHERE pa.gerente_id = ?)")
        argumentos.append(gerente_id)
    if mes is not None:
        sql += " AND substr(data_pagamento, 1, 7) = ?"
        argumentos.append(mes)
    return con.execute(sql, argumentos).fetchone()


class TestKpis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        caminho = Path(cls.pasta.name) / "base.sqlite"
        gerar_base.gerar(caminho)
        cls.con = kpis.conectar(caminho)
        cls.perfis = kpis.listar_perfis(cls.con)
        cls.payloads = {perfil["id"]: kpis.montar_payload(cls.con, perfil) for perfil in cls.perfis}

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.pasta.cleanup()

    def test_soma_dos_meses_bate_com_o_total(self):
        for perfil in self.perfis:
            serie = self.payloads[perfil["id"]]["vendas_por_mes"]
            contratos, volume, _, _ = contas_diretas(self.con, perfil["gerente_id"])
            with self.subTest(perfil["id"]):
                self.assertEqual(len(serie), 12)
                self.assertEqual(sum(mes["contratos"] for mes in serie), contratos)
                self.assertAlmostEqual(sum(mes["volume"] for mes in serie), volume, places=2)

    def test_funil_nao_cresce_de_uma_etapa_para_a_seguinte(self):
        for perfil in self.perfis:
            funil = self.payloads[perfil["id"]]["funil"]
            with self.subTest(perfil["id"]):
                self.assertEqual([etapa["etapa"] for etapa in funil], list(gerar_base.ETAPAS))
                self.assertGreater(funil[0]["quantidade"], 0)
                for anterior, seguinte in zip(funil, funil[1:]):
                    self.assertLessEqual(seguinte["quantidade"], anterior["quantidade"])
                    self.assertAlmostEqual(seguinte["conversao"], 100 * seguinte["quantidade"] / anterior["quantidade"])

    def test_kpis_do_mes_batem_com_a_conta_direta(self):
        for perfil in self.perfis:
            payload = self.payloads[perfil["id"]]
            indicadores = payload["kpis"]
            contratos, volume, prazo, taxa = contas_diretas(self.con, perfil["gerente_id"], MES)
            _, volume_anterior, _, _ = contas_diretas(self.con, perfil["gerente_id"], MES_ANTERIOR)
            with self.subTest(perfil["id"]):
                self.assertEqual((payload["mes_referencia"], payload["mes_anterior"]), (MES, MES_ANTERIOR))
                self.assertEqual(indicadores["contratos"]["atual"], contratos)
                self.assertAlmostEqual(indicadores["volume"]["atual"], volume, places=2)
                self.assertAlmostEqual(indicadores["ticket_medio"]["atual"], volume / contratos, places=6)
                self.assertAlmostEqual(indicadores["prazo_medio"]["atual"], prazo, places=6)
                self.assertAlmostEqual(indicadores["taxa_media"]["atual"], taxa, places=6)
                self.assertAlmostEqual(indicadores["volume"]["variacao"],
                                       (volume / volume_anterior - 1) * 100, places=6)

    def test_ranking_fecha_com_os_kpis_e_com_o_funil(self):
        for perfil in self.perfis:
            payload = self.payloads[perfil["id"]]
            total = payload["ranking"]["total"]
            with self.subTest(perfil["id"]):
                self.assertEqual(total["contratos"], payload["kpis"]["contratos"]["atual"])
                self.assertAlmostEqual(total["volume"], payload["kpis"]["volume"]["atual"], places=2)
                self.assertEqual(total["simulacoes"], payload["funil"][0]["quantidade"])
                self.assertEqual(total["pagas"], payload["funil"][-1]["quantidade"])
                self.assertGreaterEqual(payload["em_andamento"], 0)
                self.assertEqual(payload["ranking"]["digital"] is None, perfil["gerente_id"] is not None)

    def test_gerentes_mais_o_digital_somam_a_diretoria(self):
        diretoria = self.payloads["diretoria"]
        gerentes = [payload for perfil, payload in self.payloads.items() if perfil != "diretoria"]
        digital = diretoria["ranking"]["digital"]
        for campo in ("contratos", "volume"):
            soma = sum(payload["kpis"][campo]["atual"] for payload in gerentes) + digital[campo]
            self.assertAlmostEqual(soma, diretoria["kpis"][campo]["atual"], places=2)
        for posicao, campo in ((0, "simulacoes"), (-1, "pagas")):
            soma = sum(payload["funil"][posicao]["quantidade"] for payload in gerentes) + digital[campo]
            self.assertEqual(soma, diretoria["funil"][posicao]["quantidade"])

    def test_mes_sem_venda_entra_com_zero(self):
        linhas = [{"mes": "2026-01", "contratos": 2, "volume": 10.0, "prazo_medio": 12.0, "taxa_media": 1.5}]
        serie = kpis.serie_mensal(linhas, ["2025-12", "2026-01"])
        self.assertEqual([mes["contratos"] for mes in serie], [0, 2])
        self.assertEqual([mes["ticket_medio"] for mes in serie], [None, 5.0])


if __name__ == "__main__":
    unittest.main()
