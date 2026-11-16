"""Testes do e-mail do funil: totais que batem com os dados gerados, formatos brasileiros e o .eml."""

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


def linha_total(pagina: str) -> list[str]:
    """Células da linha "Total" da tabela de canais, como texto."""
    linha = re.search(r"<tr><td[^>]*>Total</td>(.*?)</tr>", pagina, re.S).group(1)
    return [html.unescape(re.sub(r"<[^>]+>", "", celula)) for celula in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]


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

    def test_email_sem_javascript_e_com_estilo_inline(self):
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("<style", self.html.lower())
        self.assertNotIn("<link", self.html.lower())

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
