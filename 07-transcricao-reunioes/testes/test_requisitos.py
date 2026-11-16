"""Testes da separação de pedidos: expressões, leitura da transcrição e lista em Markdown."""

import sys
import unittest
from pathlib import Path

PROJETO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJETO))

import requisitos  # noqa: E402


class TestExpressoes(unittest.TestCase):
    def test_reconhece_pedidos_sem_ligar_para_acento_ou_maiuscula(self):
        casos = [
            ("Precisa ter a conversão no topo.", "precisa"),
            ("Os números precisam bater com o financeiro.", "precisa"),
            ("Eu queria ver uma prévia antes.", "quero"),
            ("Os números têm que caber no celular.", "tem que"),
            ("DÁ PRA filtrar por gerente?", "dá para"),
            ("da pra mostrar o absoluto?", "dá para"),
            ("Seria bom receber por e-mail.", "seria bom"),
            ("Sinto falta da hora da atualização.", "falta"),
        ]
        for fala, esperado in casos:
            with self.subTest(fala=fala):
                self.assertEqual(requisitos.expressao_de_pedido(fala), esperado)

    def test_ignora_falas_sem_pedido_e_palavras_parecidas(self):
        for fala in ("Bom dia, pessoal.", "O sistema requer atenção.", "O filtro dá trabalho.", "Fica no fim da página."):
            with self.subTest(fala=fala):
                self.assertIsNone(requisitos.expressao_de_pedido(fala))


class TestLeitura(unittest.TestCase):
    def test_le_falas_com_e_sem_falante(self):
        texto = (
            "# comentário\n"
            "[00:00:05] Diretor: Precisa ter o filtro\n"
            "por gerente.\n"
            "\n"
            "[00:01:10] trecho sem falante, como sai do Whisper\n"
            "[00:01:20] Gerente: Uma dúvida: abre no celular?\n"
        )
        falas = [(f.hora, f.falante, f.texto) for f in requisitos.ler_falas(texto)]
        self.assertEqual(
            falas,
            [
                ("00:00:05", "Diretor", "Precisa ter o filtro por gerente."),
                ("00:01:10", None, "trecho sem falante, como sai do Whisper"),
                ("00:01:20", "Gerente", "Uma dúvida: abre no celular?"),
            ],
        )


class TestMarkdown(unittest.TestCase):
    def test_lista_so_os_pedidos_com_horario_e_falante(self):
        falas = requisitos.ler_falas("[00:00:05] Diretor: Precisa ter o filtro.\n[00:00:09] Gerente: Bom dia.\n")
        markdown = requisitos.montar_markdown(falas, "reuniao.txt")

        self.assertIn("- [ ] `00:00:05` **Diretor:** Precisa ter o filtro. _(precisa)_", markdown)
        self.assertNotIn("Bom dia", markdown)
        self.assertIn("50,0% · 1 de 2", markdown)
        self.assertIn("heurística", markdown)

    def test_percentual_com_absoluto(self):
        self.assertEqual(requisitos.parte_de(98, 800), "12,3% · 98 de 800")
        self.assertEqual(requisitos.parte_de(16, 47), "34,0% · 16 de 47")
        self.assertEqual(requisitos.parte_de(0, 0), "0,0% · 0 de 0")

    def test_exemplo_do_repositorio_esta_em_dia(self):
        pasta = PROJETO / "exemplo"
        falas = requisitos.ler_falas((pasta / "reuniao-ficticia.txt").read_text(encoding="utf-8"))
        gerado = requisitos.montar_markdown(falas, "reuniao-ficticia.txt")
        self.assertEqual(gerado, (pasta / "requisitos.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
