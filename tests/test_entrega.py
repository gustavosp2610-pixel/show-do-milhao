"""Testes mínimos antes da entrega (lista do professor), versão terminal/Python.

Rodam sem internet e sem credenciais: um "Supabase falso" em memória faz o
papel do banco, inclusive quedas de conexão.
"""
import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

# O CI não instala dependências: simula os pacotes externos antes de importar.
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *a, **k: None))
sys.modules.setdefault("supabase", types.SimpleNamespace(Client=object, create_client=lambda *a, **k: None))

import database  # noqa: E402
import main  # noqa: E402
from config import AppConfig  # noqa: E402
from database import DatabaseError, SupabaseRepository  # noqa: E402
from game_logic import PartidaShowDoMilhao, TABELA_PREMIOS, solicitar_apelido  # noqa: E402

NIVEIS = ("facil", "media", "dificil")


def perguntas(corretas="A"):
    """18 perguntas (6 por nível). `corretas` define a letra certa de cada uma, em ordem."""
    itens = []
    for nivel in NIVEIS:
        for i in range(6):
            n = len(itens)
            itens.append({
                "id": n + 1, "enunciado": f"Pergunta {nivel} {i}",
                "alternativa_a": "a", "alternativa_b": "b", "alternativa_c": "c", "alternativa_d": "d",
                "correta": corretas[n % len(corretas)], "dificuldade": nivel,
            })
    return itens


def jogar(entradas, lista=None):
    partida = PartidaShowDoMilhao(1, "Jogador", lista or perguntas())
    with patch("builtins.input", side_effect=entradas), redirect_stdout(io.StringIO()) as saida:
        resultado = partida.executar()
    return partida, resultado, saida.getvalue()


# ---------- Supabase falso ----------
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, banco, tabela):
        self.banco, self.tabela, self.filtros, self.acao, self.payload = banco, tabela, [], "select", None

    def select(self, *_):
        return self

    def eq(self, coluna, valor):
        self.filtros.append((coluna, valor))
        return self

    def upsert(self, payload, on_conflict=None):
        self.acao, self.payload = "upsert", payload
        return self

    def insert(self, payload):
        self.acao, self.payload = "insert", payload
        return self

    def execute(self):
        return self.banco.executar(self)


class SupabaseFalso:
    """Banco em memória. `falhas` = quantas gravações seguidas dão erro de rede;
    `perde_resposta` = grava, mas a resposta "se perde" (timeout depois do commit)."""

    def __init__(self, partidas=None, falhas=0, perde_resposta=0, consulta_falha=False):
        self.tabelas = {"jogos": {1: {"id": 1, "nome": "Show do Milhão"}}, "partidas": {}, "perguntas": {}}
        for p in partidas or []:
            self.tabelas["partidas"][p["id"]] = dict(p)
        self.falhas, self.perde_resposta, self.consulta_falha = falhas, perde_resposta, consulta_falha
        self.gravacoes = 0

    def table(self, nome):
        return _Query(self, nome)

    def executar(self, q):
        linhas = self.tabelas.setdefault(q.tabela, {})
        if q.acao == "select":
            if self.consulta_falha and q.tabela == "partidas":
                raise ConnectionError("Falha simulada de consulta")
            dados = [dict(r) for r in linhas.values() if all(r.get(c) == v for c, v in q.filtros)]
            return _Resp(dados)
        self.gravacoes += 1
        if self.falhas:
            self.falhas -= 1
            raise ConnectionError("Sem conexão (falha simulada)")
        chave = q.payload["id"]
        linhas[chave] = dict(q.payload)  # upsert/insert por id: nunca duplica
        if self.perde_resposta:
            self.perde_resposta -= 1
            raise TimeoutError("Resposta perdida depois de gravar (simulado)")
        return _Resp([dict(q.payload)])


def repositorio(banco, jogo_id=1):
    with patch.object(database, "create_client", lambda *a, **k: banco):
        return SupabaseRepository(AppConfig("https://exemplo.supabase.co", "sb_secret_x", jogo_id))


def partida_salva(id_, apelido, valor, tempo, data="2026-11-05T10:00:00+00:00", jogo_id=1):
    return {"id": id_, "jogo_id": jogo_id, "apelido": apelido, "valor_ganho": valor, "tempo_segundos": tempo,
            "acertos": 0, "motivo_encerramento": "erro", "data_hora": data}


# ---------- 1. Vitória ----------
class T1Vitoria(unittest.TestCase):
    def test_nove_acertos_paga_um_milhao_sem_somar(self):
        _, r, _ = jogar(["A"] * 9)
        self.assertEqual(r.motivo_encerramento, "vitoria")
        self.assertEqual(r.acertos, 9)
        self.assertEqual(r.valor_ganho, 1_000_000.0)
        self.assertNotEqual(r.valor_ganho, sum(TABELA_PREMIOS))  # 1.891.000 seria somar as etapas


