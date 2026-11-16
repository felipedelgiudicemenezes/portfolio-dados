"""Testes do painel: quando uma rotina está em dia, atrasada, com erro ou interrompida."""

import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import painel  # noqa: E402

FUSO = timezone(timedelta(hours=-3))
SEGUNDA_9H = datetime(2026, 11, 16, 9, 0, tzinfo=FUSO)
DIAS_UTEIS = ["seg", "ter", "qua", "qui", "sex"]


def estado(inicio: datetime, resultado: str = "ok", pid: int | None = None) -> dict:
    return {"inicio": inicio.isoformat(), "resultado": resultado, "pid": pid}


class TestSituacao(unittest.TestCase):
    def test_rotina_por_intervalo(self):
        config = {"intervalo_min": 15}
        self.assertEqual(painel.situacao(config, estado(SEGUNDA_9H - timedelta(minutes=20)), SEGUNDA_9H), "em dia")
        self.assertEqual(painel.situacao(config, estado(SEGUNDA_9H - timedelta(minutes=30)), SEGUNDA_9H), "atrasada")

    def test_rotina_por_horario_so_em_dia_util(self):
        config = {"horario": "08:30", "dias": DIAS_UTEIS}
        sexta_8h30 = datetime(2026, 11, 13, 8, 30, tzinfo=FUSO)
        domingo_meio_dia = datetime(2026, 11, 15, 12, 0, tzinfo=FUSO)

        self.assertEqual(painel.situacao(config, estado(sexta_8h30), domingo_meio_dia), "em dia")
        self.assertEqual(painel.situacao(config, estado(sexta_8h30), SEGUNDA_9H), "atrasada")
        segunda_8h30 = SEGUNDA_9H.replace(minute=30, hour=8)
        self.assertEqual(painel.situacao(config, estado(segunda_8h30), SEGUNDA_9H), "em dia")

    def test_dentro_da_folga_ainda_nao_esta_atrasada(self):
        config = {"horario": "08:55"}
        ontem = SEGUNDA_9H - timedelta(days=1)
        self.assertEqual(painel.situacao(config, estado(ontem.replace(hour=8, minute=55)), SEGUNDA_9H), "em dia")

    def test_erro_nunca_rodou_e_interrompida(self):
        processo = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
        pid_encerrado = int(processo.stdout)

        self.assertEqual(painel.situacao({}, None, SEGUNDA_9H), "nunca rodou")
        self.assertEqual(painel.situacao({}, estado(SEGUNDA_9H, "erro"), SEGUNDA_9H), "com erro")
        self.assertEqual(painel.situacao({}, estado(SEGUNDA_9H, "rodando", os.getpid()), SEGUNDA_9H), "rodando")
        self.assertEqual(painel.situacao({}, estado(SEGUNDA_9H, "rodando", pid_encerrado), SEGUNDA_9H), "interrompida")


class TestTextos(unittest.TestCase):
    def test_agenda(self):
        self.assertEqual(painel.agenda({"intervalo_min": 15}), "a cada 15 min")
        self.assertEqual(painel.agenda({"horario": "08:30", "dias": DIAS_UTEIS}), "seg a sex 08:30")
        self.assertEqual(painel.agenda({"horario": "02:00"}), "todo dia 02:00")
        self.assertEqual(painel.agenda({"horario": "07:00", "dias": ["seg", "qua"]}), "seg, qua 07:00")

    def test_duracao(self):
        self.assertEqual(painel.duracao(0.42), "0,4 s")
        self.assertEqual(painel.duracao(125), "2 min 05 s")
        self.assertEqual(painel.duracao(3780), "1 h 03 min")


if __name__ == "__main__":
    unittest.main()
