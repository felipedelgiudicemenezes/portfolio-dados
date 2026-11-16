"""Testes da conferência. Rodar da pasta do projeto:

    python -m unittest discover -s testes -v
"""

from __future__ import annotations

import io
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / "exemplo")]

import conferir  # noqa: E402
import criar_banco  # noqa: E402
import relatorio  # noqa: E402

ESQUEMA = """
CREATE TABLE parceiros (id INTEGER PRIMARY KEY, nome TEXT, uf TEXT);
CREATE TABLE propostas (id INTEGER PRIMARY KEY, parceiro_id INTEGER, criada_em TEXT, status TEXT);
CREATE VIEW aprovadas AS SELECT id, criada_em FROM propostas WHERE status = 'aprovada';
INSERT INTO propostas VALUES (1, 1, '2026-01-02 10:00:00', 'aprovada');
"""


class ComBanco(unittest.TestCase):
    """Base: um banco pequeno e uma pasta de consultas numa pasta temporária."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)
        self.banco = self.pasta / "teste.sqlite"
        with closing(sqlite3.connect(self.banco)) as conn:
            conn.executescript(ESQUEMA)
        self.consultas = self.pasta / "consultas"
        self.consultas.mkdir()

    def gravar(self, nome: str, sql: str, encoding: str = "utf-8") -> Path:
        arquivo = self.consultas / nome
        arquivo.write_text(sql, encoding=encoding)
        return arquivo

    def conferir_sql(self, sql: str, encoding: str = "utf-8") -> conferir.Conferencia:
        arquivo = self.gravar("consulta.sql", sql, encoding)
        with closing(conferir.abrir_somente_leitura(self.banco)) as conn:
            return conferir.conferir_consulta(conn, arquivo)


class TestDeclaracao(unittest.TestCase):
    def test_le_os_itens_em_minusculas(self):
        sql = "-- usa: Propostas.Status ,  parceiros.nome\nSELECT 1"
        self.assertEqual(conferir.ler_declaracao(sql), {"propostas.status", "parceiros.nome"})

    def test_junta_varias_linhas_do_topo(self):
        sql = "-- Quadro de teste\n-- usa: a.x\n--usa: b.y\nSELECT 1"
        self.assertEqual(conferir.ler_declaracao(sql), {"a.x", "b.y"})

    def test_sem_a_linha_usa_devolve_none(self):
        self.assertIsNone(conferir.ler_declaracao("-- só um comentário\nSELECT 1"))

    def test_ignora_usa_depois_do_comeco_da_consulta(self):
        self.assertIsNone(conferir.ler_declaracao("SELECT 1\n-- usa: a.x"))


class TestConferencia(ComBanco):
    def test_ok_quando_declarado_e_usado_batem(self):
        c = self.conferir_sql("-- usa: propostas.criada_em, propostas.status\n"
                              "SELECT date(criada_em), COUNT(*) FROM propostas WHERE status = 'aprovada' GROUP BY 1")
        self.assertEqual(c.status, "ok")
        self.assertEqual(c.usado, {"propostas.criada_em", "propostas.status"})

    def test_erro_quando_a_coluna_nao_existe(self):
        c = self.conferir_sql("-- usa: propostas.valor\nSELECT p.valor FROM propostas AS p")
        self.assertEqual((c.status, c.erro), ("erro", "coluna não existe: p.valor"))

    def test_erro_quando_a_tabela_nao_existe(self):
        c = self.conferir_sql("-- usa: lojistas.nome\nSELECT nome FROM lojistas")
        self.assertEqual((c.status, c.erro), ("erro", "tabela não existe: lojistas"))

    def test_erro_de_sintaxe(self):
        self.assertEqual(self.conferir_sql("SELEC 1").erro, 'erro de sintaxe perto de "SELEC"')

    def test_erro_com_mais_de_um_comando(self):
        self.assertEqual(self.conferir_sql("SELECT 1; SELECT 2;").erro, "o arquivo tem mais de um comando SQL")

    def test_erro_nao_lista_diferencas(self):
        c = self.conferir_sql("-- usa: lojistas.nome\nSELECT nome FROM lojistas")
        self.assertEqual((c.declarado_nao_usado, c.usado_nao_declarado), ([], []))

    def test_aviso_declarado_e_nao_usado(self):
        c = self.conferir_sql("-- usa: propostas.status, propostas.valor\nSELECT status FROM propostas")
        self.assertEqual(c.status, "aviso")
        self.assertEqual((c.declarado_nao_usado, c.usado_nao_declarado), (["propostas.valor"], []))

    def test_aviso_usado_e_nao_declarado(self):
        c = self.conferir_sql("-- usa: parceiros.uf\nSELECT uf FROM parceiros WHERE nome LIKE 'A%'")
        self.assertEqual(c.status, "aviso")
        self.assertEqual((c.declarado_nao_usado, c.usado_nao_declarado), ([], ["parceiros.nome"]))

    def test_aviso_sem_declaracao(self):
        c = self.conferir_sql("-- Quadro sem declaração\nSELECT uf FROM parceiros")
        self.assertEqual(c.status, "aviso")
        self.assertIsNone(c.declarado)
        self.assertEqual(c.usado_nao_declarado, ["parceiros.uf"])
        self.assertIn('sem a linha "-- usa:"', c.resumo)

    def test_count_estrela_casa_com_a_tabela_declarada(self):
        c = self.conferir_sql("-- usa: propostas\nSELECT COUNT(*) FROM propostas")
        self.assertEqual((c.status, c.usado), ("ok", {"propostas"}))

    def test_tabela_sozinha_some_quando_ha_coluna_lida(self):
        # `id` é apelido do rowid: o SQLite também avisa a leitura da tabela sem coluna.
        c = self.conferir_sql("-- usa: propostas.id\nSELECT id FROM propostas")
        self.assertEqual((c.status, c.usado), ("ok", {"propostas.id"}))

    def test_colunas_da_cte_nao_contam_so_as_das_tabelas(self):
        c = self.conferir_sql(
            "-- usa: propostas.parceiro_id, parceiros.id, parceiros.nome\n"
            "WITH t AS (SELECT parceiro_id, COUNT(*) AS n FROM propostas GROUP BY parceiro_id)\n"
            "SELECT pa.nome, t.n FROM t JOIN parceiros AS pa ON pa.id = t.parceiro_id")
        self.assertEqual((c.status, c.usado), ("ok", {"propostas.parceiro_id", "parceiros.id", "parceiros.nome"}))

    def test_visao_conta_como_tabela(self):
        c = self.conferir_sql("-- usa: aprovadas.criada_em\nSELECT criada_em FROM aprovadas")
        self.assertEqual((c.status, c.usado), ("ok", {"aprovadas.criada_em"}))

    def test_parametros_nomeados_viram_null(self):
        c = self.conferir_sql("-- usa: propostas.criada_em\n"
                              "SELECT COUNT(*) FROM propostas WHERE criada_em >= :inicio AND criada_em < :fim")
        self.assertEqual(c.status, "ok")

    def test_parametro_com_interrogacao_vira_erro_explicado(self):
        c = self.conferir_sql("-- usa: propostas.status\nSELECT COUNT(*) FROM propostas WHERE status = ?")
        self.assertEqual(c.erro, "parâmetro com ? não é aceito; use :nome")

    def test_nao_executa_a_consulta(self):
        c = self.conferir_sql("-- usa: propostas.status\nDELETE FROM propostas WHERE status = 'aprovada'")
        self.assertEqual(c.status, "ok")
        with closing(sqlite3.connect(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM propostas").fetchone(), (1,))

    def test_le_arquivo_salvo_com_bom(self):
        c = self.conferir_sql("-- usa: parceiros.uf\nSELECT uf FROM parceiros", encoding="utf-8-sig")
        self.assertEqual(c.status, "ok")


class TestRelatorios(unittest.TestCase):
    AGORA = datetime(2026, 1, 2, 9, 30)

    def test_markdown_tem_uma_linha_por_consulta_e_escapa_a_barra(self):
        c = conferir.Conferencia("a.sql", "SELECT |", frozenset(), erro='erro de sintaxe perto de "|"')
        md = relatorio.para_markdown([c], "banco.sqlite", "consultas", self.AGORA)
        self.assertIn('| `a.sql` | ✗ erro | erro de sintaxe perto de "\\|" |', md)
        self.assertIn("Gerado em: 02/01/2026 09:30", md)

    def test_html_autocontido_com_icone_e_texto_e_sql_escapado(self):
        c = conferir.Conferencia("b.sql", "SELECT '<script>'", frozenset())
        pagina = relatorio.para_html([c], "banco.sqlite", "consultas", self.AGORA)
        self.assertIn("&lt;script&gt;", pagina)
        self.assertIn('<span class="selo selo-ok"><svg', pagina)
        for externo in ("<script", "<link", "http://", "https://"):
            self.assertNotIn(externo, pagina)


class TestLinhaDeComando(ComBanco):
    def rodar(self, *args) -> tuple[int, str]:
        texto = io.StringIO()
        with redirect_stdout(texto), redirect_stderr(texto):
            codigo = conferir.main([str(a) for a in args])
        return codigo, texto.getvalue()

    def test_codigo_1_com_erro_erros_primeiro_e_os_dois_relatorios(self):
        self.gravar("a_boa.sql", "-- usa: parceiros.uf\nSELECT uf FROM parceiros")
        self.gravar("b_quebrada.sql", "-- usa: lojistas.nome\nSELECT nome FROM lojistas")
        destino = self.pasta / "saida"
        codigo, texto = self.rodar(self.banco, self.consultas, destino)
        self.assertEqual(codigo, 1)
        self.assertLess(texto.index("b_quebrada.sql"), texto.index("a_boa.sql"))
        for nome in ("relatorio.md", "relatorio.html"):
            self.assertIn("b_quebrada.sql", (destino / nome).read_text(encoding="utf-8"))

    def test_codigo_0_com_ok_e_aviso(self):
        self.gravar("boa.sql", "-- usa: parceiros.uf\nSELECT uf FROM parceiros")
        self.gravar("sem_declaracao.sql", "SELECT nome FROM parceiros")
        codigo, texto = self.rodar(self.banco, self.consultas, self.pasta / "saida")
        self.assertEqual(codigo, 0)
        self.assertIn("Total: 1 ok, 1 com aviso, 0 com erro", texto)

    def test_codigo_2_quando_o_banco_nao_existe(self):
        self.gravar("boa.sql", "SELECT 1")
        codigo, texto = self.rodar(self.pasta / "nao_existe.sqlite", self.consultas)
        self.assertEqual(codigo, 2)
        self.assertIn("Banco não encontrado", texto)

    def test_codigo_2_quando_a_pasta_nao_tem_sql(self):
        codigo, texto = self.rodar(self.banco, self.consultas)
        self.assertEqual(codigo, 2)
        self.assertIn("Nenhum arquivo .sql", texto)

    def test_codigo_2_quando_faltam_argumentos(self):
        codigo, texto = self.rodar(self.banco)
        self.assertEqual(codigo, 2)
        self.assertIn("uso: python conferir.py", texto)


class TestExemplo(unittest.TestCase):
    ESPERADO = {
        "01_propostas_por_dia.sql": "ok",
        "02_volume_liberado_por_mes.sql": "ok",
        "03_aprovacao_por_parceiro.sql": "ok",
        "04_total_de_propostas.sql": "ok",
        "05_ticket_medio_por_prazo.sql": "aviso",
        "06_parceiros_ativos_por_uf.sql": "aviso",
        "07_contratos_da_semana.sql": "aviso",
        "08_valor_pago_por_parceiro.sql": "erro",
        "09_propostas_por_lojista.sql": "erro",
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)

    def test_cada_consulta_do_exemplo_tem_o_status_esperado(self):
        banco = criar_banco.criar(self.pasta / "exemplo.sqlite")
        conferencias = conferir.conferir_pasta(banco, RAIZ / "exemplo" / "consultas")
        self.assertEqual({c.arquivo: c.status for c in conferencias}, self.ESPERADO)

    def test_banco_de_exemplo_sai_igual_com_a_mesma_semente(self):
        copias = []
        for nome in ("a.sqlite", "b.sqlite"):
            with closing(sqlite3.connect(criar_banco.criar(self.pasta / nome))) as conn:
                copias.append(list(conn.iterdump()))
        self.assertEqual(copias[0], copias[1])
        self.assertTrue(any(linha.startswith('INSERT INTO "contratos"') for linha in copias[0]))


if __name__ == "__main__":
    unittest.main()
