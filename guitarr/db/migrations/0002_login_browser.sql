-- login browser: a sign-in link remembers the browser that asked for it (a hash of a cookie),
-- so opening it elsewhere is shown as such before signing in

ALTER TABLE login_tokens ADD COLUMN browser_hash text;
