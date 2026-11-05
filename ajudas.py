"""Simuladores das ajudas do Show do Milhão (sem acesso ao banco)."""
import random

LETRAS = ("A", "B", "C", "D")


def cartas(correta: str) -> dict:
    """Sorteia de zero a três alternativas incorretas para eliminar."""
    quantidade = random.randint(0, 3)
    erradas = [letra for letra in LETRAS if letra != correta]
    eliminadas = sorted(random.sample(erradas, quantidade))
    return {"carta": quantidade, "eliminadas": eliminadas}


def universitarios(correta: str) -> dict:
    """Três palpites simulados; cada universitário tem 65% de chance de acertar."""
    palpites = [
        correta if random.random() < 0.65
        else random.choice([letra for letra in LETRAS if letra != correta])
        for _ in range(3)
    ]
    return {"palpites": palpites}


def plateia(correta: str) -> dict:
    """Distribuição simulada de 100 votos, com tendência de acerto."""
    percentual_correto = random.randint(42, 76)
    restantes = 100 - percentual_correto
    cortes = sorted([0, random.randint(0, restantes), random.randint(0, restantes), restantes])
    distribuicao = [cortes[i + 1] - cortes[i] for i in range(3)]
    outras = [letra for letra in LETRAS if letra != correta]
    random.shuffle(distribuicao)
    votos = {correta: percentual_correto}
    votos.update(dict(zip(outras, distribuicao)))
    return {"votos": {letra: votos[letra] for letra in LETRAS}}
