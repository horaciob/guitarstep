-- user data: each user's documents (settings, progress, practice plan, tone rig, setlists), their
-- practice sessions (history) and their own charts; kept as files by the local app

CREATE TABLE user_documents (
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       text NOT NULL,
    data       jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, name)
);

CREATE TABLE practice_sessions (
    id        bigserial PRIMARY KEY,
    user_id   uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    song_id   text NOT NULL,
    kind      text NOT NULL,
    played_at timestamptz NOT NULL,
    data      jsonb NOT NULL
);
CREATE INDEX practice_sessions_user_song ON practice_sessions (user_id, song_id, played_at);

CREATE TABLE user_charts (
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    id         text NOT NULL,
    text       text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id)
);
