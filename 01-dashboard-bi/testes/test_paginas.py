"""As páginas: recorte por perfil, arquivo autocontido e números no padrão brasileiro."""

import base64
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import build
import render

FONTES_DOS_QUADROS = [  # na ordem da página: originação, indicadores, gráfico, funil, motivos e ranking
    "sql/ranking_parceiros.sql", "sql/vendas_por_mes.sql", "sql/vendas_por_mes_canal.sql",
    "sql/funil.sql", "sql/motivos_recusa.sql", "sql/ranking_parceiros.sql",
]


class TestPaginas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        raiz = Path(cls.pasta.name)
        gerados = build.construir(raiz / "base.sqlite", raiz / "saida")
        cls.html = {caminho.stem: caminho.read_text(encoding="utf-8") for caminho in gerados}
        with closing(sqlite3.connect(raiz / "base.sqlite")) as con:
            cls.carteiras = con.execute(
                "SELECT g.id, g.nome, pa.nome FROM parceiros pa JOIN gerentes g ON g.id = pa.gerente_id"
            ).fetchall()

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def test_uma_pagina_por_perfil(self):
        self.assertEqual(sorted(self.html), ["diretoria", "gerente-1", "gerente-2", "gerente-3"])

    def test_pagina_do_gerente_nao_tem_dado_de_outro_gerente(self):
        for gerente_id in sorted({dono for dono, _, _ in self.carteiras}):
            html = self.html[f"gerente-{gerente_id}"]
            self.assertNotIn("Canal digital (sem parceiro)", html)
            for dono, nome_do_dono, parceiro in self.carteiras:
                with self.subTest(pagina=f"gerente-{gerente_id}", parceiro=parceiro):
                    if dono == gerente_id:
                        self.assertIn(parceiro, html)  # controle: a carteira dele está na página
                    else:
                        self.assertNotIn(parceiro, html)
                        self.assertNotIn(nome_do_dono, html)

    def test_diretoria_ve_todos_os_parceiros_e_o_canal_digital(self):
        for _, _, parceiro in self.carteiras:
            self.assertIn(parceiro, self.html["diretoria"])
        self.assertIn("Canal digital (sem parceiro)", self.html["diretoria"])

    def test_pagina_do_gerente_nao_tem_o_canal_digital(self):
        self.assertIn('data-canal="digital"', self.html["diretoria"])  # controle: o marcador existe
        for perfil, html in self.html.items():
            if perfil != "diretoria":
                with self.subTest(perfil):
                    self.assertNotIn('data-canal="digital"', html)  # nem cartão, nem barra, nem linha do ranking

    def test_filtros_mostram_o_recorte_da_pagina(self):
        self.assertIn("<dt>Gerente</dt><dd><span>Todos</span>", self.html["diretoria"])
        self.assertIn("<dt>Canal</dt><dd><span>Todos</span>", self.html["diretoria"])
        for gerente_id, nome in sorted({(dono, nome) for dono, nome, _ in self.carteiras}):
            html = self.html[f"gerente-{gerente_id}"]
            with self.subTest(f"gerente-{gerente_id}"):
                self.assertIn(f"<dt>Gerente</dt><dd><span>{nome}</span>", html)
                self.assertIn("<dt>Canal</dt><dd><span>Correspondentes</span>", html)

    def test_cada_quadro_tem_o_seu_fonte(self):
        for perfil, html in self.html.items():
            with self.subTest(perfil):
                achados = re.findall(r'<details class="fonte"><summary>.*?<code>(sql/\w+\.sql)</code>', html)
                self.assertEqual(achados, FONTES_DOS_QUADROS)

    def test_paginas_nao_dependem_de_nada_externo(self):
        for perfil, html in self.html.items():
            with self.subTest(perfil):
                # a fonte vai como data: URI; qualquer outro url( buscaria algo fora do arquivo
                self.assertIsNone(re.search(r"https?://|<script|<link|@import|url\((?!data:)", html))

    def test_fonte_nunito_vai_embutida(self):
        arquivo = (Path(render.__file__).resolve().parent / "fontes" / "nunito-latin.woff2").read_bytes()
        for perfil, html in self.html.items():
            with self.subTest(perfil):
                embutida = re.search(r'font-family: "Nunito";[^}]*url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\)',
                                     html)
                self.assertIsNotNone(embutida)
                self.assertEqual(base64.b64decode(embutida.group(1)), arquivo)

    def test_numeros_no_padrao_brasileiro(self):
        self.assertEqual(render.moeda(1234567.891), "R$ 1.234.567,89")
        self.assertEqual(render.moeda(-1234.5), "-R$ 1.234,50")
        self.assertEqual(render.numero(1146), "1.146")
        self.assertEqual(render.percentual_com_absoluto(12.25, 98, 800), "12,3% · 98 de 800")
        self.assertEqual(render.moeda_compacta(2_500_000), "R$ 2,5 mi")
        self.assertEqual(render.texto_variacao(-0.0149, "p.p."), "▼ 0,01 p.p.")
        self.assertEqual(render.texto_variacao(0.04, "%"), "= 0,0%")
        self.assertEqual(render.mes_abreviado("2026-10"), "out/2026")
        self.assertEqual(render.moeda_curta(666_714.08), "R$ 667 mil")
        self.assertEqual(render.moeda_curta(1_168_191.22), "R$ 1,17 mi")
        self.assertEqual(render.moeda_curta(10_500_000), "R$ 10,5 mi")
        self.assertEqual(render.fatia_do_volume(9.505, 666_714.08, 7_014_017.97), "9,5% · R$ 667 mil de R$ 7,01 mi")


if __name__ == "__main__":
    unittest.main()
