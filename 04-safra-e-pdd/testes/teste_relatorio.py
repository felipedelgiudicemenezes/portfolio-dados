"""Relatório: fonte embutida, HTML sem dependências e cores com o contraste calculado."""

import base64
import colorsys
import re
import unittest

import graficos
import pdd
import relatorio
import safra
from carteira_de_teste import caminho_da_carteira
from comum import abrir_banco

BRANCO = graficos.FUNDO


def matiz(cor: str) -> float:
    """Matiz HSL em graus."""
    r, g, b = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


class TesteContraste(unittest.TestCase):
    def teste_valores_conhecidos_da_wcag(self):
        self.assertAlmostEqual(graficos.contraste("#ffffff", "#000000"), 21)
        self.assertAlmostEqual(graficos.contraste("#000000", "#ffffff"), 21)
        self.assertAlmostEqual(graficos.contraste(graficos.MARCA, graficos.MARCA), 1)

    def teste_texto_sobre_escolhe_o_de_mais_contraste(self):
        self.assertEqual(graficos.texto_sobre(graficos.RAMPA_TEAL[0]), BRANCO)
        self.assertEqual(graficos.texto_sobre("#f6f8fa"), graficos.TEXTO)


class TesteCores(unittest.TestCase):
    def teste_linhas_das_safras_tem_3_para_1_contra_o_branco(self):
        for quantidade in (2, 18, 40):
            for cor in graficos.rampa(safra.CORES_DAS_SAFRAS, quantidade):
                with self.subTest(quantidade=quantidade, cor=cor):
                    self.assertGreaterEqual(graficos.contraste(cor, BRANCO), 3)

    def teste_safra_mais_antiga_e_a_mais_clara(self):
        luminancias = [graficos.luminancia(cor) for cor in graficos.rampa(safra.CORES_DAS_SAFRAS, 18)]
        self.assertEqual(luminancias, sorted(luminancias, reverse=True))
        self.assertEqual(len(set(luminancias)), 18)

    def teste_faixas_da_pdd_escurecem_com_o_atraso_e_tem_3_para_1(self):
        cores = pdd.cores_das_faixas()
        self.assertEqual(len(cores), len(pdd.FAIXAS))
        luminancias = [graficos.luminancia(cor) for cor in cores]
        self.assertEqual(luminancias, sorted(luminancias, reverse=True))
        for cor in cores:
            with self.subTest(cor=cor):
                self.assertGreaterEqual(graficos.contraste(cor, BRANCO), 3)

    def teste_cada_classe_do_calor_tem_texto_com_4_5_para_1(self):
        for cor in relatorio.CALOR:
            with self.subTest(cor=cor):
                self.assertGreaterEqual(graficos.contraste(cor, graficos.texto_sobre(cor)), 4.5)
        self.assertGreaterEqual(graficos.contraste(relatorio.SEM_ATRASO, graficos.APOIO), 4.5)

    def teste_calor_vai_do_claro_ao_escuro_na_mesma_matiz(self):
        luminancias = [graficos.luminancia(cor) for cor in relatorio.CALOR]
        self.assertEqual(luminancias, sorted(luminancias, reverse=True))
        self.assertEqual(graficos.texto_sobre(relatorio.CALOR[0]), graficos.TEXTO)
        self.assertEqual(graficos.texto_sobre(relatorio.CALOR[-1]), BRANCO)
        base = matiz(graficos.RAMPA_TEAL[-1])
        for cor in relatorio.CALOR:
            with self.subTest(cor=cor):
                # Até 4 graus: nos tons bem claros, o arredondamento para 8 bits mexe um pouco na matiz.
                self.assertAlmostEqual(matiz(cor), base, delta=4)

    def teste_classes_do_calor_cobrem_o_maior_e_ele_fica_na_mais_escura(self):
        for maior in (0.004, 0.03, 0.068, 0.0866, 0.117, 0.5, 1.0):
            with self.subTest(maior=maior):
                bordas, cores = relatorio.classes_de_calor(maior)
                self.assertEqual(bordas[0], 0)
                self.assertGreaterEqual(bordas[-1], maior)
                self.assertEqual(len(cores), len(bordas) - 1)
                self.assertLessEqual(len(cores), len(relatorio.CALOR))
                self.assertLessEqual(set(cores), set(relatorio.CALOR))
                self.assertEqual(relatorio.cor_do_calor(maior, bordas, cores), relatorio.CALOR[-1])
                self.assertEqual(relatorio.cor_do_calor(0, bordas, cores), relatorio.SEM_ATRASO)

    def teste_valor_na_borda_fica_na_classe_de_baixo(self):
        bordas, cores = [0, 0.02, 0.04], ["#111111", "#222222"]
        self.assertEqual(relatorio.cor_do_calor(0.02, bordas, cores), "#111111")
        self.assertEqual(relatorio.cor_do_calor(0.021, bordas, cores), "#222222")


class TesteRelatorioMontado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with abrir_banco(caminho_da_carteira()) as conexao:
            data_base, safras = safra.calcular(conexao)
            _, linhas = pdd.calcular(conexao)
        cls.html = relatorio.montar(data_base, safras, linhas)

    def teste_fonte_nunito_embutida_e_igual_ao_arquivo(self):
        achado = re.search(
            r'@font-face \{[^}]*font-family: "Nunito";[^}]*font-weight: 400 800;[^}]*'
            r'url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\) format\("woff2"\)', self.html)
        self.assertIsNotNone(achado)
        dados = base64.b64decode(achado.group(1), validate=True)
        self.assertTrue(dados.startswith(b"wOF2"))
        self.assertEqual(dados, relatorio.FONTE_NUNITO.read_bytes())

    def teste_texto_usa_a_nunito_com_reserva_do_sistema(self):
        self.assertIn('font: 400 14px/1.5 Nunito, system-ui, "Segoe UI", sans-serif', self.html)
        self.assertIn("SIL Open Font License 1.1", self.html)

    def teste_html_sem_rede_nem_javascript(self):
        for proibido in ("<script", "<link", "@import", "url(http", 'src="http', "src='http", 'href="http'):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, self.html)

    def teste_secoes_numeradas_na_ordem(self):
        titulos = ("Curvas de safra", "Tabela das safras", "PDD por faixa de atraso", "Como ler")
        posicoes = [self.html.index(f'<span class="secao-numero">{ordem}</span><h2>{titulo}</h2>')
                    for ordem, titulo in enumerate(titulos, start=1)]
        self.assertEqual(posicoes, sorted(posicoes))

    def teste_empresa_ficticia_e_aviso_dos_dados(self):
        self.assertIn("Fintech Exemplo · carteira de consignado · dados fictícios", self.html)
        self.assertIn("dados fictícios, gerados por script", self.html)

    def teste_toda_celula_do_mapa_de_calor_tem_texto_legivel(self):
        pares = set(re.findall(r'<td style="background:(#[0-9a-f]{6});color:(#[0-9a-f]{6})"', self.html))
        self.assertGreater(len(pares), 3)
        for fundo, tinta in pares:
            with self.subTest(fundo=fundo):
                self.assertGreaterEqual(graficos.contraste(fundo, tinta), 4.5)

    def teste_uma_aba_aberta_e_seis_tabelas(self):
        self.assertEqual(self.html.count('type="radio" name="matriz"'), 6)
        self.assertEqual(self.html.count(" checked>"), 1)
        self.assertEqual(self.html.count("<table class='matriz'>"), 6)


if __name__ == "__main__":
    unittest.main()
