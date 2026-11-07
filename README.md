## Execução do Pipeline ETL com Docker

O pipeline ETL da Sprint 2 pode ser executado utilizando Docker, permitindo realizar a carga dos dados em um ambiente isolado, com as dependências Python instaladas automaticamente.

### Pré-requisitos

- Docker Desktop instalado e em execução.
- Arquivos CSV necessários disponíveis na pasta `data`.

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

### Validação da execução

Ao executar o pipeline, os arquivos CSV são lidos, os dados são carregados no banco SQLite e a integridade do banco é verificada.

A execução deve apresentar mensagens semelhantes a:

```text
Lido clean_ai4i.csv: 10000 linhas
Lido ai4i2020.csv: 10000 linhas
UDI e Product ID recuperados com sucesso.
Lido clean_downtime.csv: 2500 linhas

Carga ETL concluída com sucesso!
assembly_lines: 3
failure_modes: 5
machine_downtime_logs: 2500
machines: 3
process_readings: 10000
product_types: 3
reading_failure_modes: 373
Novas leituras: 0
Novos modos de falha: 0
Novos logs de Downtime: 0
Integridade do SQLite: OK
Banco: /app/data/sprint2_etl.db
```

A mensagem `Integridade do SQLite: OK` indica que a verificação de integridade do banco foi concluída com sucesso.

### Verificação da imagem

Para confirmar que a imagem Docker foi criada, execute:

```powershell
docker images
```

A imagem `data-harvest-etl:latest` deverá aparecer na lista de imagens disponíveis.