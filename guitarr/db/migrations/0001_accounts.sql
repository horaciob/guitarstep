-- accounts: users, one-time sign-in links and browser sessions

CREATE TABLE users (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email      text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login timestamptz
);
CREATE UNIQUE INDEX users_email ON users (lower(email));

-- a sign-in link sent by email; only the SHA-256 of the token is kept
CREATE TABLE login_tokens (
    token_hash text PRIMARY KEY,
    email      text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at    timestamptz
);
CREATE INDEX login_tokens_email ON login_tokens (lower(email), created_at);

-- a signed-in browser (the cookie holds the token; only its SHA-256 is kept)
CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_seen  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user ON sessions (user_id);
