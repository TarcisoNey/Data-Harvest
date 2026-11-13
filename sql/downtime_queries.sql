/* Uso: sqlite3 analise.db < sql/downtime_dump.sql  e depois este arquivo.
   Estas consultas usam o modelo da Sprint 1 (tabela "bruto" + dim_maquina),
   não o schema oficial de sql/schema_sqlite.sql. */

CREATE TABLE IF NOT EXISTS dim_maquina AS
SELECT DISTINCT machine_id, assembly_line_no
FROM bruto;


/* PERGUNTA: Quais são as 10 falhas mais recentes registradas nas operações?
   (O conjunto não tem duração da parada: "downtime" só indica se houve falha.
   Por isso a consulta ordena pela data, e não por um "tempo de parada".) */

SELECT date, machine_id, assembly_line_no, downtime
FROM bruto
WHERE downtime != 'No_Machine_Failure'
ORDER BY date DESC
LIMIT 10;

/* INTERPRETAÇÃO: As 10 falhas mais recentes, com a máquina e a linha de montagem de cada uma. */


/* PERGUNTA: Quantas falhas ocorreram em cada linha de montagem? */

SELECT assembly_line_no, COUNT(*) AS total_falhas 
FROM bruto 
WHERE downtime != 'No_Machine_Failure'
GROUP BY assembly_line_no;

/* INTERPRETAÇÃO: Resume quantas falhas houve em cada setor sem precisar percorrer 2500 linhas de registros. */


/* PERGUNTA: Quais são as quantidades de falhas de equipamentos em suas respectivas linhas de montagem? */

SELECT d.machine_id, d.assembly_line_no, COUNT(*) AS total_falhas
FROM bruto b
JOIN dim_maquina d ON b.machine_id = d.machine_id
WHERE b.downtime != 'No_Machine_Failure'
GROUP BY d.machine_id, d.assembly_line_no;

/* INTERPRETAÇÃO: Utilizando o comando JOIN ON permitiu consolidar a quantidade de 
falhas por equipamento e sua respetiva linha de montagem de forma integrada. */



/*PERGUNTA: Quais máquinas possuem a quantidade de falhas acima da média geral de falhas das máquinas? */

SELECT machine_id, COUNT(*) AS total_falhas
FROM bruto
WHERE downtime != 'No_Machine_Failure'
GROUP BY machine_id
HAVING COUNT(*) > (
    SELECT AVG(contagem) 
    FROM (
        SELECT COUNT(*) AS contagem 
        FROM bruto 
        WHERE downtime != 'No_Machine_Failure' 
        GROUP BY machine_id
    )
);

/* INTERPRETAÇÃO: Isolamento das máquinas cujos índices de falhas superam a média de ocorrências da fábrica, apontando os maiores focos de atenção. */


/* PERGUNTA: Quantas falhas ocorreram em toda a fabrica? */

SELECT downtime, COUNT(*) AS total_ocorrencias
FROM bruto
WHERE downtime != 'No_Machine_Failure'
GROUP BY downtime
ORDER BY total_ocorrencias DESC;

/* INTERPRETAÇÃO: Com essa consulta mapeamos todas as falhas da fabrica em uma unica linha. */



