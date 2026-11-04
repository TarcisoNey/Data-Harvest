-- =====================================================================
-- Data Harvest - Schema relacional (SQLite)
--
-- AI4I 2020 (conjunto principal):
--   product_types (1) ──< process_readings (1) ──< reading_failure_modes >── (1) failure_modes
--
-- Downtime (espelha os modelos de src/database.py):
--   assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)
--
-- Uso:  sqlite3 data_harvest.db < sql/schema_sqlite.sql
-- =====================================================================

-- No SQLite as FKs vêm DESLIGADAS por padrão e o PRAGMA vale por conexão:
-- execute-o também em toda conexão da aplicação.
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

DROP TABLE IF EXISTS reading_failure_modes;
DROP TABLE IF EXISTS process_readings;
DROP TABLE IF EXISTS failure_modes;
DROP TABLE IF EXISTS product_types;
DROP TABLE IF EXISTS machine_downtime_logs;
DROP TABLE IF EXISTS machines;
DROP TABLE IF EXISTS assembly_lines;

-- =====================================================================
-- AI4I 2020 - Predictive Maintenance Dataset
-- =====================================================================

-- ---------------------------------------------------------------------
-- Tipos de produto (variante de qualidade)
-- ---------------------------------------------------------------------
CREATE TABLE product_types (
    code         TEXT PRIMARY KEY NOT NULL CHECK (code IN ('L', 'M', 'H')),
    quality      TEXT NOT NULL,
    description  TEXT
);

INSERT INTO product_types (code, quality, description) VALUES
    ('L', 'Low',    'Qualidade baixa - cerca de 50% dos produtos'),
    ('M', 'Medium', 'Qualidade média - cerca de 30% dos produtos'),
    ('H', 'High',   'Qualidade alta - cerca de 20% dos produtos');

-- ---------------------------------------------------------------------
-- Modos de falha (catálogo)
-- ---------------------------------------------------------------------
CREATE TABLE failure_modes (
    code         TEXT PRIMARY KEY NOT NULL,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL
);

INSERT INTO failure_modes (code, name, description) VALUES
    ('TWF', 'Tool Wear Failure',
        'Falha por desgaste da ferramenta: ela é trocada ou falha em um tempo de desgaste aleatório entre 200 e 240 min.'),
    ('HDF', 'Heat Dissipation Failure',
        'Falha por dissipação de calor: diferença entre temperatura do ar e do processo abaixo de 8,6 K com rotação abaixo de 1380 rpm.'),
    ('PWF', 'Power Failure',
        'Falha de potência: potência (torque x velocidade de rotação em rad/s) abaixo de 3500 W ou acima de 9000 W.'),
    ('OSF', 'Overstrain Failure',
        'Falha por sobrecarga: desgaste da ferramenta x torque acima de 11.000 (L), 12.000 (M) ou 13.000 (H) min.Nm.'),
    ('RNF', 'Random Failure',
        'Falha aleatória: 0,1% de chance em cada processo, independente dos parâmetros.');

-- ---------------------------------------------------------------------
-- Leituras do processo (uma por produto)
-- ---------------------------------------------------------------------
CREATE TABLE process_readings (
    udi                  INTEGER PRIMARY KEY,          -- identificador único do registro
    product_id           TEXT    NOT NULL UNIQUE,      -- ex.: 'M14860'
    product_type_code    TEXT    NOT NULL,
    air_temperature      REAL    NOT NULL,             -- K
    process_temperature  REAL    NOT NULL,             -- K
    rotational_speed     INTEGER NOT NULL,             -- rpm
    torque               REAL    NOT NULL,             -- Nm
    tool_wear            INTEGER NOT NULL,             -- min
    machine_failure      INTEGER NOT NULL CHECK (machine_failure IN (0, 1)),
    CONSTRAINT fk_readings_product_type
        FOREIGN KEY (product_type_code)
        REFERENCES product_types (code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX ix_readings_product_type ON process_readings (product_type_code);
CREATE INDEX ix_readings_failure      ON process_readings (machine_failure);

-- ---------------------------------------------------------------------
-- Modos de falha ocorridos em cada leitura (N:N)
-- Obs.: no dataset original há leituras com machine_failure = 1 sem modo
-- e leituras com modo (quase sempre RNF) e machine_failure = 0;
-- os dados são mantidos como vieram.
-- ---------------------------------------------------------------------
CREATE TABLE reading_failure_modes (
    reading_udi        INTEGER NOT NULL,
    failure_mode_code  TEXT    NOT NULL,
    PRIMARY KEY (reading_udi, failure_mode_code),
    CONSTRAINT fk_rfm_reading
        FOREIGN KEY (reading_udi)
        REFERENCES process_readings (udi)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_rfm_failure_mode
        FOREIGN KEY (failure_mode_code)
        REFERENCES failure_modes (code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX ix_rfm_failure_mode ON reading_failure_modes (failure_mode_code);

-- =====================================================================
-- Downtime
-- =====================================================================

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
