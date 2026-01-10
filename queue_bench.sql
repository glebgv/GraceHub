-- queue_bench.sql (исправленный для pgbench)

-- Установка случайной переменной для update_id (мета-команда pgbench)
\set update_id random(1, 1000000000)

-- Запасной ID, если RETURNING не вернет значение
\set initial_job_id random(1, 1000000000)

BEGIN;

-- Enqueue: Вставка новой задачи с переменной :update_id
INSERT INTO tg_update_queue (instance_id, update_id, payload, status, run_at, attempts, created_at, updated_at)
VALUES ('test_instance', :update_id, '{"test": "data"}'::jsonb, 'pending', NOW(), 0, NOW(), NOW())
ON CONFLICT DO NOTHING;

-- Pick: Выбор и обновление с RETURNING id (для захвата в переменную)
WITH cte AS (
    SELECT id
    FROM tg_update_queue
    WHERE status IN ('pending', 'retry')
    AND run_at <= NOW()
    ORDER BY run_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE tg_update_queue q
SET status = 'processing',
    attempts = q.attempts + 1,
    locked_at = NOW(),
    locked_by = 'test_worker',
    updated_at = NOW()
FROM cte
WHERE q.id = cte.id
RETURNING q.id;

-- Захват возвращенного id в переменную 'returned_id' (мета-команда pgbench)
\gset returned_

-- Ack: Обновление с использованием захваченной переменной :returned_id (или запасной, если NULL)
UPDATE tg_update_queue
SET status = 'done',
    locked_at = NULL,
    locked_by = NULL,
    updated_at = NOW()
WHERE id = COALESCE(:returned_id, :initial_job_id);

END;
