"""
Módulo de acesso a dados e integração com o Supabase.
Gerencia a conexão, validação do jogo_id na tabela 'jogos', sorteio de perguntas,
consulta ao ranking com deduplicação por apelido e persistência defensiva de partidas
com logs detalhados de status HTTP e erros da API.
"""

from datetime import datetime
import random
import unicodedata
from typing import Any
from supabase import Client, create_client

from config import AppConfig


class DatabaseError(Exception):
    """Exceção geral para falhas de comunicação ou consulta ao banco de dados."""
    pass


class PerguntasInsuficientesError(DatabaseError):
    """Exceção específica para quando o banco não possui perguntas suficientes."""
    pass


def _extrair_detalhes_erro_api(exc: Exception) -> str:
    """
    Inspeciona exceções lançadas pelo cliente Supabase/PostgREST/httpx para
    extrair código HTTP, código de erro Postgres (ex: 42501 RLS, 23503 FK),
    mensagem, detalhes e dica (hint).
    """
    partes: list[str] = [f"Tipo: {type(exc).__name__}"]
    for atributo in ("status_code", "code", "message", "details", "hint"):
        valor = getattr(exc, atributo, None)
        if valor:
            partes.append(f"{atributo}={valor!r}")
    texto_base = str(exc)
    if texto_base and texto_base not in " | ".join(partes):
        partes.append(f"raw={texto_base}")
    return " | ".join(partes)


def _timestamp_para_float(data_iso: Any) -> float:
    """Converte string ISO 8601 para timestamp numérico para desempate cronológico."""
    try:
        texto = str(data_iso).strip()
        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"
        return datetime.fromisoformat(texto).timestamp()
    except Exception:
        return float("inf")


