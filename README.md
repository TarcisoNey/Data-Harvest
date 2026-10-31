# Data Harvest

Projeto de análise de dados desenvolvido pelo Instituto Caldeira em parceria
com a John Deere. O repositório reúne pipelines para os conjuntos Downtime e
AI4I 2020, seus dados e resultados, além de consultas SQL para o conjunto
Downtime.

## Estrutura

```text
data/
  raw/                 # Dados de origem, preservados sem transformação
  processed/           # CSVs tratados, resumos e gráficos dos pipelines
src/
  pipelines/           # Um pipeline independente para cada conjunto de dados
sql/                   # Dump do banco Downtime e consultas de análise
```

## Configuração

Requer Python 3.10 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Executar o banco de dados

Configure o arquivo `.env` na raiz do projeto. Se ainda não existir, crie-o a
partir do exemplo:

```powershell
Copy-Item .env.example .env
```

Edite `.env` e defina os dados de acesso do PostgreSQL. No Windows, se a porta
`5432` já estiver ocupada por outra instalação do PostgreSQL, use `DB_PORT=5433`.
O mesmo valor será usado pelo Docker e pelo script Python.

Inicie o container e confirme que o banco está pronto:

```powershell
docker compose up -d
docker compose ps
docker compose exec -T db pg_isready
```

Crie as tabelas definidas nos modelos:

```powershell
python src\database.py
```

Para parar o container sem apagar os dados persistidos:

```powershell
docker compose down
```

Evite `docker compose down -v` se quiser preservar os dados do banco: a opção
`-v` também remove o volume.

## Executar os pipelines

Execute os comandos a partir da raiz do repositório. Os caminhos padrão para os
dados de entrada e saída já estão configurados; argumentos posicionais podem
ser usados para substituí-los.

```powershell
python src\pipelines\downtime.py
python src\pipelines\ai4i2020.py
```

Para especificar outros caminhos:

```powershell
python src\pipelines\downtime.py caminho\para\entrada.csv caminho\para\saida
python src\pipelines\ai4i2020.py caminho\para\entrada.csv caminho\para\saida
```

Cada pipeline gera um CSV tratado, um resumo agregado e um gráfico em
`data/processed/<conjunto>/`.

## SQL

- `sql/downtime_dump.sql` contém a estrutura e os dados de exemplo do banco
  Downtime.
- `sql/downtime_queries.sql` reúne as consultas analíticas para esse conjunto.
