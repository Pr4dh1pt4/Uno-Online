-- Skema database UNO Online untuk MariaDB / MySQL.
-- Jalankan: mysql -u root -p < schema.sql  (atau via init di database.py)

CREATE DATABASE IF NOT EXISTS uno_online
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE uno_online;

-- USERS ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(32) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- LEADERBOARD (1:1 dengan users) -------------------------------------------
CREATE TABLE IF NOT EXISTS leaderboard (
    user_id     INT PRIMARY KEY,
    total_match INT DEFAULT 0,
    total_win   INT DEFAULT 0,
    total_lose  INT DEFAULT 0,
    total_point INT DEFAULT 0,
    rank_tier   VARCHAR(16) DEFAULT 'Bronze',
    win_rate    FLOAT DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_lb_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ROOMS ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rooms (
    room_id    VARCHAR(36) PRIMARY KEY,
    room_code  VARCHAR(8) NOT NULL UNIQUE,
    host_id    INT,
    status     VARCHAR(16) DEFAULT 'WAITING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_room_host FOREIGN KEY (host_id) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- MATCHES -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    match_id     INT AUTO_INCREMENT PRIMARY KEY,
    room_id      VARCHAR(36),
    winner_id    INT,
    player_count INT,
    match_mode   VARCHAR(16) DEFAULT 'ranked',
    started_at   TIMESTAMP NULL,
    ended_at     TIMESTAMP NULL
) ENGINE=InnoDB;

-- MATCH_PLAYERS -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_players (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    match_id        INT NOT NULL,
    user_id         INT NOT NULL,
    finish_position INT,
    point_change    INT,
    result          VARCHAR(8),
    CONSTRAINT fk_mp_match FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
    CONSTRAINT fk_mp_user  FOREIGN KEY (user_id)  REFERENCES users(user_id)   ON DELETE CASCADE
) ENGINE=InnoDB;

-- ACTIVITY_LOG --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_log (
    log_id     INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT,
    event_type VARCHAR(32) NOT NULL,
    detail     TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- SESSIONS ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    token      VARCHAR(64) PRIMARY KEY,
    user_id    INT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_sess_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- INDEX ---------------------------------------------------------------------
CREATE INDEX idx_leaderboard_point ON leaderboard(total_point DESC);
CREATE INDEX idx_match_players_user ON match_players(user_id);
CREATE INDEX idx_activity_user ON activity_log(user_id, created_at);
