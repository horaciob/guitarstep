-- classes: a teacher invites students with a link; a student in a class shares their weekly report with
-- that teacher and gets the setlists the teacher sends (assignments). Admins can block an account.

ALTER TABLE users ADD COLUMN blocked_at timestamptz;

CREATE TABLE class_invites (
    code_hash  text PRIMARY KEY,
    teacher_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX class_invites_teacher ON class_invites (teacher_id);

CREATE TABLE class_members (
    teacher_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    student_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    joined_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (teacher_id, student_id),
    CHECK (teacher_id <> student_id)
);
CREATE INDEX class_members_student ON class_members (student_id);

CREATE TABLE assignments (
    id          bigserial PRIMARY KEY,
    teacher_id  uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    student_id  uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    payload     jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    answered_at timestamptz,
    accepted    boolean
);
CREATE INDEX assignments_student ON assignments (student_id, answered_at);
