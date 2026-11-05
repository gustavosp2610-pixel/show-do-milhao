-- =============================================================================
-- SHOW DO MILHÃO — ESTRUTURA DO BANCO (Supabase / PostgreSQL)
--
-- Este arquivo reproduz exatamente o que está no projeto Supabase.
-- Ordem para montar um banco novo no SQL Editor:
--   1. sql/schema.sql       (este arquivo: tabelas e segurança básica)
--   2. sql/02_jogo_web.sql  (tabela jogos, ranking público e funções do jogo web)
--   3. Cadastre as perguntas (pelo menos 6 por nível; o projeto usa 8).
--      As perguntas NÃO ficam no GitHub porque o repositório é público
--      e elas contêm o gabarito.
--
-- Quem acessa o quê:
--   * Python (terminal): chave SECRETA (sb_secret_...) no .env → acesso total.
--   * Site (navegador): chave PUBLICÁVEL (sb_publishable_...) → só lê o ranking
--     e joga pelas funções web_*. Nunca vê o gabarito.
-- =============================================================================

-- 1. PERGUNTAS (gabarito confidencial) ----------------------------------------
CREATE TABLE IF NOT EXISTS public.perguntas (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    enunciado text NOT NULL CHECK (length(trim(enunciado)) > 0),
    alternativa_a text NOT NULL,
    alternativa_b text NOT NULL,
    alternativa_c text NOT NULL,
    alternativa_d text NOT NULL,
    correta char(1) NOT NULL CHECK (correta IN ('A', 'B', 'C', 'D')),
    dificuldade text NOT NULL CHECK (dificuldade IN ('facil', 'media', 'dificil')),
    categoria text NOT NULL DEFAULT 'Conhecimentos gerais',
    ativa boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS perguntas_dificuldade_idx
    ON public.perguntas(dificuldade) WHERE ativa;

-- 2. PARTIDAS (resultado final de cada jogo = ranking) ------------------------
CREATE TABLE IF NOT EXISTS public.partidas (
    id uuid PRIMARY KEY,
    jogo_id integer NOT NULL,
    apelido text NOT NULL CHECK (length(trim(apelido)) BETWEEN 1 AND 100),
    valor_ganho numeric(12,2) NOT NULL DEFAULT 0 CHECK (valor_ganho >= 0),
    tempo_segundos numeric(12,2) NOT NULL DEFAULT 0 CHECK (tempo_segundos >= 0),
    acertos integer NOT NULL DEFAULT 0 CHECK (acertos BETWEEN 0 AND 9),
    motivo_encerramento text NOT NULL CHECK (motivo_encerramento IN ('vitoria', 'erro', 'desistencia')),
    data_hora timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS partidas_ranking_idx
    ON public.partidas(jogo_id, valor_ganho DESC, acertos DESC, tempo_segundos ASC);

-- 3. AJUDAS UTILIZADAS (histórico) --------------------------------------------
CREATE TABLE IF NOT EXISTS public.ajudas_utilizadas (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    partida_id uuid NOT NULL REFERENCES public.partidas(id) ON DELETE CASCADE,
    pergunta_id bigint NOT NULL REFERENCES public.perguntas(id),
    tipo text NOT NULL CHECK (tipo IN ('cartas', 'universitarios', 'plateia', 'pulo')),
    resultado jsonb NOT NULL DEFAULT '{}'::jsonb,
    utilizada_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (partida_id, pergunta_id, tipo)
);

-- Cartas, universitários e plateia: no máximo uma vez por partida.
CREATE UNIQUE INDEX IF NOT EXISTS ajudas_unicas_por_partida
    ON public.ajudas_utilizadas(partida_id, tipo)
    WHERE tipo IN ('cartas', 'universitarios', 'plateia');
CREATE INDEX IF NOT EXISTS ajudas_pergunta_idx ON public.ajudas_utilizadas(pergunta_id);

-- 4. ETAPAS DE PREMIAÇÃO ------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.etapas_premiacao (
    etapa smallint PRIMARY KEY CHECK (etapa BETWEEN 1 AND 9),
    valor_premio numeric(12,2) NOT NULL CHECK (valor_premio > 0)
);

INSERT INTO public.etapas_premiacao (etapa, valor_premio) VALUES
    (1, 1000), (2, 5000), (3, 10000), (4, 25000), (5, 50000),
    (6, 100000), (7, 200000), (8, 500000), (9, 1000000)
ON CONFLICT (etapa) DO NOTHING;

-- 5. PARTIDAS EM ANDAMENTO NO SITE --------------------------------------------
CREATE TABLE IF NOT EXISTS public.partidas_web (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    apelido text NOT NULL CHECK (length(trim(apelido)) BETWEEN 1 AND 40),
    etapa integer NOT NULL DEFAULT 1 CHECK (etapa BETWEEN 1 AND 9),
    acertos integer NOT NULL DEFAULT 0 CHECK (acertos BETWEEN 0 AND 9),
    valor_ganho numeric(12,2) NOT NULL DEFAULT 0 CHECK (valor_ganho >= 0),
    status text NOT NULL DEFAULT 'em_andamento'
        CHECK (status IN ('em_andamento', 'vitoria', 'erro', 'desistencia')),
    pergunta_id bigint NOT NULL REFERENCES public.perguntas(id),
    perguntas_usadas bigint[] NOT NULL DEFAULT '{}'::bigint[],
    pulos_restantes integer NOT NULL DEFAULT 3 CHECK (pulos_restantes BETWEEN 0 AND 3),
    cartas_usada boolean NOT NULL DEFAULT false,
    universitarios_usado boolean NOT NULL DEFAULT false,
    plateia_usada boolean NOT NULL DEFAULT false,
    eliminadas text[] NOT NULL DEFAULT '{}'::text[],
    ajuda_estado jsonb NOT NULL DEFAULT '{}'::jsonb,
    historico_ajudas jsonb NOT NULL DEFAULT '[]'::jsonb,
    revisao integer NOT NULL DEFAULT 0 CHECK (revisao >= 0),
    iniciada_em timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now(),
    finalizada_em timestamptz,
    CONSTRAINT nome_simples CHECK (length(apelido) <= 40)
);

CREATE INDEX IF NOT EXISTS partidas_web_ativas_idx ON public.partidas_web(status, iniciada_em);
CREATE INDEX IF NOT EXISTS partidas_web_pergunta_idx ON public.partidas_web(pergunta_id);

-- 6. SEGURANÇA ----------------------------------------------------------------
-- RLS ligado em tudo e nenhum acesso direto para o navegador (anon/authenticated).
-- O sql/02_jogo_web.sql libera só a LEITURA do ranking (jogos e partidas)
-- e as funções web_* do jogo.
ALTER TABLE public.perguntas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partidas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ajudas_utilizadas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.etapas_premiacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partidas_web ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.perguntas, public.partidas, public.ajudas_utilizadas,
              public.etapas_premiacao, public.partidas_web
    FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;

COMMENT ON TABLE public.perguntas IS
    'Answers are confidential: never expose correta to browser clients.';
