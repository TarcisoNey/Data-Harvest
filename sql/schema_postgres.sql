-- Gerado por: python src/database.py --ddl > sql/schema_postgres.sql
-- Não edite à mão: o schema é definido em src/database.py.

CREATE TABLE assembly_lines (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE machines (
	id VARCHAR NOT NULL, 
	assembly_line_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(assembly_line_id) REFERENCES assembly_lines (id) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX ix_machines_assembly_line_id ON machines (assembly_line_id);

CREATE TABLE machine_downtime_logs (
	id SERIAL NOT NULL, 
	machine_id VARCHAR NOT NULL, 
	date TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	hydraulic_pressure FLOAT, 
	coolant_pressure FLOAT, 
	air_system_pressure FLOAT, 
	coolant_temperature FLOAT, 
	hydraulic_oil_temperature FLOAT, 
	spindle_bearing_temperature FLOAT, 
	spindle_vibration FLOAT, 
	tool_vibration FLOAT, 
	spindle_speed FLOAT, 
	voltage FLOAT, 
	torque FLOAT, 
	cutting FLOAT, 
	downtime_status VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_logs_downtime_status CHECK (downtime_status IN ('Machine_Failure', 'No_Machine_Failure')), 
	FOREIGN KEY(machine_id) REFERENCES machines (id) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX ix_machine_downtime_logs_date ON machine_downtime_logs (date);
CREATE INDEX ix_machine_downtime_logs_machine_id ON machine_downtime_logs (machine_id);

