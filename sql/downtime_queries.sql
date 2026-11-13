/* Consultas analíticas do conjunto Downtime (PostgreSQL).
   Usam o schema oficial (sql/schema_postgres.sql):
     assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)
   Uso: psql -h localhost -U <usuario> -d data_harvest_db -f sql/downtime_queries.sql */


/* PERGUNTA: Quais são as 10 falhas mais recentes registradas nas operações?
   (O conjunto não tem duração da parada: downtime_status só indica se houve falha.) */

SELECT l.date::date AS data, l.machine_id, a.name AS linha, l.downtime_status
FROM machine_downtime_logs l
JOIN machines m ON m.id = l.machine_id
JOIN assembly_lines a ON a.id = m.assembly_line_id
WHERE l.downtime_status = 'Machine_Failure'
ORDER BY l.date DESC, l.id DESC
LIMIT 10;

/* INTERPRETAÇÃO: As 10 falhas mais recentes, com a máquina e a linha de montagem de cada uma. */


/* PERGUNTA: Quantas falhas ocorreram em cada linha de montagem? */

SELECT a.name AS linha, COUNT(*) AS total_falhas
FROM machine_downtime_logs l
JOIN machines m ON m.id = l.machine_id
JOIN assembly_lines a ON a.id = m.assembly_line_id
WHERE l.downtime_status = 'Machine_Failure'
GROUP BY a.name
ORDER BY a.name;

/* INTERPRETAÇÃO: Resume quantas falhas houve em cada setor sem precisar percorrer 2500 linhas de registros. */


/* PERGUNTA: Quais são as quantidades de falhas de equipamentos em suas respectivas linhas de montagem? */

SELECT m.id AS machine_id, a.name AS linha, COUNT(*) AS total_falhas,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_das_falhas
FROM machine_downtime_logs l
JOIN machines m ON m.id = l.machine_id
JOIN assembly_lines a ON a.id = m.assembly_line_id
WHERE l.downtime_status = 'Machine_Failure'
GROUP BY m.id, a.name
ORDER BY total_falhas DESC;

/* INTERPRETAÇÃO: O JOIN entre as três tabelas consolida a quantidade de falhas por equipamento
   e sua respectiva linha de montagem, com a participação de cada um no total de falhas. */


/* PERGUNTA: Quais máquinas possuem a quantidade de falhas acima da média geral de falhas das máquinas? */

WITH falhas AS (
    SELECT machine_id, COUNT(*) AS total_falhas
    FROM machine_downtime_logs
    WHERE downtime_status = 'Machine_Failure'
    GROUP BY machine_id
)
SELECT machine_id, total_falhas
FROM falhas
WHERE total_falhas > (SELECT AVG(total_falhas) FROM falhas)
ORDER BY total_falhas DESC;

/* INTERPRETAÇÃO: Isolamento das máquinas cujos índices de falhas superam a média de ocorrências da fábrica, apontando os maiores focos de atenção. */


/* PERGUNTA: Quantas falhas ocorreram em toda a fábrica, e qual a taxa de falha? */

SELECT COUNT(*) FILTER (WHERE downtime_status = 'Machine_Failure') AS total_falhas,
       COUNT(*) AS total_leituras,
       ROUND(100.0 * COUNT(*) FILTER (WHERE downtime_status = 'Machine_Failure') / COUNT(*), 1) AS taxa_falha_pct
FROM machine_downtime_logs;

/* INTERPRETAÇÃO: Com essa consulta mapeamos todas as falhas da fábrica em uma única linha, junto da taxa sobre o total de leituras. */


/* PERGUNTA: Como as falhas evoluíram mês a mês? */

SELECT to_char(date, 'YYYY-MM') AS mes,
       COUNT(*) FILTER (WHERE downtime_status = 'Machine_Failure') AS falhas,
       COUNT(*) AS leituras
FROM machine_downtime_logs
GROUP BY mes
ORDER BY mes;

/* INTERPRETAÇÃO: Mostra a concentração de falhas entre fevereiro e abril de 2022. Meses com poucas leituras têm taxas pouco confiáveis. */
