-- jobs: the slow work of the web service (transcribing a recording, separating the guitar, analyzing
-- a take) runs in a worker instead of the request; see guitarr/jobs.py

CREATE TABLE jobs (
    id          bigserial PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind        text NOT NULL,
    args        jsonb NOT NULL,
    status      text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    result      jsonb,
    error       jsonb,
    attempts    integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz
);
CREATE INDEX jobs_queued ON jobs (id) WHERE status = 'queued';
CREATE INDEX jobs_user_active ON jobs (user_id) WHERE status IN ('queued', 'running');