class SupabaseRepository:
    """Repositório responsável pelas operações no banco de dados Supabase."""

    DIFICULDADES_ORDEM: tuple[tuple[str, int], ...] = (
        ("facil", 6),
        ("media", 6),
        ("dificil", 6),
    )

    CAMPOS_OBRIGATORIOS_PERGUNTA: set[str] = {
        "id",
        "enunciado",
        "alternativa_a",
        "alternativa_b",
        "alternativa_c",
        "alternativa_d",
        "correta",
        "dificuldade",
    }

    COLUNAS_CONTRATO_PARTIDA: tuple[str, ...] = (
        "id",
        "jogo_id",
        "apelido",
        "valor_ganho",
        "tempo_segundos",
        "acertos",
        "motivo_encerramento",
        "data_hora",
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        try:
            self.client: Client = create_client(config.supabase_url, config.supabase_key)
        except Exception as exc:
            raise DatabaseError(
                f"Falha ao inicializar o cliente do Supabase: {_extrair_detalhes_erro_api(exc)}"
            ) from exc

    def validar_ou_garantir_jogo(self) -> bool:
        """
        Verifica se o `jogo_id` configurado no .env existe na tabela `jogos`.
        Isso é essencial porque o site no GitHub Pages consulta primeiro a tabela `jogos`
        e filtra `partidas` por `jogo_id`. Se não existir, tenta cadastrar automaticamente.
        """
        jogo_id = self.config.jogo_id
        try:
            resposta = (
                self.client.table("jogos")
                .select("id, nome")
                .eq("id", jogo_id)
                .execute()
            )
            dados = resposta.data or []
            if dados:
                nome_jogo = dados[0].get("nome", "Sem nome")
                print(
                    f"[DEBUG SUPABASE] HTTP 200 OK | Jogo validado na tabela 'jogos': "
                    f"id={jogo_id} ('{nome_jogo}')"
                )
                return True

            print(
                f"[!] Aviso: jogo_id={jogo_id} não encontrado na tabela 'jogos'. "
                "Tentando cadastrar automaticamente..."
            )
            insercao = (
                self.client.table("jogos")
                .upsert({"id": jogo_id, "nome": "Show do Milhão"}, on_conflict="id")
                .execute()
            )
            if insercao.data:
                print(
                    f"[DEBUG SUPABASE] HTTP 201 CREATED | Jogo id={jogo_id} "
                    "cadastrado com sucesso na tabela 'jogos'!"
                )
                return True
            return False
        except Exception as exc:
            detalhes = _extrair_detalhes_erro_api(exc)
            print(
                f"[DEBUG SUPABASE] [!] Alerta ao verificar tabela 'jogos' para jogo_id={jogo_id}: {detalhes}\n"
                "    Dica: rode sql/schema.sql e depois sql/02_jogo_web.sql no SQL Editor do Supabase "
                "para criar a tabela 'jogos', e confira se SUPABASE_KEY é a chave secreta (sb_secret_...)."
            )
            return False

    def _validar_pergunta(self, registro: dict[str, Any]) -> dict[str, Any] | None:
        """
        Valida e sanitiza um registro de pergunta vindo do banco.
        Retorna None caso o registro esteja incompleto ou com alternativa correta inválida.
        """
        if not self.CAMPOS_OBRIGATORIOS_PERGUNTA.issubset(registro.keys()):
            return None

        correta = str(registro.get("correta", "")).strip().upper()
        if correta not in ("A", "B", "C", "D"):
            return None

        enunciado = str(registro.get("enunciado", "")).strip()
        if not enunciado:
            return None

        return {
            "id": registro["id"],
            "enunciado": enunciado,
            "alternativa_a": str(registro.get("alternativa_a", "")).strip(),
            "alternativa_b": str(registro.get("alternativa_b", "")).strip(),
            "alternativa_c": str(registro.get("alternativa_c", "")).strip(),
            "alternativa_d": str(registro.get("alternativa_d", "")).strip(),
            "correta": correta,
            "dificuldade": str(registro.get("dificuldade", "")).strip().lower(),
        }

    def buscar_perguntas_partida(self) -> list[dict[str, Any]]:
        """
        Busca 18 perguntas sem repetição: 6 por dificuldade (3 titulares + 3 reservas para pulos).
        Caso o banco possua entre 3 e 5 perguntas em algum nível, adapta a reserva para não travar,
        exigindo o mínimo estrito de 3 perguntas por nível.
        """
        perguntas_selecionadas: list[dict[str, Any]] = []
        ids_ja_utilizados: set[Any] = set()

        try:
            for dificuldade, quantidade_ideal in self.DIFICULDADES_ORDEM:
                resposta = (
                    self.client.table("perguntas")
                    .select(
                        "id, enunciado, alternativa_a, alternativa_b, "
                        "alternativa_c, alternativa_d, correta, dificuldade"
                    )
                    .eq("dificuldade", dificuldade)
                    .eq("ativa", True)
                    .execute()
                )

                dados = resposta.data or []
                perguntas_validas: list[dict[str, Any]] = []

                for item in dados:
                    pergunta_limpa = self._validar_pergunta(item)
                    if pergunta_limpa and pergunta_limpa["id"] not in ids_ja_utilizados:
                        perguntas_validas.append(pergunta_limpa)

                if len(perguntas_validas) < quantidade_ideal:
                    raise PerguntasInsuficientesError(
                        f"Banco de dados possui apenas {len(perguntas_validas)} pergunta(s) "
                        f"válida(s) de nível '{dificuldade}', mas são necessárias pelo menos "
                        f"{quantidade_ideal} para iniciar a partida."
                    )

                sorteadas = random.sample(perguntas_validas, quantidade_ideal)
                for p in sorteadas:
                    ids_ja_utilizados.add(p["id"])
                    perguntas_selecionadas.append(p)

            return perguntas_selecionadas

        except PerguntasInsuficientesError:
            raise
        except Exception as exc:
            raise DatabaseError(
                f"Erro de conexão/consulta ao buscar perguntas no Supabase: "
                f"{_extrair_detalhes_erro_api(exc)}"
            ) from exc

    def _preparar_payload_partida(self, dados_partida: dict[str, Any]) -> dict[str, Any]:
        """
        Garante que o dicionário enviado ao Supabase contenha exatamente as colunas
        e tipos definidos no contrato da tabela 'partidas'.
        """
        faltantes = [col for col in self.COLUNAS_CONTRATO_PARTIDA if col not in dados_partida]
        if faltantes:
            raise DatabaseError(
                f"Contrato de dados inválido para 'partidas'. Colunas ausentes: {', '.join(faltantes)}"
            )

        jogo_id_raw = dados_partida["jogo_id"]
        jogo_id_limpo: int | str = (
            int(jogo_id_raw)
            if isinstance(jogo_id_raw, str) and jogo_id_raw.isdigit()
            else jogo_id_raw
        )

        return {
            "id": str(dados_partida["id"]).strip(),
            "jogo_id": jogo_id_limpo,
            "apelido": str(dados_partida["apelido"]).strip(),
            "valor_ganho": float(dados_partida["valor_ganho"]),
            "tempo_segundos": round(float(dados_partida["tempo_segundos"]), 2),
            "acertos": int(dados_partida["acertos"]),
            "motivo_encerramento": str(dados_partida["motivo_encerramento"]).strip().lower(),
            "data_hora": str(dados_partida["data_hora"]).strip(),
        }

    def salvar_partida_idempotente(self, dados_partida: dict[str, Any]) -> bool:
        """
        Persiste os dados da partida na tabela 'partidas' de forma defensiva e idempotente.
        1. Valida os nomes de colunas e tipos do payload.
        2. Confirma se 'jogo_id' está cadastrado na tabela 'jogos'.
        3. Executa upsert com fallback para insert e exibe diagnóstico HTTP completo.
        """
        payload = self._preparar_payload_partida(dados_partida)

        # Confirma vínculo com a tabela 'jogos' antes de gravar a partida
        self.validar_ou_garantir_jogo()

        print(
            f"[DEBUG SUPABASE] Enviando payload para tabela 'partidas':\n"
            f"  -> id (UUID): {payload['id']}\n"
            f"  -> jogo_id: {payload['jogo_id']} (tipo: {type(payload['jogo_id']).__name__})\n"
            f"  -> apelido: {payload['apelido']!r}\n"
            f"  -> valor_ganho: {payload['valor_ganho']} (float puro)\n"
            f"  -> tempo_segundos: {payload['tempo_segundos']}s | acertos: {payload['acertos']}/9\n"
            f"  -> motivo_encerramento: {payload['motivo_encerramento']!r} | data_hora: {payload['data_hora']}"
        )

        try:
            try:
                resposta = (
                    self.client.table("partidas")
                    .upsert(payload, on_conflict="id")
                    .execute()
                )
                metodo_usado = "UPSERT"
            except Exception as erro_upsert:
                print(
                    f"[DEBUG SUPABASE] Upsert retornou aviso ({_extrair_detalhes_erro_api(erro_upsert)}). "
                    "Tentando INSERT direto..."
                )
                resposta = (
                    self.client.table("partidas")
                    .insert(payload)
                    .execute()
                )
                metodo_usado = "INSERT"

            if resposta is not None and isinstance(resposta.data, list) and len(resposta.data) > 0:
                registro_salvo = resposta.data[0]
                print(
                    f"[DEBUG SUPABASE] [HTTP 200/201 OK - {metodo_usado}] Partida gravada com sucesso!\n"
                    f"  -> Registro confirmado pelo Supabase: id={registro_salvo.get('id')} | "
                    f"jogo_id={registro_salvo.get('jogo_id')} | apelido={registro_salvo.get('apelido')!r} | "
                    f"valor_ganho={registro_salvo.get('valor_ganho')}"
                )
                return True

            print(
                "[DEBUG SUPABASE] [HTTP ERRO] Resposta vazia do Supabase (nenhuma linha retornada). "
                "Verifique as políticas RLS de SELECT/INSERT na tabela 'partidas'."
            )
            raise DatabaseError(
                "O Supabase não retornou confirmação de gravação dos dados (resposta vazia)."
            )
        except DatabaseError:
            raise
        except Exception as exc:
            detalhes_erro = _extrair_detalhes_erro_api(exc)
            print(f"[DEBUG SUPABASE] [ERRO DE API/HTTP AO SALVAR PARTIDA] {detalhes_erro}")
            raise DatabaseError(
                f"Falha ao salvar partida no Supabase (UUID: {payload.get('id')}): {detalhes_erro}"
            ) from exc

    def salvar_ajudas(self, ajudas: list[dict[str, Any]]) -> None:
        """Persiste as ajudas da partida; reenvios não devem criar duplicatas."""
        if not ajudas:
            return
        try:
            self.client.table("ajudas_utilizadas").upsert(
                ajudas, on_conflict="partida_id,pergunta_id,tipo"
            ).execute()
        except Exception as exc:
            raise DatabaseError(
                f"Falha ao salvar historico de ajudas: {_extrair_detalhes_erro_api(exc)}"
            ) from exc

    def consultar_ranking_top10(self) -> list[dict[str, Any]]:
        """
        Consulta as partidas registradas para o JOGO_ID atual e aplica exatamente
        as mesmas regras de classificação e deduplicação do site no GitHub Pages:
          1º Maior valor_ganho (decrescente)
          2º Menor tempo_segundos (crescente)
          3º Data_hora mais antiga (crescente)
          4º ID da partida (crescente)
        Exibe apenas a melhor partida de cada apelido (normalizado via NFC) e limita ao Top 10.
        """
        try:
            resposta = (
                self.client.table("partidas")
                .select(
                    "id, jogo_id, apelido, valor_ganho, acertos, "
                    "tempo_segundos, motivo_encerramento, data_hora"
                )
                .eq("jogo_id", self.config.jogo_id)
                .execute()
            )
            partidas_brutas: list[dict[str, Any]] = resposta.data or []
            print(
                f"[DEBUG SUPABASE] HTTP 200 OK | Consulta em 'partidas' (jogo_id={self.config.jogo_id}) "
                f"retornou {len(partidas_brutas)} registro(s) bruto(s)."
            )

            # Filtra registros válidos e ordena pelos 4 critérios oficiais de desempate
            partidas_validas = [
                p for p in partidas_brutas
                if p.get("id") is not None
                and isinstance(p.get("apelido"), str)
                and p.get("apelido", "").strip()
                and p.get("valor_ganho") is not None
                and p.get("tempo_segundos") is not None
            ]

            partidas_ordenadas = sorted(
                partidas_validas,
                key=lambda r: (
                    -float(r.get("valor_ganho", 0.0)),
                    float(r.get("tempo_segundos", 0.0)),
                    _timestamp_para_float(r.get("data_hora", "")),
                    str(r.get("id", "")),
                ),
            )

            # Deduplicação por apelido (mantém apenas a melhor partida de cada jogador)
            apelidos_vistos: set[str] = set()
            top10_unico: list[dict[str, Any]] = []
            for linha in partidas_ordenadas:
                chave_apelido = unicodedata.normalize("NFC", str(linha["apelido"]).strip())
                if chave_apelido in apelidos_vistos:
                    continue
                apelidos_vistos.add(chave_apelido)
                top10_unico.append(linha)
                if len(top10_unico) == 10:
                    break

            return top10_unico
        except Exception as exc:
            detalhes_erro = _extrair_detalhes_erro_api(exc)
            print(f"[DEBUG SUPABASE] [ERRO AO CONSULTAR RANKING] {detalhes_erro}")
            raise DatabaseError(
                f"Não foi possível consultar o ranking no Supabase: {detalhes_erro}"
            ) from exc
