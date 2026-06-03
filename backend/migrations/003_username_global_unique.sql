-- 账号全局唯一：登录/注册仅用户名+密码

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tenant_username_unique;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique ON users (username);
