## Execução do Pipeline ETL com Docker

O pipeline ETL (`src/etl_sqlite.py`) carrega o conjunto **Downtime** no banco
SQLite, seguindo o schema de `sql/schema_sqlite.sql`:
`assembly_lines` → `machines` → `machine_downtime_logs`.

Ele pode ser executado utilizando Docker, permitindo realizar a carga dos dados em um ambiente isolado, com as dependências Python instaladas automaticamente.

### Pré-requisitos

- Docker Desktop instalado e em execução.
- CSV limpo do Downtime em `data/processed/downtime/clean_downtime.csv`.
  Se ele não existir, gere com `python src/downtime.py`.

### Construção da imagem

Na pasta principal do projeto, execute o comando:

```powershell
docker build -t data-harvest-etl .
```

Esse comando constrói a imagem Docker utilizando as configurações do `Dockerfile` e as dependências do `requirements.txt`.

### Execução do pipeline

No terminal PowerShell, na raiz do repositório, execute:

```powershell
docker run --rm --mount "type=bind,source=${PWD}\data,target=/app/data" data-harvest-etl
```

O comando monta a pasta `data` do computador no diretório `/app/data` do contêiner, permitindo que o pipeline acesse os arquivos CSV sem incorporá-los à imagem Docker.

O banco SQLite gerado ou atualizado fica disponível em `data/sprint2_etl.db`.

> Se você tem um `data/sprint2_etl.db` antigo, criado quando o ETL também
> carregava o AI4I, apague-o antes. O ETL não sobrescreve um banco com
> tabelas diferentes das do schema atual.

### Validação da execução

Ao executar o pipeline, os arquivos CSV são lidos, os dados são carregados no banco SQLite e a integridade do banco é verificada.

A execução deve apresentar mensagens semelhantes a:

```text
Lido clean_downtime.csv: 2500 linhas
Schema oficial criado em banco vazio: /app/data/sprint2_etl.db

Carga ETL concluída com sucesso!
assembly_lines: 3
machine_downtime_logs: 2500
machines: 3
Novos logs de Downtime: 2500
Integridade do SQLite: OK
Banco: /app/data/sprint2_etl.db
```

Rodando de novo com o mesmo CSV, a carga não duplica registros e mostra
`Novos logs de Downtime: 0`.

A mensagem `Integridade do SQLite: OK` indica que a verificação de integridade do banco foi concluída com sucesso.

### Verificação da imagem

Para confirmar que a imagem Docker foi criada, execute:

```powershell
docker images
```

A imagem `data-harvest-etl:latest` deverá aparecer na lista de imagens disponíveis.

## Execução sem Docker

Na raiz do repositório:

```powershell
python src\downtime.py           # limpa o CSV bruto -> data/processed/downtime/
python src\etl_sqlite.py         # carrega no SQLite -> data/sprint2_etl.db
python teste.py                  # conta os registros e verifica a integridade
python sql\validate_schema.py    # valida PKs, FKs e restrições do schema
```

## PostgreSQL e relatórios para o RAG

Com o container do PostgreSQL rodando (`docker compose up -d`) e o `.env`
configurado:

```powershell
python src\load_postgres.py      # carrega o CSV limpo nas tabelas de src\database.py
python src\relatorios.py         # gera os relatórios a partir do PostgreSQL
```

O `load_postgres.py` não duplica dados: se as tabelas já estiverem carregadas,
ele não faz nada. Use `--recriar` para apagar e carregar de novo.

O `relatorios.py` gera, em `data/processed/relatorios/`:

- `relatorio_downtime.md`: visão geral, falhas por mês, perfil dos sensores,
  zonas de risco, diagnósticos (superaquecimento, torque alto e baixo, pressão
  hidráulica baixa) e recomendações por máquina;
- `documentos_rag.jsonl`: os mesmos conteúdos como documentos curtos, um por
  linha, com `id`, `text` e `metadata`, prontos para indexar no ChromaDB.

Para gerar a partir do SQLite do ETL em vez do PostgreSQL:

```powershell
python src\relatorios.py --url sqlite:///data/sprint2_etl.db
```

As zonas de risco e as recomendações são heurísticas: usam a frequência
histórica de falhas em cada faixa de valores dos sensores. Não são um modelo
preditivo treinado.