# ---------- 2. Erros e desistência ----------
class T2ErroEDesistencia(unittest.TestCase):
    def test_erro_na_primeira_fica_com_zero(self):
        _, r, saida = jogar(["B"])
        self.assertEqual((r.motivo_encerramento, r.valor_ganho, r.acertos), ("erro", 0.0, 0))
        self.assertIn("Correta: A", saida)

    def test_erro_depois_de_tres_acertos_fica_com_premio_da_terceira(self):
        _, r, _ = jogar(["A", "A", "A", "B"])
        self.assertEqual((r.motivo_encerramento, r.valor_ganho, r.acertos), ("erro", 10_000.0, 3))

    def test_desistencia_depois_de_dois_acertos(self):
        _, r, _ = jogar(["A", "A", "P"])
        self.assertEqual((r.motivo_encerramento, r.valor_ganho, r.acertos), ("desistencia", 5_000.0, 2))


# ---------- 3. Entradas inválidas ----------
class T3EntradasInvalidas(unittest.TestCase):
    def test_apelido_vazio_pede_de_novo(self):
        with patch("builtins.input", side_effect=["", "   ", "x" * 101, "  Ana  "]), redirect_stdout(io.StringIO()) as s:
            self.assertEqual(solicitar_apelido(), "Ana")
        self.assertEqual(s.getvalue().count("Digite um apelido de 1 a 100 caracteres."), 3)

    def test_alternativa_invalida_permite_corrigir(self):
        _, r, saida = jogar(["X", "", "AB", "9", "A"] + ["A"] * 8)
        self.assertEqual(saida.count("Opção inválida"), 4)
        self.assertEqual((r.motivo_encerramento, r.acertos), ("vitoria", 9))

    def test_responder_c_nao_ativa_as_cartas(self):
        partida, r, _ = jogar(["C", "P"], perguntas(corretas="C"))
        self.assertEqual(r.acertos, 1)
        self.assertNotIn("cartas", partida.ajudas_usadas)


