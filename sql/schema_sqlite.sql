-- =====================================================================
-- Data Harvest - Schema relacional do conjunto Downtime (SQLite)
-- Espelha os modelos de src/database.py:
--   assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)
--
-- Uso:  sqlite3 data/sprint2_etl.db < sql/schema_sqlite.sql
-- =====================================================================

-- No SQLite as FKs vêm DESLIGADAS por padrão e o PRAGMA vale por conexão:
-- execute-o também em toda conexão da aplicação.
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS machine_downtime_logs;
DROP TABLE IF EXISTS machines;
DROP TABLE IF EXISTS assembly_lines;

-- ---------------------------------------------------------------------
-- Linhas de montagem (ex.: 'Shopfloor-L1')
-- ---------------------------------------------------------------------
CREATE TABLE assembly_lines (
    id    INTEGER PRIMARY KEY,               -- alias do ROWID
    name  TEXT    NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- Máquinas (ex.: 'Makino-L1-Unit1-2013'); cada uma pertence a uma linha
-- ---------------------------------------------------------------------
CREATE TABLE machines (
    id                TEXT    PRIMARY KEY NOT NULL,
    assembly_line_id  INTEGER NOT NULL,
    CONSTRAINT fk_machines_assembly_line
        FOREIGN KEY (assembly_line_id)
        REFERENCES assembly_lines (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX ix_machines_assembly_line_id ON machines (assembly_line_id);

-- ---------------------------------------------------------------------
-- Leituras de sensores e status de parada por máquina
-- ---------------------------------------------------------------------
CREATE TABLE machine_downtime_logs (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id                   TEXT    NOT NULL,
    date                         TEXT    NOT NULL,   -- ISO 8601 'YYYY-MM-DD'
    hydraulic_pressure           REAL,               -- bar
    coolant_pressure             REAL,               -- bar
    air_system_pressure          REAL,               -- bar
    coolant_temperature          REAL,               -- °C
    hydraulic_oil_temperature    REAL,               -- °C
    spindle_bearing_temperature  REAL,               -- °C
    spindle_vibration            REAL,               -- µm
    tool_vibration               REAL,               -- µm
    spindle_speed                REAL,               -- RPM
    voltage                      REAL,               -- V
    torque                       REAL,               -- Nm
    cutting                      REAL,               -- kN
    downtime_status              TEXT    NOT NULL
        CHECK (downtime_status IN ('Machine_Failure', 'No_Machine_Failure')),
    CONSTRAINT fk_logs_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX ix_logs_machine_id ON machine_downtime_logs (machine_id);
CREATE INDEX ix_logs_date       ON machine_downtime_logs (date);

COMMIT;
