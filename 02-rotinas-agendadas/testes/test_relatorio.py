"""Testes do e-mail do funil: totais que batem com os dados gerados, formatos brasileiros, o visual e o .eml."""

import base64
import email
import email.policy
import html
import random
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import relatorio_diario as relatorio  # noqa: E402

DIA = date(2026, 11, 16)
ULTIMA = len(relatorio.ETAPAS) - 1
UTIL = relatorio.LARGURA - 2 - 2 * relatorio.RESPIRO  # largura do conteúdo do cartão do funil


def linha_total(pagina: str) -> list[str]:
    """Células da linha "Total" da tabela de canais, como texto."""
    linha = re.search(r"<tr><td[^>]*>Total</td>(.*?)</tr>", pagina, re.S).group(1)
    return [html.unescape(re.sub(r"<[^>]+>", "", celula)) for celula in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]


def texto_visivel(pagina: str) -> str:
    """O texto que aparece na tela: sem o <head>, sem a prévia escondida e sem as tags."""
    corpo = pagina.split("</head>", 1)[1]
    corpo = re.sub(r'<div style="display:none;.*?</div>', "", corpo, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", corpo)))


def barras_do_funil(pagina: str) -> list[tuple[int, str, str]]:
    """(largura, cor, conteúdo) de cada barra do funil, na ordem."""
    achadas = re.findall(r'<td width="(\d+)" height="\d+" bgcolor="(#[0-9a-f]{6})"[^>]*>(<table.*?</table>|&nbsp;)</td>', pagina, re.S)
    return [(int(largura), cor, conteudo) for largura, cor, conteudo in achadas if cor in relatorio.RAMPA_FUNIL]


class TestRelatorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.simulacoes = relatorio.gerar_simulacoes(random.Random(relatorio.SEMENTE))
        cls.resumo = relatorio.resumir(cls.simulacoes)
        cls.html = relatorio.montar_html(cls.resumo, DIA)

    def test_funil_bate_com_as_simulacoes(self):
        esperado = [sum(s.etapa >= etapa for s in self.simulacoes) for etapa in range(len(relatorio.ETAPAS))]
        self.assertEqual(self.resumo.funil, esperado)
        self.assertEqual(self.resumo.simulacoes, len(self.simulacoes))
        self.assertEqual(self.resumo.funil, sorted(self.resumo.funil, reverse=True), "o funil só pode encolher")

    def test_canais_somam_os_totais(self):
        canais = self.resumo.canais.values()
        pagas = [s for s in self.simulacoes if s.etapa == ULTIMA]
        self.assertEqual(sum(c.simulacoes for c in canais), len(self.simulacoes))
        self.assertEqual(sum(c.pagas for c in canais), len(pagas))
        self.assertEqual(self.resumo.volume, sum(s.valor for s in pagas))

    def test_linha_total_do_email_mostra_os_totais_dos_dados(self):
        pagas = [s for s in self.simulacoes if s.etapa == ULTIMA]
        esperado = [
            relatorio.numero(len(self.simulacoes)),
            relatorio.numero(len(pagas)),
            relatorio.parte_de(len(pagas), len(self.simulacoes)),
            relatorio.moeda(sum(s.valor for s in pagas)),
        ]
        self.assertEqual(linha_total(self.html), esperado)

    def test_email_sem_javascript_e_estilo_so_no_head(self):
        cabeca, corpo = self.html.split("</head>", 1)
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("<link", self.html.lower())
        self.assertNotIn("<style", corpo.lower(), "no corpo, todo estilo é inline")

        fonte, outlook = re.findall(r"<style>(.*?)</style>", cabeca, re.S)
        fonte = re.sub(r"base64,[A-Za-z0-9+/=]+", "base64,", fonte)
        self.assertRegex(fonte, r"^\s*@media screen \{\s*@font-face\{[^{}]*\}\s*\}\s*$", "o <style> aberto só traz a fonte")
        self.assertIn(f"<!--[if mso]><style>{outlook}</style><![endif]-->", cabeca, "o outro <style> é só do Outlook")

    def test_nunito_embutida_com_fonte_de_reserva(self):
        dados = re.search(r"base64,([A-Za-z0-9+/=]+)", self.html).group(1)
        self.assertEqual(base64.b64decode(dados), relatorio.ARQUIVO_FONTE.read_bytes())
        self.assertTrue((relatorio.ARQUIVO_FONTE.parent / "OFL.txt").exists(), "a licença vai junto com a fonte")
        familias = set(re.findall(r"font-family:([^;\"]+)", self.html.split("</head>", 1)[1]))
        self.assertEqual(familias, {"Nunito,'Segoe UI',Arial,sans-serif"}, "cada célula com a Nunito e a reserva")

    def test_degrade_tem_cor_solida_de_reserva(self):
        celulas = re.findall(r"<td[^>]*linear-gradient[^>]*>", self.html)
        self.assertTrue(celulas)
        for celula in celulas:
            self.assertIn(f'bgcolor="{relatorio.TEAL}"', celula)
            self.assertLess(
                celula.index(f"background-color:{relatorio.TEAL}"), celula.index("background-image:"),
                "a cor sólida vem antes, e o degradê por cima onde o cliente aceita",
            )

    def test_barras_do_funil_proporcionais_na_rampa_e_com_rotulo_branco(self):
        larguras = relatorio.larguras_do_funil(self.resumo.funil, UTIL)
        self.assertEqual(larguras[0], UTIL, "a entrada do funil ocupa a largura toda")
        for quantidade, largura in zip(self.resumo.funil, larguras):
            self.assertAlmostEqual(largura, quantidade / self.resumo.simulacoes * UTIL, delta=0.5)

        barras = barras_do_funil(self.html)
        self.assertEqual([(largura, cor) for largura, cor, _ in barras], list(zip(larguras, relatorio.RAMPA_FUNIL)))
        for (_, _, conteudo), etapa, quantidade in zip(barras, relatorio.ETAPAS, self.resumo.funil):
            self.assertIn(f'color:{relatorio.BRANCO};">{html.escape(etapa)}</td>', conteudo)
            self.assertIn(f'color:{relatorio.BRANCO};">{relatorio.numero(quantidade)}</td>', conteudo)

    def test_escala_do_funil_deixa_espaco_para_a_conversao(self):
        larguras = relatorio.larguras_do_funil([1000, 950, 500, 100], 600, reserva=150)
        self.assertLessEqual(larguras[1], 600 - 150)
        self.assertAlmostEqual(larguras[1] / larguras[0], 0.95, delta=0.01)
        self.assertEqual(relatorio.larguras_do_funil([0, 0], 600), [0, 0])

    def test_barra_estreita_leva_o_nome_para_fora(self):
        apertado = relatorio.Resumo([1000, 400, 120, 30, 10], self.resumo.canais)
        pagina = relatorio.montar_html(apertado, DIA)
        self.assertIn(f'color:{relatorio.BRANCO};">Proposta enviada</td>', pagina)
        self.assertIn(f'color:{relatorio.TEXTO};">Contrato pago</td>', pagina, "10 de 1.000 não comporta o nome")
        self.assertNotIn(f'color:{relatorio.BRANCO};">Contrato pago</td>', pagina)

    def test_mini_barra_e_a_parte_do_canal_no_volume(self):
        partes = re.findall(rf'<td width="(\d+)%" height="\d+" bgcolor="{relatorio.TEAL_CLARO}"', self.html)
        esperado = [round(canal.volume / self.resumo.volume * 100) for canal in self.resumo.canais.values()]
        self.assertEqual([int(parte) for parte in partes], esperado)

    def test_todo_percentual_vem_com_o_absoluto(self):
        texto = texto_visivel(self.html)
        percentuais = re.findall(r"\d+,\d%", texto)
        self.assertGreaterEqual(len(percentuais), 11)  # cartão, 4 etapas, a frase do funil e 5 linhas de canal
        self.assertEqual(len(re.findall(r"\d+,\d% · [\d.]+ de [\d.]+", texto)), len(percentuais))

    def test_email_abaixo_do_corte_do_gmail(self):
        """O Gmail corta o e-mail com mais de ~102 KB de HTML; a fonte embutida pesa uns 52 KB."""
        self.assertLess(len(self.html.encode("utf-8")), 100_000)

    def test_mesma_semente_mesmos_dados(self):
        self.assertEqual(relatorio.gerar_simulacoes(random.Random(relatorio.SEMENTE)), self.simulacoes)

    def test_formatos_brasileiros(self):
        self.assertEqual(relatorio.numero(1234567), "1.234.567")
        self.assertEqual(relatorio.moeda(1234567.5), "R$ 1.234.567,50")
        self.assertEqual(relatorio.parte_de(98, 800), "12,3% · 98 de 800")
        self.assertEqual(relatorio.parte_de(0, 0), "0,0% · 0 de 0")
        self.assertEqual(relatorio.por_extenso(DIA), "Segunda-feira, 16 de novembro de 2026")

    def test_eml_tem_texto_e_html(self):
        mensagem = relatorio.montar_email(self.resumo, DIA, self.html, "a@x.example", ["b@x.example"])
        with tempfile.TemporaryDirectory() as pasta:
            caminho_html, caminho_eml = relatorio.salvar(self.html, mensagem, DIA, Path(pasta))
            self.assertEqual(caminho_html.name, "relatorio-2026-11-16.html")
            lida = email.message_from_bytes(caminho_eml.read_bytes(), policy=email.policy.default)

        self.assertIn("16/11/2026", lida["Subject"])
        self.assertIn(relatorio.moeda(self.resumo.volume), lida.get_body(("plain",)).get_content())
        self.assertIn(relatorio.moeda(self.resumo.volume), lida.get_body(("html",)).get_content())

    def test_envio_sem_configuracao_nao_tenta_conectar(self):
        mensagem = relatorio.montar_email(self.resumo, DIA, self.html, "a@x.example", ["b@x.example"])
        with self.assertRaises(relatorio.ConfiguracaoIncompleta) as erro:
            relatorio.enviar(mensagem, {"SMTP_HOST": "smtp.x.example"})
        self.assertIn("SMTP_SENHA", str(erro.exception))


if __name__ == "__main__":
    unittest.main()