# ---------- 4. Ordem das dificuldades e sem repetição ----------
class T4OrdemESemRepeticao(unittest.TestCase):
    def test_ordem_facil_media_dificil_sem_repetir_mesmo_com_pulos(self):
        partida = PartidaShowDoMilhao(1, "Jogador", perguntas())
        exibidas = []
        original = partida._exibir_pergunta
        partida._exibir_pergunta = lambda i, p, e: (exibidas.append((i, p["id"], p["dificuldade"])), original(i, p, e))
        with patch("builtins.input", side_effect=["S", "A", "A", "A", "S", "A", "A", "A", "S", "A", "A", "A"]), \
                redirect_stdout(io.StringIO()):
            r = partida.executar()
        self.assertEqual(r.acertos, 9)
        niveis_por_etapa = [p["dificuldade"] for p in partida.perguntas]
        self.assertEqual(niveis_por_etapa, ["facil"] * 3 + ["media"] * 3 + ["dificil"] * 3)
        ids_respondidas = [p["id"] for p in partida.perguntas]
        self.assertEqual(len(set(ids_respondidas)), 9)
        ids_mostradas = {pid for _, pid, _ in exibidas}
        self.assertEqual(len(ids_mostradas), 12)  # 9 respondidas + 3 puladas, nenhuma repetida
        for etapa, _, nivel in exibidas:
            self.assertEqual(nivel, NIVEIS[etapa // 3])

    def test_sorteio_do_banco_nao_repete(self):
        banco = SupabaseFalso()
        for n, p in enumerate(perguntas() + perguntas(), start=1):  # 36 perguntas, 12 por nível
            banco.tabelas["perguntas"][n] = dict(p, id=n, ativa=True)
        repo = repositorio(banco)
        for _ in range(50):  # 50 sorteios seguidos
            sorteadas = repo.buscar_perguntas_partida()
            self.assertEqual(len(sorteadas), 18)
            self.assertEqual(len({p["id"] for p in sorteadas}), 18)
            self.assertEqual([p["dificuldade"] for p in sorteadas], ["facil"] * 6 + ["media"] * 6 + ["dificil"] * 6)


# ---------- 5. Gravação e ranking ----------
class T5GravacaoERanking(unittest.TestCase):
    def test_partida_e_gravada_com_jogo_apelido_valor_e_duracao(self):
        banco = SupabaseFalso()
        _, r, _ = jogar(["A", "A", "P"])
        with redirect_stdout(io.StringIO()):
            self.assertTrue(repositorio(banco).salvar_partida_idempotente(r.para_dicionario()))
        salvo = banco.tabelas["partidas"][r.id]
        self.assertEqual((salvo["jogo_id"], salvo["apelido"], salvo["valor_ganho"]), (1, "Jogador", 5_000.0))
        self.assertIn("tempo_segundos", salvo)

    def test_empate_de_valor_menor_tempo_primeiro_e_melhor_de_cada_apelido_por_jogo(self):
        banco = SupabaseFalso(partidas=[
            partida_salva("1", "Ana", 50_000, 80.0),
            partida_salva("2", "Bia", 50_000, 40.0),        # mesmo valor, menos tempo: vem antes da Ana
            partida_salva("3", "Ana", 10_000, 5.0),         # partida pior da Ana: não aparece
            partida_salva("4", "Caio", 1_000_000, 300.0),
            partida_salva("5", "Zé", 1_000_000, 1.0, jogo_id=2),  # outro jogo: não mistura
        ])
        with redirect_stdout(io.StringIO()):
            ranking = repositorio(banco, jogo_id=1).consultar_ranking_top10()
        self.assertEqual([(r["apelido"], r["valor_ganho"]) for r in ranking],
                         [("Caio", 1_000_000), ("Bia", 50_000), ("Ana", 50_000)])
        self.assertEqual(len(banco.tabelas["partidas"]), 5)  # todas as partidas continuam guardadas
        with redirect_stdout(io.StringIO()):
            ranking2 = repositorio(banco, jogo_id=2).consultar_ranking_top10()
        self.assertEqual([r["apelido"] for r in ranking2], ["Zé"])

    def test_empate_total_desempata_pela_data(self):
        banco = SupabaseFalso(partidas=[
            partida_salva("a", "Novo", 5_000, 30.0, data="2026-11-05T12:00:00+00:00"),
            partida_salva("b", "Antigo", 5_000, 30.0, data="2026-11-05T09:00:00+00:00"),
        ])
        with redirect_stdout(io.StringIO()):
            ranking = repositorio(banco).consultar_ranking_top10()
        self.assertEqual([r["apelido"] for r in ranking], ["Antigo", "Novo"])


# ---------- 6. Falha de conexão e reenvio ----------
class T6FalhaDeConexao(unittest.TestCase):
    def test_falha_e_reenvio_grava_uma_vez_so(self):
        banco = SupabaseFalso(falhas=2)  # upsert e insert falham na 1ª tentativa
        repo = repositorio(banco)
        _, r, _ = jogar(["A", "P"])
        pendentes = []
        with patch("builtins.input", side_effect=["S"]), redirect_stdout(io.StringIO()) as saida:
            main.persistir_com_reintento(repo, r, pendentes)
        self.assertIn("Falha ao salvar partida", saida.getvalue())
        self.assertIn("Sucesso", saida.getvalue())
        self.assertEqual(list(banco.tabelas["partidas"]), [r.id])
        self.assertEqual(pendentes, [])

    def test_resposta_perdida_depois_de_gravar_nao_duplica(self):
        banco = SupabaseFalso(perde_resposta=1)  # gravou, mas o programa achou que falhou
        repo = repositorio(banco)
        _, r, _ = jogar(["A", "P"])
        with patch("builtins.input", side_effect=["S"]), redirect_stdout(io.StringIO()):
            main.persistir_com_reintento(repo, r, [])
        self.assertEqual(len(banco.tabelas["partidas"]), 1)
        self.assertGreaterEqual(banco.gravacoes, 2)  # reenviou com o mesmo UUID

    def test_desiste_de_reenviar_e_fica_pendente_para_depois(self):
        banco = SupabaseFalso(falhas=2)
        repo = repositorio(banco)
        _, r, _ = jogar(["P"])
        pendentes = []
        with patch("builtins.input", side_effect=["N"]), redirect_stdout(io.StringIO()):
            main.persistir_com_reintento(repo, r, pendentes)
        self.assertEqual(pendentes, [r])
        with patch("builtins.input", side_effect=[]), redirect_stdout(io.StringIO()):
            main.sincronizar_pendentes(repo, pendentes)  # opção 4 do menu
        self.assertEqual((pendentes, list(banco.tabelas["partidas"])), ([], [r.id]))


# ---------- 7. Reabrir, ranking vazio e falha de consulta ----------
class T7ReabrirEConsulta(unittest.TestCase):
    def test_reabrir_o_programa_mantem_os_resultados(self):
        banco = SupabaseFalso()
        _, r, _ = jogar(["A", "A", "A", "P"])
        with redirect_stdout(io.StringIO()):
            repositorio(banco).salvar_partida_idempotente(r.para_dicionario())
            ranking = repositorio(banco).consultar_ranking_top10()  # nova conexão = programa reaberto
        self.assertEqual([x["id"] for x in ranking], [r.id])

    def test_ranking_vazio(self):
        with redirect_stdout(io.StringIO()) as saida:
            main.exibir_ranking(repositorio(SupabaseFalso()))
        self.assertIn("Nenhuma partida registrada", saida.getvalue())

    def test_falha_de_consulta_do_ranking(self):
        with redirect_stdout(io.StringIO()) as saida:
            main.exibir_ranking(repositorio(SupabaseFalso(consulta_falha=True)))
        self.assertIn("Erro ao consultar o ranking", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
