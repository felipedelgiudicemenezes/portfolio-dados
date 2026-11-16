"""Testes do executor: trava, novas tentativas, tempo limite e arquivo de estado."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJETO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJETO))

import rotina  # noqa: E402

PYTHON = sys.executable


def em_python(codigo: str) -> list[str]:
    return [PYTHON, "-c", codigo]


def pid_de_processo_encerrado() -> int:
    processo = subprocess.run(em_python("import os; print(os.getpid())"), capture_output=True, text=True, check=True)
    return int(processo.stdout)


class ComPastaTemporaria(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)

    def estado(self, nome: str) -> dict:
        return json.loads((self.pasta / "estado" / f"{nome}.json").read_text(encoding="utf-8"))


class TestTrava(ComPastaTemporaria):
    def test_segunda_execucao_e_pulada_enquanto_a_primeira_roda(self):
        trava = self.pasta / "estado" / "lenta.trava"
        marca = self.pasta / "segunda_rodou.txt"
        primeira = subprocess.Popen(
            [PYTHON, str(PROJETO / "rotina.py"), "lenta", "--pasta", str(self.pasta), "--", *em_python("import time; time.sleep(3)")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            prazo = time.monotonic() + 20
            while not trava.exists():
                self.assertLess(time.monotonic(), prazo, "a primeira execução não criou a trava")
                time.sleep(0.05)
            codigo = rotina.executar("lenta", em_python(f"open(r'{marca}', 'w').close()"), pasta=self.pasta)
        finally:
            primeira.wait(timeout=60)

        self.assertEqual(codigo, rotina.SAIDA_OCUPADA)
        self.assertFalse(marca.exists(), "a segunda execução não podia ter rodado o comando")
        self.assertEqual(primeira.returncode, rotina.SAIDA_OK)
        self.assertFalse(trava.exists(), "a primeira execução devia liberar a trava ao terminar")

    def test_trava_de_processo_que_morreu_e_liberada(self):
        trava = self.pasta / "estado" / "carga.trava"
        trava.parent.mkdir(parents=True)
        trava.write_text(json.dumps({"pid": pid_de_processo_encerrado()}), encoding="utf-8")

        codigo = rotina.executar("carga", em_python("print('ok')"), pasta=self.pasta)

        self.assertEqual(codigo, rotina.SAIDA_OK)
        self.assertFalse(trava.exists())

    def test_trava_alem_da_validade_e_liberada_mesmo_com_o_pid_vivo(self):
        caminho = self.pasta / "carga.trava"
        caminho.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        self.assertFalse(rotina.Trava(caminho, validade_s=600).adquirir())

        duas_horas_atras = time.time() - 7200
        os.utime(caminho, (duas_horas_atras, duas_horas_atras))
        self.assertTrue(rotina.Trava(caminho, validade_s=600).adquirir())


class TestTentativas(ComPastaTemporaria):
    def test_erro_passageiro_repete_com_espera_crescente(self):
        contador = self.pasta / "contador.txt"
        falha_duas_vezes = (
            f"import pathlib, sys; p = pathlib.Path(r'{contador}'); "
            "n = int(p.read_text()) if p.exists() else 0; p.write_text(str(n + 1)); "
            "sys.exit(75 if n < 2 else 0)"
        )
        esperas = []

        codigo = rotina.executar(
            "instavel", em_python(falha_duas_vezes), tentativas=5, espera_s=10, pasta=self.pasta, dormir=esperas.append
        )

        self.assertEqual(codigo, rotina.SAIDA_OK)
        self.assertEqual(esperas, [10, 20])
        self.assertEqual(self.estado("instavel")["tentativas"], 3)

    def test_esgota_as_tentativas_e_devolve_o_codigo_passageiro(self):
        esperas = []
        codigo = rotina.executar(
            "fora_do_ar", em_python("import sys; sys.exit(75)"), tentativas=4, espera_s=1, pasta=self.pasta,
            dormir=esperas.append,
        )
        self.assertEqual(codigo, rotina.SAIDA_PASSAGEIRA)
        self.assertEqual(esperas, [1, 2, 4])

    def test_erro_definitivo_nao_repete(self):
        esperas = []
        codigo = rotina.executar(
            "quebrada", em_python("import sys; sys.exit(1)"), tentativas=3, espera_s=1, pasta=self.pasta,
            dormir=esperas.append,
        )
        self.assertEqual(codigo, 1)
        self.assertEqual(esperas, [])
        self.assertEqual(self.estado("quebrada")["tentativas"], 1)


class TestEstado(ComPastaTemporaria):
    def test_sucesso_grava_estado_e_log(self):
        codigo = rotina.executar("carga", em_python("print('1.234 propostas copiadas')"), pasta=self.pasta)

        estado = self.estado("carga")
        self.assertEqual(codigo, rotina.SAIDA_OK)
        self.assertEqual(estado["resultado"], "ok")
        self.assertEqual(estado["codigo_saida"], 0)
        self.assertIsNone(estado["erro"])
        self.assertLessEqual(estado["inicio"], estado["fim"])
        self.assertGreaterEqual(estado["duracao_s"], 0)
        log = (self.pasta / "logs" / "carga.log").read_text(encoding="utf-8")
        self.assertIn("1.234 propostas copiadas", log)

    def test_erro_grava_estado_com_a_mensagem(self):
        codigo = rotina.executar("carga", em_python("import sys; sys.exit('arquivo de entrada vazio')"), pasta=self.pasta)

        estado = self.estado("carga")
        self.assertEqual(codigo, 1)
        self.assertEqual(estado["resultado"], "erro")
        self.assertEqual(estado["codigo_saida"], 1)
        self.assertIn("arquivo de entrada vazio", estado["erro"])
        self.assertIsNotNone(estado["fim"])

    def test_tempo_limite_encerra_o_comando(self):
        inicio = time.monotonic()
        codigo = rotina.executar("lenta", em_python("import time; time.sleep(30)"), tempo_limite_s=1, pasta=self.pasta)

        self.assertEqual(codigo, rotina.SAIDA_TEMPO_ESGOTADO)
        self.assertLess(time.monotonic() - inicio, 20)
        self.assertIn("Tempo limite de 1 s", self.estado("lenta")["erro"])

    def test_comando_inexistente(self):
        codigo = rotina.executar("fantasma", ["comando-que-nao-existe-123"], pasta=self.pasta)
        self.assertEqual(codigo, rotina.SAIDA_NAO_INICIOU)
        self.assertEqual(self.estado("fantasma")["resultado"], "erro")


if __name__ == "__main__":
    unittest.main()
