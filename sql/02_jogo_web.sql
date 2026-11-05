-- =============================================================================
-- SHOW DO MILHÃO — INTEGRAÇÃO SITE + SUPABASE (jogo web e ranking público)
-- Aplicado no projeto Supabase como a migração "jogo_web_e_ranking_publico".
-- Rode DEPOIS de sql/schema.sql (que cria perguntas, partidas, ajudas etc.).
--
-- Ideia geral:
--   * O navegador NUNCA lê a tabela perguntas (o gabarito fica só no banco).
--   * O site joga chamando funções (RPC) com a chave publicável. As funções
--     rodam no servidor do banco, conferem a resposta e guardam o estado da
--     partida em partidas_web.
--   * Ao terminar, a partida é copiada para partidas (a mesma tabela usada
--     pelo jogo em Python), então o ranking é um só.
--   * O navegador só pode LER jogos e partidas (ranking). Não pode gravar nada
--     direto nas tabelas.
-- =============================================================================

-- 1. TABELA jogos (o site e o Python filtram o ranking por jogo_id) ----------
CREATE TABLE IF NOT EXISTS public.jogos (
    id integer PRIMARY KEY,
    nome text NOT NULL CHECK (length(trim(nome)) > 0)
);

INSERT INTO public.jogos (id, nome)
VALUES (1, 'Show do Milhão')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.jogos ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'partidas_jogo_id_fkey'
    ) THEN
        ALTER TABLE public.partidas
            ADD CONSTRAINT partidas_jogo_id_fkey
            FOREIGN KEY (jogo_id) REFERENCES public.jogos(id);
    END IF;
END $$;

-- 2. RANKING PÚBLICO: o navegador só pode LER jogos e partidas ---------------
REVOKE ALL ON public.jogos, public.partidas FROM anon, authenticated;
GRANT SELECT ON public.jogos, public.partidas TO anon, authenticated;

DROP POLICY IF EXISTS "Ranking publico: ler jogos" ON public.jogos;
CREATE POLICY "Ranking publico: ler jogos"
    ON public.jogos FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "Ranking publico: ler partidas" ON public.partidas;
CREATE POLICY "Ranking publico: ler partidas"
    ON public.partidas FOR SELECT TO anon, authenticated USING (true);

-- perguntas, ajudas_utilizadas, etapas_premiacao e partidas_web continuam
-- sem nenhum acesso para anon/authenticated (REVOKE ALL das migrações antigas).

COMMENT ON TABLE public.partidas IS
    'Resultados finais (Python e site). Leitura pública para o ranking; '
    'escrita só pelo backend Python (chave secreta) ou pelas funções web_*.';
COMMENT ON TABLE public.partidas_web IS
    'Partidas em andamento do site. Acesso só pelas funções web_* (SECURITY DEFINER); '
    'token guardado como hash SHA-256. Gabarito nunca vai para o navegador.';

-- 3. FUNÇÕES INTERNAS (schema privado, invisível para o site) ----------------
CREATE SCHEMA IF NOT EXISTS privado;
REVOKE ALL ON SCHEMA privado FROM PUBLIC, anon, authenticated;

-- Etapas 1-3 fáceis, 4-6 médias, 7-9 difíceis (igual ao Python).
CREATE OR REPLACE FUNCTION privado.dificuldade_da_etapa(p_etapa integer)
RETURNS text
LANGUAGE sql IMMUTABLE
SET search_path = ''
AS $$
    SELECT CASE WHEN p_etapa <= 3 THEN 'facil'
                WHEN p_etapa <= 6 THEN 'media'
                ELSE 'dificil' END
$$;

-- Sorteia uma pergunta ativa do nível, sem repetir as já usadas na partida.
CREATE OR REPLACE FUNCTION privado.sortear_pergunta(p_dificuldade text, p_usadas bigint[])
RETURNS bigint
LANGUAGE sql VOLATILE
SET search_path = ''
AS $$
    SELECT p.id
      FROM public.perguntas p
     WHERE p.ativa
       AND p.dificuldade = p_dificuldade
       AND NOT (p.id = ANY (coalesce(p_usadas, '{}'::bigint[])))
     ORDER BY random()
     LIMIT 1
$$;

CREATE OR REPLACE FUNCTION privado.hash_token(p_token text)
RETURNS text
LANGUAGE sql IMMUTABLE
SET search_path = ''
AS $$
    SELECT encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
