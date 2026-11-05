"""Testes unitários: não exigem credenciais do Supabase."""
import unittest
from unittest.mock import patch

from ajudas import cartas, universitarios, plateia
from game_logic import PartidaShowDoMilhao, TABELA_PREMIOS


def perguntas_exemplo():
    itens = []
    for nivel in ("facil", "media", "dificil"):
        for indice in range(6):
            itens.append({
                "id": len(itens) + 1,
                "enunciado": f"Pergunta {nivel} {indice}",
                "alternativa_a": "Correta", "alternativa_b": "Errada B",
                "alternativa_c": "Errada C", "alternativa_d": "Errada D",
                "correta": "A", "dificuldade": nivel,
            })
    return itens


class TesteAjudas(unittest.TestCase):
    def test_cartas_nunca_eliminam_correta(self):
        for _ in range(100):
            resultado = cartas("A")
            self.assertNotIn("A", resultado["eliminadas"])
            self.assertLessEqual(len(resultado["eliminadas"]), 3)

    def test_plateia_totaliza_cem(self):
        for _ in range(100):
            resultado = plateia("A")
            self.assertEqual(sum(resultado["votos"].values()), 100)

    def test_universitarios_tres_palpites(self):
        self.assertEqual(len(universitarios("A")["palpites"]), 3)

    @patch("builtins.input", side_effect=["A"] * 9)
    def test_vitoria_com_nove_acertos(self, _):
        partida = PartidaShowDoMilhao(1, "Jogador", perguntas_exemplo())
        final = partida.executar()
        self.assertEqual(final.motivo_encerramento, "vitoria")
        self.assertEqual(final.valor_ganho, TABELA_PREMIOS[-1])
        self.assertEqual(final.acertos, 9)

    @patch("builtins.input", side_effect=["S", "A"] * 3 + ["A"] * 6)
    def test_tres_pulos(self, _):
        partida = PartidaShowDoMilhao(1, "Jogador", perguntas_exemplo())
        final = partida.executar()
        self.assertEqual(final.motivo_encerramento, "vitoria")
        self.assertEqual(partida.pulos_restantes, 0)
        self.assertEqual(len(partida.historico_ajudas), 3)

    @patch("builtins.input", side_effect=["P"])
    def test_desistencia(self, _):
        partida = PartidaShowDoMilhao(1, "Jogador", perguntas_exemplo())
        final = partida.executar()
        self.assertEqual(final.valor_ganho, 0)
        self.assertEqual(final.motivo_encerramento, "desistencia")


if __name__ == "__main__":
    unittest.main()
