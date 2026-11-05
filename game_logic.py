"""Motor do Show do Milhão: nove etapas, quatro ajudas simuladas e contrato de dados Supabase."""
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ajudas import cartas, plateia, universitarios

TABELA_PREMIOS: tuple[float, ...] = (
    1_000.0, 5_000.0, 10_000.0, 25_000.0, 50_000.0,
    100_000.0, 200_000.0, 500_000.0, 1_000_000.0,
)
ROTULO_DIFICULDADE = {"facil": "FÁCIL", "media": "MÉDIA", "dificil": "DIFÍCIL"}


def formatar_moeda(valor: float) -> str:
    """Formata um valor numérico puro apenas para exibição visual no terminal."""
    numero = f"{valor:,.2f}"
    return "R$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")


def solicitar_apelido() -> str:
    """Solicita e valida o apelido obrigatório do jogador (1 a 100 caracteres)."""
    while True:
        try:
            apelido = input("\nDigite seu apelido: ").strip()
        except EOFError:
            apelido = ""
        if apelido and len(apelido) <= 100:
            return apelido
        print("Digite um apelido de 1 a 100 caracteres.")


@dataclass
class ResultadoPartida:
    """
    Representa o contrato exato da tabela 'partidas' no Supabase:
    - id: UUID v4 em string
    - jogo_id: ID do jogo cadastrado na tabela 'jogos'
    - apelido: Nome/apelido do jogador
    - valor_ganho: Float numérico puro (ex: 10000.0)
    - tempo_segundos: Float arredondado em 2 casas decimais
    - acertos: Inteiro de 0 a 9
    - motivo_encerramento: 'vitoria', 'erro' ou 'desistencia'
    - data_hora: String ISO 8601 em UTC
    """
    id: str
    jogo_id: int | str
    apelido: str
    valor_ganho: float
    tempo_segundos: float
    acertos: int
    motivo_encerramento: str
    data_hora: str

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa os dados garantindo os tipos e nomes exatos das colunas no Supabase."""
        jogo_id_normalizado: int | str = (
            int(self.jogo_id)
            if isinstance(self.jogo_id, str) and self.jogo_id.isdigit()
            else self.jogo_id
        )
        return {
            "id": str(self.id),
            "jogo_id": jogo_id_normalizado,
            "apelido": str(self.apelido).strip(),
            "valor_ganho": float(self.valor_ganho),
            "tempo_segundos": round(float(self.tempo_segundos), 2),
            "acertos": int(self.acertos),
            "motivo_encerramento": str(self.motivo_encerramento).strip().lower(),
            "data_hora": str(self.data_hora),
        }


class PartidaShowDoMilhao:
    """Nove perguntas, três por dificuldade, e até três pulos."""

    def __init__(self, jogo_id: int | str, apelido: str,
                 perguntas: list[dict[str, Any]]) -> None:
        if len(perguntas) < 18:
            raise ValueError("São necessárias 18 perguntas: seis de cada nível.")
        self.partida_id = str(uuid.uuid4())
        self.jogo_id = jogo_id
        self.apelido = apelido
        self.perguntas: list[dict[str, Any]] = []
        self.reservas: dict[str, list[dict[str, Any]]] = {}
        for nivel in ("facil", "media", "dificil"):
            candidatas = [p for p in perguntas if p["dificuldade"] == nivel]
            if len(candidatas) < 6:
                raise ValueError(f"Faltam perguntas de nível {nivel}.")
            self.perguntas.extend(candidatas[:3])
            self.reservas[nivel] = candidatas[3:]
        if len({p["id"] for p in perguntas}) != len(perguntas):
            raise ValueError("Há perguntas duplicadas no sorteio.")
        self.acertos = 0
        self.valor_ganho = 0.0
        self.motivo_encerramento = ""
        self.tempo_segundos = 0.0
        self.pulos_restantes = 3
        self.ajudas_usadas: set[str] = set()
        self.historico_ajudas: list[dict[str, Any]] = []

    def _registrar_ajuda(self, pergunta: dict, tipo: str, resultado: dict) -> None:
        self.historico_ajudas.append({
            "partida_id": self.partida_id,
            "pergunta_id": pergunta["id"],
            "tipo": tipo,
            "resultado": resultado,
        })

    def _exibir_pergunta(self, indice: int, pergunta: dict, eliminadas: set[str]) -> None:
        numero = indice + 1
        print("\n" + "=" * 64)
        print(f"PERGUNTA {numero}/9 | {ROTULO_DIFICULDADE[pergunta['dificuldade']]}"
              f" | Valendo {formatar_moeda(TABELA_PREMIOS[indice])}")
        print(f"Jogador: {self.apelido} | Garantido: {formatar_moeda(self.valor_ganho)}")
        print("=" * 64)
        print(pergunta["enunciado"])
        for letra in "ABCD":
            print(f" [{letra}] " + (
                "(eliminada pelas cartas)" if letra in eliminadas
                else str(pergunta[f"alternativa_{letra.lower()}"])
            ))
        disponiveis = []
        if "cartas" not in self.ajudas_usadas:
            disponiveis.append("C = cartas")
        if "universitarios" not in self.ajudas_usadas:
            disponiveis.append("U = universitários")
        if "plateia" not in self.ajudas_usadas:
            disponiveis.append("L = plateia")
        if self.pulos_restantes and self.reservas[pergunta["dificuldade"]]:
            disponiveis.append(f"S = pular ({self.pulos_restantes})")
        print(" [P] Desistir | " + " | ".join(disponiveis))

    def executar(self) -> ResultadoPartida:
        print(f"\nCOMEÇOU O SHOW DO MILHÃO, {self.apelido}!")
        inicio = time.perf_counter()
        try:
            for indice in range(9):
                pergunta = self.perguntas[indice]
                eliminadas: set[str] = set()
                while True:
                    self._exibir_pergunta(indice, pergunta, eliminadas)
                    try:
                        escolha = input("Sua escolha: ").strip().upper()
                    except EOFError:
                        escolha = "P"
                    correta = str(pergunta["correta"]).upper()
                    if escolha in ("P", "PARAR", "DESISTIR"):
                        self.motivo_encerramento = "desistencia"
                        break
                    if escolha == "C" and "cartas" not in self.ajudas_usadas:
                        resultado = cartas(correta)
                        eliminadas.update(resultado["eliminadas"])
                        self.ajudas_usadas.add("cartas")
                        self._registrar_ajuda(pergunta, "cartas", resultado)
                        print(f"Cartas eliminaram: {', '.join(resultado['eliminadas']) or 'nenhuma'}.")
                        continue
                    if escolha == "U" and "universitarios" not in self.ajudas_usadas:
                        resultado = universitarios(correta)
                        self.ajudas_usadas.add("universitarios")
                        self._registrar_ajuda(pergunta, "universitarios", resultado)
                        print("Universitários: " + ", ".join(resultado["palpites"]))
                        continue
                    if escolha == "L" and "plateia" not in self.ajudas_usadas:
                        resultado = plateia(correta)
                        self.ajudas_usadas.add("plateia")
                        self._registrar_ajuda(pergunta, "plateia", resultado)
                        print("Votos da plateia: " + " | ".join(
                            f"{letra}: {votos}%" for letra, votos in resultado["votos"].items()
                        ))
                        continue
                    if escolha == "S" and self.pulos_restantes and self.reservas[pergunta["dificuldade"]]:
                        self.pulos_restantes -= 1
                        self._registrar_ajuda(pergunta, "pulo", {"etapa": indice + 1})
                        pergunta = self.reservas[pergunta["dificuldade"]].pop(0)
                        self.perguntas[indice] = pergunta
                        eliminadas = set()
                        print("Pergunta trocada! O valor do prêmio continua igual.")
                        continue
                    if escolha not in "ABCD" or len(escolha) != 1 or escolha in eliminadas:
                        print("Opção inválida ou ajuda indisponível.")
                        continue
                    if escolha == correta:
                        self.acertos += 1
                        self.valor_ganho = float(TABELA_PREMIOS[indice])
                        print(f"Certa resposta! Prêmio: {formatar_moeda(self.valor_ganho)}")
                        if self.acertos == 9:
                            self.motivo_encerramento = "vitoria"
                        break
                    self.motivo_encerramento = "erro"
                    print(f"Resposta incorreta. Correta: {correta}.")
                    break
                if self.motivo_encerramento:
                    break
        except KeyboardInterrupt:
            self.motivo_encerramento = "desistencia"
        finally:
            self.tempo_segundos = round(time.perf_counter() - inicio, 2)
        if not self.motivo_encerramento:
            self.motivo_encerramento = "vitoria"
        print(f"Fim da partida: {self.motivo_encerramento}. "
              f"Prêmio final: {formatar_moeda(self.valor_ganho)}")
        return ResultadoPartida(
            id=self.partida_id,
            jogo_id=self.jogo_id,
            apelido=self.apelido,
            valor_ganho=float(self.valor_ganho),
            tempo_segundos=round(float(self.tempo_segundos), 2),
            acertos=int(self.acertos),
            motivo_encerramento=self.motivo_encerramento,
            data_hora=datetime.now(timezone.utc).isoformat(),
        )