$$;

-- Confere partida + token e trava a linha (evita duas respostas ao mesmo tempo).
CREATE OR REPLACE FUNCTION privado.autenticar(p_partida uuid, p_token text)
RETURNS public.partidas_web
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v public.partidas_web;
BEGIN
    IF p_partida IS NULL OR p_token IS NULL OR p_token !~ '^[a-f0-9]{64}$' THEN
        RAISE EXCEPTION 'Partida não encontrada. Comece um novo jogo.'
            USING ERRCODE = 'P0001', HINT = 'PARTIDA_INVALIDA';
    END IF;

    SELECT * INTO v
      FROM public.partidas_web w
     WHERE w.id = p_partida
       AND w.token_hash = privado.hash_token(p_token)
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Partida não encontrada. Comece um novo jogo.'
            USING ERRCODE = 'P0001', HINT = 'PARTIDA_INVALIDA';
    END IF;
    RETURN v;
END;
$$;

CREATE OR REPLACE FUNCTION privado.exigir_em_andamento(v public.partidas_web)
RETURNS void
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF v.status <> 'em_andamento' THEN
        RAISE EXCEPTION 'Esta partida já terminou. Comece um novo jogo.'
            USING ERRCODE = 'P0001', HINT = 'PARTIDA_ENCERRADA';
    END IF;
END;
$$;

-- Monta o que o site pode ver. NÃO inclui a alternativa correta enquanto a
-- partida está em andamento (só revela ao errar, como no Python).
CREATE OR REPLACE FUNCTION privado.montar_estado(v public.partidas_web, p_extra jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb
LANGUAGE plpgsql STABLE
SET search_path = ''
AS $$
DECLARE
    p public.perguntas;
    v_valendo numeric;
    v_em_andamento boolean := v.status = 'em_andamento';
    v_pulo_possivel boolean;
BEGIN
    SELECT * INTO p FROM public.perguntas WHERE id = v.pergunta_id;
    SELECT valor_premio INTO v_valendo FROM public.etapas_premiacao WHERE etapa = v.etapa;

    v_pulo_possivel := v_em_andamento AND v.pulos_restantes > 0 AND EXISTS (
        SELECT 1 FROM public.perguntas q
         WHERE q.ativa AND q.dificuldade = p.dificuldade
           AND NOT (q.id = ANY (v.perguntas_usadas))
    );

    RETURN jsonb_build_object(
        'partida_id', v.id,
        'apelido', v.apelido,
        'status', v.status,
        'etapa', v.etapa,
        'total_etapas', 9,
        'dificuldade', p.dificuldade,
        'acertos', v.acertos,
        'valor_ganho', v.valor_ganho,
        'valendo', v_valendo,
        'pergunta', jsonb_build_object(
            'enunciado', p.enunciado,
            'categoria', p.categoria,
            'alternativas', jsonb_build_object(
                'A', p.alternativa_a, 'B', p.alternativa_b,
                'C', p.alternativa_c, 'D', p.alternativa_d
            )
        ),
        'eliminadas', to_jsonb(v.eliminadas),
        'ajudas', jsonb_build_object(
            'cartas', v_em_andamento AND NOT v.cartas_usada,
            'universitarios', v_em_andamento AND NOT v.universitarios_usado,
            'plateia', v_em_andamento AND NOT v.plateia_usada,
            'pulo', v_pulo_possivel,
            'pulos_restantes', v.pulos_restantes
        ),
        'ajuda_estado', v.ajuda_estado,
        'correta', CASE WHEN v.status IN ('erro', 'vitoria') THEN p.correta::text END,
        'tempo_segundos', CASE WHEN v.finalizada_em IS NOT NULL
            THEN round(extract(epoch FROM v.finalizada_em - v.iniciada_em)::numeric, 2) END
    ) || coalesce(p_extra, '{}'::jsonb);
END;
$$;

-- Encerra a partida e copia o resultado para partidas (ranking) e
-- ajudas_utilizadas (histórico), no mesmo formato do jogo em Python.
CREATE OR REPLACE FUNCTION privado.finalizar(v public.partidas_web, p_motivo text)
RETURNS public.partidas_web
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    UPDATE public.partidas_web
       SET status = p_motivo,
           finalizada_em = clock_timestamp(),
           atualizada_em = clock_timestamp(),
           revisao = revisao + 1
     WHERE id = v.id
    RETURNING * INTO v;

    INSERT INTO public.partidas
        (id, jogo_id, apelido, valor_ganho, tempo_segundos, acertos, motivo_encerramento, data_hora)
    VALUES
        (v.id, 1, v.apelido, v.valor_ganho,
         round(extract(epoch FROM v.finalizada_em - v.iniciada_em)::numeric, 2),
         v.acertos, p_motivo, v.finalizada_em)
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.ajudas_utilizadas (partida_id, pergunta_id, tipo, resultado, utilizada_em)
    SELECT v.id,
           (h ->> 'pergunta_id')::bigint,
           h ->> 'tipo',
           coalesce(h -> 'resultado', '{}'::jsonb),
           coalesce((h ->> 'utilizada_em')::timestamptz, clock_timestamp())
      FROM jsonb_array_elements(v.historico_ajudas) AS h
    ON CONFLICT DO NOTHING;

    RETURN v;
END;
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA privado FROM PUBLIC, anon, authenticated;

-- 4. FUNÇÕES PÚBLICAS (o site chama via /rest/v1/rpc/...) --------------------

-- Começa uma partida. Devolve partida_id + token (o token só aparece aqui).
CREATE OR REPLACE FUNCTION public.web_iniciar_partida(p_apelido text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_apelido text := regexp_replace(coalesce(p_apelido, ''), '^\s+|\s+$', '', 'g');
    v_token text;
    v_pergunta bigint;
    v public.partidas_web;
BEGIN
    IF length(v_apelido) < 1 OR length(v_apelido) > 40 THEN
        RAISE EXCEPTION 'Digite um apelido de 1 a 40 caracteres.'
            USING ERRCODE = 'P0001', HINT = 'APELIDO_INVALIDO';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM (VALUES ('facil'), ('media'), ('dificil')) AS n(dificuldade)
         WHERE (SELECT count(*) FROM public.perguntas q
                 WHERE q.ativa AND q.dificuldade = n.dificuldade) < 3
    ) THEN
        RAISE EXCEPTION 'O banco precisa de pelo menos 3 perguntas ativas de cada nível.'
            USING ERRCODE = 'P0001', HINT = 'PERGUNTAS_INSUFICIENTES';
    END IF;

    v_pergunta := privado.sortear_pergunta('facil', '{}'::bigint[]);
    v_token := replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '');

    INSERT INTO public.partidas_web (token_hash, apelido, pergunta_id, perguntas_usadas)
    VALUES (privado.hash_token(v_token), v_apelido, v_pergunta, ARRAY[v_pergunta])
    RETURNING * INTO v;

    RETURN privado.montar_estado(v, jsonb_build_object('token', v_token));
