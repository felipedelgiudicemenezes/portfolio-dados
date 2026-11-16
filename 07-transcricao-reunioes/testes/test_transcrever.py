"""Testes da formatação de tempo e da escrita do .txt e do .srt, com trechos falsos (sem o Whisper)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import transcrever  # noqa: E402
from transcrever import Trecho  # noqa: E402

TRECHOS = [
    Trecho(0.0, 2.5, "Bom dia, pessoal."),
    Trecho(2.5, 65.25, "Vamos começar pela dashboard."),
    Trecho(3723.4, 3725.0, "Obrigado a todos."),
]


class TestTempo(unittest.TestCase):
    def test_hhmmss_corta_a_fracao(self):
        self.assertEqual(transcrever.hhmmss(0), "00:00:00")
        self.assertEqual(transcrever.hhmmss(65.9), "00:01:05")
        self.assertEqual(transcrever.hhmmss(3 * 3600 + 25), "03:00:25")

    def test_tempo_srt_com_milissegundos(self):
        self.assertEqual(transcrever.tempo_srt(0), "00:00:00,000")
        self.assertEqual(transcrever.tempo_srt(65.25), "00:01:05,250")
        self.assertEqual(transcrever.tempo_srt(3723.4), "01:02:03,400")

    def test_tempo_srt_arredonda_sem_estourar_os_campos(self):
        self.assertEqual(transcrever.tempo_srt(59.9996), "00:01:00,000")
        self.assertEqual(transcrever.tempo_srt(3599.9999), "01:00:00,000")


class TestArquivos(unittest.TestCase):
    def test_grava_txt_e_srt(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho_txt, caminho_srt = transcrever.gravar(TRECHOS, Path(pasta), "reuniao.2026-11-04")
            txt = caminho_txt.read_bytes().decode("utf-8")
            srt = caminho_srt.read_bytes().decode("utf-8")
            nomes = (caminho_txt.name, caminho_srt.name)

        self.assertEqual(nomes, ("reuniao.2026-11-04.txt", "reuniao.2026-11-04.srt"))
        self.assertEqual(
            txt,
            "[00:00:00] Bom dia, pessoal.\n"
            "[00:00:02] Vamos começar pela dashboard.\n"
            "[01:02:03] Obrigado a todos.\n",
        )
        self.assertEqual(
            srt,
            "1\n00:00:00,000 --> 00:00:02,500\nBom dia, pessoal.\n\n"
            "2\n00:00:02,500 --> 00:01:05,250\nVamos começar pela dashboard.\n\n"
            "3\n01:02:03,400 --> 01:02:05,000\nObrigado a todos.\n\n",
        )

    def test_sem_faster_whisper_sai_com_a_instrucao_de_instalacao(self):
        with mock.patch.dict(sys.modules, {"faster_whisper": None}):
            with self.assertRaises(SystemExit) as saida:
                transcrever.carregar_modelo("small")
        self.assertIn("pip install faster-whisper", str(saida.exception.code))


if __name__ == "__main__":
    unittest.main()