END;
$$;

-- Devolve o estado atual (usado para continuar após recarregar a página).
CREATE OR REPLACE FUNCTION public.web_estado(p_partida uuid, p_token text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    RETURN privado.montar_estado(privado.autenticar(p_partida, p_token));
END;
$$;

-- Responde a pergunta atual com A, B, C ou D.
CREATE OR REPLACE FUNCTION public.web_responder(p_partida uuid, p_token text, p_letra text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v public.partidas_web;
    v_letra text := upper(trim(coalesce(p_letra, '')));
    v_correta text;
    v_premio numeric;
    v_nova bigint;
BEGIN
    v := privado.autenticar(p_partida, p_token);
    PERFORM privado.exigir_em_andamento(v);

    IF v_letra NOT IN ('A', 'B', 'C', 'D') THEN
        RAISE EXCEPTION 'Escolha A, B, C ou D.' USING ERRCODE = 'P0001', HINT = 'LETRA_INVALIDA';
    END IF;
    IF v_letra = ANY (v.eliminadas) THEN
        RAISE EXCEPTION 'Essa alternativa foi eliminada pelas cartas.'
            USING ERRCODE = 'P0001', HINT = 'LETRA_ELIMINADA';
    END IF;

    SELECT correta::text INTO v_correta FROM public.perguntas WHERE id = v.pergunta_id;

    IF v_letra <> v_correta THEN
        v := privado.finalizar(v, 'erro');
        RETURN privado.montar_estado(v, jsonb_build_object(
            'ultima_resposta', jsonb_build_object('letra', v_letra, 'acertou', false)
        ));
    END IF;

    SELECT valor_premio INTO v_premio FROM public.etapas_premiacao WHERE etapa = v.etapa;

    IF v.etapa = 9 THEN
        UPDATE public.partidas_web
           SET acertos = acertos + 1, valor_ganho = v_premio,
               revisao = revisao + 1, atualizada_em = clock_timestamp()
         WHERE id = v.id
        RETURNING * INTO v;
        v := privado.finalizar(v, 'vitoria');
    ELSE
        v_nova := privado.sortear_pergunta(privado.dificuldade_da_etapa(v.etapa + 1), v.perguntas_usadas);
        IF v_nova IS NULL THEN
            RAISE EXCEPTION 'Faltam perguntas no banco para a próxima etapa.'
                USING ERRCODE = 'P0001', HINT = 'PERGUNTAS_INSUFICIENTES';
        END IF;
        UPDATE public.partidas_web
           SET acertos = acertos + 1,
               valor_ganho = v_premio,
               etapa = etapa + 1,
               pergunta_id = v_nova,
               perguntas_usadas = perguntas_usadas || v_nova,
               eliminadas = '{}'::text[],
               ajuda_estado = '{}'::jsonb,
               revisao = revisao + 1,
               atualizada_em = clock_timestamp()
         WHERE id = v.id
        RETURNING * INTO v;
    END IF;

    RETURN privado.montar_estado(v, jsonb_build_object(
        'ultima_resposta', jsonb_build_object('letra', v_letra, 'acertou', true, 'premio', v_premio)
    ));
END;
$$;

-- Usa uma ajuda: 'cartas', 'universitarios', 'plateia' ou 'pulo'.
-- Mesmas regras e probabilidades do ajudas.py.
CREATE OR REPLACE FUNCTION public.web_usar_ajuda(p_partida uuid, p_token text, p_tipo text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v public.partidas_web;
    v_tipo text := lower(trim(coalesce(p_tipo, '')));
    v_correta text;
    v_dificuldade text;
    v_erradas text[];
    v_resultado jsonb;
    v_qtd integer;
    v_eliminadas text[];
    v_palpites text[] := '{}';
    v_pc integer;
    v_rest integer;
    v_r1 integer;
    v_r2 integer;
    v_partes integer[];
    v_votos jsonb;
    v_nova bigint;
    v_registro jsonb;
    i integer;
BEGIN
    v := privado.autenticar(p_partida, p_token);
    PERFORM privado.exigir_em_andamento(v);

    SELECT correta::text, dificuldade INTO v_correta, v_dificuldade
      FROM public.perguntas WHERE id = v.pergunta_id;
    v_erradas := array_remove(ARRAY['A', 'B', 'C', 'D'], v_correta);

    IF v_tipo = 'cartas' THEN
        IF v.cartas_usada THEN
            RAISE EXCEPTION 'Você já usou as cartas nesta partida.' USING ERRCODE = 'P0001', HINT = 'AJUDA_USADA';
        END IF;
        v_qtd := floor(random() * 4)::integer;  -- 0 a 3, como random.randint(0, 3)
        SELECT coalesce(array_agg(l ORDER BY l), '{}') INTO v_eliminadas
          FROM (SELECT l FROM unnest(v_erradas) AS l ORDER BY random() LIMIT v_qtd) AS s;
        v_resultado := jsonb_build_object('carta', v_qtd, 'eliminadas', to_jsonb(v_eliminadas));
        UPDATE public.partidas_web
           SET cartas_usada = true, eliminadas = v_eliminadas
         WHERE id = v.id;

    ELSIF v_tipo = 'universitarios' THEN
        IF v.universitarios_usado THEN
            RAISE EXCEPTION 'Você já chamou os universitários nesta partida.' USING ERRCODE = 'P0001', HINT = 'AJUDA_USADA';
        END IF;
        FOR i IN 1..3 LOOP
            IF random() < 0.65 THEN
                v_palpites := v_palpites || v_correta;
            ELSE
                v_palpites := v_palpites || v_erradas[1 + floor(random() * 3)::integer];
            END IF;
        END LOOP;
        v_resultado := jsonb_build_object('palpites', to_jsonb(v_palpites));
        UPDATE public.partidas_web SET universitarios_usado = true WHERE id = v.id;

    ELSIF v_tipo = 'plateia' THEN
        IF v.plateia_usada THEN
            RAISE EXCEPTION 'Você já consultou a plateia nesta partida.' USING ERRCODE = 'P0001', HINT = 'AJUDA_USADA';
        END IF;
        v_pc := 42 + floor(random() * 35)::integer;  -- 42 a 76
        v_rest := 100 - v_pc;
        v_r1 := floor(random() * (v_rest + 1))::integer;
        v_r2 := floor(random() * (v_rest + 1))::integer;
        v_partes := ARRAY[least(v_r1, v_r2), greatest(v_r1, v_r2) - least(v_r1, v_r2), v_rest - greatest(v_r1, v_r2)];
        SELECT array_agg(x ORDER BY random()) INTO v_partes FROM unnest(v_partes) AS x;
        v_votos := jsonb_build_object(v_correta, v_pc);
        FOR i IN 1..3 LOOP
            v_votos := v_votos || jsonb_build_object(v_erradas[i], v_partes[i]);
        END LOOP;
        v_votos := jsonb_build_object('A', v_votos -> 'A', 'B', v_votos -> 'B', 'C', v_votos -> 'C', 'D', v_votos -> 'D');
        v_resultado := jsonb_build_object('votos', v_votos);
        UPDATE public.partidas_web SET plateia_usada = true WHERE id = v.id;

    ELSIF v_tipo = 'pulo' THEN
        IF v.pulos_restantes <= 0 THEN
            RAISE EXCEPTION 'Você não tem mais pulos.' USING ERRCODE = 'P0001', HINT = 'AJUDA_USADA';
        END IF;
        v_nova := privado.sortear_pergunta(v_dificuldade, v.perguntas_usadas);
        IF v_nova IS NULL THEN
            RAISE EXCEPTION 'Não há outra pergunta deste nível para trocar.' USING ERRCODE = 'P0001', HINT = 'SEM_RESERVA';
        END IF;
        v_resultado := jsonb_build_object('etapa', v.etapa);
    ELSE
        RAISE EXCEPTION 'Ajuda desconhecida.' USING ERRCODE = 'P0001', HINT = 'AJUDA_INVALIDA';
    END IF;

    v_registro := jsonb_build_object(
        'pergunta_id', v.pergunta_id,
        'tipo', v_tipo,
        'resultado', v_resultado,
        'utilizada_em', clock_timestamp()
    );

    IF v_tipo = 'pulo' THEN
        UPDATE public.partidas_web
           SET pulos_restantes = pulos_restantes - 1,
               pergunta_id = v_nova,
               perguntas_usadas = perguntas_usadas || v_nova,
               eliminadas = '{}'::text[],
               ajuda_estado = '{}'::jsonb,
               historico_ajudas = historico_ajudas || jsonb_build_array(v_registro),
               revisao = revisao + 1,
               atualizada_em = clock_timestamp()
         WHERE id = v.id
        RETURNING * INTO v;
    ELSE
        UPDATE public.partidas_web
           SET ajuda_estado = ajuda_estado || jsonb_build_object(v_tipo, v_resultado),
               historico_ajudas = historico_ajudas || jsonb_build_array(v_registro),
               revisao = revisao + 1,
               atualizada_em = clock_timestamp()
         WHERE id = v.id
        RETURNING * INTO v;
    END IF;

    RETURN privado.montar_estado(v, jsonb_build_object(
        'ajuda', jsonb_build_object('tipo', v_tipo, 'resultado', v_resultado)
    ));
END;
$$;

-- Para o jogo e leva o prêmio do último acerto.
CREATE OR REPLACE FUNCTION public.web_parar(p_partida uuid, p_token text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v public.partidas_web;
BEGIN
    v := privado.autenticar(p_partida, p_token);
    PERFORM privado.exigir_em_andamento(v);
    v := privado.finalizar(v, 'desistencia');
    RETURN privado.montar_estado(v);
END;
$$;

-- Só estas cinco funções ficam disponíveis para o site.
REVOKE ALL ON FUNCTION public.web_iniciar_partida(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.web_estado(uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.web_responder(uuid, text, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.web_usar_ajuda(uuid, text, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.web_parar(uuid, text) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.web_iniciar_partida(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.web_estado(uuid, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.web_responder(uuid, text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.web_usar_ajuda(uuid, text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.web_parar(uuid, text) TO anon, authenticated;
