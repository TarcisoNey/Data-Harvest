# Data Harvest

Análise de paradas de máquinas CNC (conjunto **Machine Downtime**: 2.500
leituras de sensores de 3 máquinas Makino em 3 linhas de montagem) com
pipeline de dados, banco PostgreSQL, relatórios de manutenção, dashboard e um
agente de IA que responde perguntas cruzando os dados com os manuais.

## Como as peças se encaixam

```text
data/raw/downtime/machine_downtime.csv
  └─ src/downtime.py ─────► data/processed/downtime/clean_downtime.csv
       └─ src/etl.py ─────► PostgreSQL (docker compose; schema em src/database.py)
            ├─ src/relatorios.py ──► data/processed/relatorios/ (relatório + documentos_rag.jsonl)
            │    └─ src/rag_ingest.py ──► chroma_db/ (banco vetorial, coleção manuais_rag)
            ├─ dashboard/app.py ───► Dashboard Industrial (Streamlit) + Assistente IA
            └─ src/agente/ (Gemini) ► consulta o PostgreSQL + chroma_db/
```

O PostgreSQL é o único banco do projeto. O schema é definido em
`src/database.py` e documentado em `sql/schema_postgres.sql` (gerado a partir
dele com `python src/database.py --ddl > sql/schema_postgres.sql`).

## Começo rápido

Pré-requisitos: Python 3.10+ e Docker Desktop. Na raiz do repositório:

```powershell
pip install -r requirements.txt
copy .env.example .env                  # preencha POSTGRES_PASSWORD e GEMINI_API_KEY
docker compose up -d db                 # 1. sobe o PostgreSQL
python src\downtime.py                  # 2. limpa o CSV bruto
python src\etl.py                       # 3. carrega no PostgreSQL
python src\relatorios.py                # 4. relatórios para o RAG
python src\rag_ingest.py                # 5. indexa no ChromaDB
python -m streamlit run dashboard\app.py   # 6. dashboard com o assistente
```

Os passos 2 a 5 só precisam rodar de novo quando os dados mudarem. O banco
fica num volume do Docker e sobrevive a reinícios (`docker compose down -v`
apaga os dados).

## Pipeline de dados

### Limpeza (`src/downtime.py`)

Padroniza os nomes das colunas, converte datas, remove duplicatas, trata
valores não positivos como ausentes e imputa a mediana de cada máquina. Gera
em `data/processed/downtime/` o CSV limpo, um resumo por máquina e um gráfico.

### Carga no PostgreSQL (`src/etl.py`)

Valida o CSV limpo e carrega nas tabelas
`assembly_lines` → `machines` → `machine_downtime_logs`:

```powershell
python src\etl.py              # cria as tabelas se preciso e carrega
python src\etl.py --recriar    # apaga as tabelas e carrega do zero
```

A carga é idempotente: rodando de novo com o mesmo CSV, mostra
`Novos logs de Downtime: 0`. Se o CSV for diferente do que já está no banco,
a carga é cancelada sem sobrescrever nada (use `--recriar`). A saída esperada:

```text
Lido clean_downtime.csv: 2500 linhas

Carga ETL concluída com sucesso!
assembly_lines: 3
machine_downtime_logs: 2500
machines: 3
Novos logs de Downtime: 2500
Integridade do PostgreSQL: OK
Banco: postgresql://postgres_user@localhost:5432/data_harvest_db
```

O banco garante as regras do schema: chaves estrangeiras com `RESTRICT` no
delete e `CASCADE` no update, `NOT NULL` nas colunas obrigatórias e `CHECK`
nos valores de `downtime_status`.

### ETL pelo Docker

O serviço `etl` do `docker-compose.yml` roda a carga num contêiner, sem
instalar Python. Ele espera o banco ficar pronto e lê os CSVs da pasta `data`:

```powershell
docker compose run --rm etl
```

A imagem instala só as dependências do ETL (`requirements-etl.txt`).

### Consultas analíticas (`sql/downtime_queries.sql`)

Falhas recentes, falhas por linha e por máquina, máquinas acima da média,
taxa geral e evolução mensal:

```powershell
Get-Content sql\downtime_queries.sql | docker compose exec -T db psql -U postgres_user -d data_harvest_db
```

### Relatórios para o RAG (`src/relatorios.py`)

Lê o PostgreSQL e gera, em `data/processed/relatorios/`:

- `relatorio_downtime.md`: visão geral, falhas por mês, perfil dos sensores,
  zonas de risco, diagnósticos (superaquecimento, torque alto e baixo, pressão
  hidráulica baixa) e recomendações por máquina;
- `documentos_rag.jsonl`: os mesmos conteúdos como documentos curtos, um por
  linha, com `id`, `text` e `metadata`, prontos para indexar no ChromaDB.

As zonas de risco e as recomendações são heurísticas: usam a frequência
histórica de falhas em cada faixa de valores dos sensores. Não são um modelo
preditivo treinado.

## Dashboard Industrial

```powershell
python -m streamlit run dashboard\app.py
```

Lê os dados do PostgreSQL e mostra, com filtros de período, máquina, situação e
sensor: os totais do recorte, onde as falhas se concentram (a faixa de valores
de sensor com a maior taxa de falha, pelo mesmo critério dos relatórios),
falhas ao longo do tempo e por máquina, as médias do sensor escolhido (por
situação, por mês e taxa de falha por faixa de valor) e os sensores que mais
mudam quando a máquina falha.

Nos gráficos, amarelo marca falha e verde-sálvia marca "sem falha". Se o banco
estiver fora do ar, o dashboard avisa e usa o CSV limpo local. Os cálculos
ficam em `dashboard/metricas.py`; o tema fica em `.streamlit/config.toml`, na
raiz, porque o Streamlit lê a configuração da pasta de onde é executado.

O painel **Assistente IA** à direita conversa com o agente RAG (seção
abaixo). Cada resposta tem um painel "Como cheguei nessa resposta" com o SQL
executado, o resultado e os trechos de manual consultados. Sem
`GEMINI_API_KEY` no `.env`, o painel mostra o que está faltando e o resto do
dashboard funciona normalmente.

## Agente RAG (Busca + Dados)

O agente em `src/agente/` responde perguntas cruzando os dados de sensores do
PostgreSQL com os manuais técnicos indexados, usando function calling com
duas ferramentas:

- `consultar_banco`: o LLM escreve um `SELECT` e a ferramenta executa numa
  sessão **somente leitura** do PostgreSQL, com tempo limite por consulta.
  Comandos que alteram o banco ou a sessão são recusados antes de executar;
- `buscar_manuais`: busca trechos nos manuais indexados no ChromaDB
  (`chroma_db/`, coleção `manuais_rag`, criada por `src/rag_ingest.py`).
  A busca é híbrida: junta a busca semântica (embeddings multilíngues do
  `multilingual-e5-small`, que entende sinônimos em português) com uma busca
  por palavras-chave (BM25), que garante termos exatos como "Makino-L2". Sem
  o ChromaDB, usa só o BM25 em `data/processed/relatorios/documentos_rag.jsonl`
  e nos arquivos de `data/manuais/`.

### Configuração do LLM

- Gemini (padrão): crie a chave no Google AI Studio
  (https://aistudio.google.com/apikey) e coloque em `GEMINI_API_KEY`.
  O modelo padrão é `gemini-3.5-flash-lite`: rápido, barato e estável. Os
  Flash maiores (como o `gemini-3.8-flash`) dão erro 503 (servidor
  sobrecarregado) com frequência. Para usar outro, troque `LLM_MODEL`; em
  `LLM_MODEL_RESERVA` dá para indicar um modelo que entra quando o principal
  continua dando 503 depois das novas tentativas;
- OpenAI: `OPENAI_API_KEY` e `LLM_MODEL` (ex.: `gpt-4o-mini`);
- modelo local com Ollama: `LLM_BASE_URL=http://localhost:11434/v1` e um
  modelo com suporte a tools em `LLM_MODEL` (ex.: `qwen2.5`, `llama3.1`).

**Velocidade:** cada pergunta faz no mínimo duas chamadas ao modelo (uma para
escolher as ferramentas e outra para escrever a resposta). O Flash-Lite já
usa o raciocínio mínimo por padrão; nos Flash maiores, cujo padrão é raciocínio
alto, o agente envia `reasoning_effort=low`. Para escolher, use
`LLM_REASONING_EFFORT=low`, `medium` ou `high` no `.env`. Erros temporários
(429 e 5xx) são repetidos automaticamente até `LLM_MAX_TENTATIVAS` vezes (padrão
4). Com `-v`, o agente mostra quanto tempo levou cada etapa; no dashboard, o
tempo aparece em "Como cheguei nessa resposta".

O Gemini é acessado pelo endpoint compatível com a OpenAI
(`https://generativelanguage.googleapis.com/v1beta/openai/`), por isso o
pacote usado é o `openai` mesmo, sem SDK extra.

### Uso

```powershell
python -m src.agente -v "Quantas falhas a Makino-L1 teve com pressão hidráulica baixa e o que o manual recomenda?"
python -m src.agente              # modo interativo
python -m src.agente.avaliar      # roda as perguntas de teste e salva data\processed\avaliacao_agente.md
```

### Banco vetorial (`src/rag_ingest.py`)

O ingest indexa na coleção `manuais_rag` de `chroma_db/`:

- `data/processed/relatorios/documentos_rag.jsonl`: um documento por
  assunto (sensor, diagnóstico, recomendação...), já com metadados;
- `data/manuais/` (e subpastas): **coloque aqui os manuais técnicos reais**
  das máquinas, em `.pdf`, `.md` ou `.txt`. PDFs são lidos página a página
  (a página é citada na resposta); markdown é dividido pelas seções. PDFs
  escaneados (só imagem, sem texto) são ignorados com um aviso.

Depois de adicionar ou trocar manuais, rode `python src\rag_ingest.py` de
novo. Cada trecho guarda `fonte`, `tipo`, `secao` e `pagina` nos metadados,
que o agente usa para citar a origem. A coleção é recriada a cada execução
(não duplica nem deixa trechos antigos). O `chroma_db/` não fica no git:
cada pessoa gera o seu com o ingest.

Os vetores vêm de `src/embeddings.py` (`multilingual-e5-small`, ONNX em CPU).
A primeira execução baixa o modelo (~120 MB) do Hugging Face para o cache do
usuário. O nome do modelo fica nos metadados da coleção e o agente usa o
mesmo nas perguntas. Para usar uma cópia local do modelo (sem internet),
aponte `EMBEDDING_MODEL_DIR` para a pasta com `model_quantized.onnx` e
`tokenizer.json`.

## Testes e integração contínua

```powershell
pip install -r requirements-dev.txt
docker compose up -d db
python -m pytest -v
```

Os testes que usam banco rodam num banco **separado** (`data_harvest_test`),
criado e carregado sozinho no mesmo servidor; o banco de trabalho não é
tocado. Sem PostgreSQL rodando, esses testes são pulados e os demais rodam.
Não precisam de chave de API nem de internet: o LLM e o modelo de embedding
são simulados. Cobrem:

- `test_etl.py`: validação do CSV, carga idempotente e recusa de CSV divergente;
- `test_banco.py`: contagens, regras do schema (FK, NOT NULL, CHECK, UNIQUE,
  RESTRICT, CASCADE) e se `sql/schema_postgres.sql` está atualizado;
- `test_agente.py`: ferramenta SQL (somente leitura, bloqueio de comandos,
  tempo limite), retriever e o loop de function calling do agente;
- `test_rag_ingest.py`: ingest no ChromaDB + leitura pelo retriever;
- `test_metricas.py`: cálculos do dashboard.

O GitHub Actions (`.github/workflows/testes.yml`) roda o pipeline e os testes
com um PostgreSQL 15 em Python 3.10 e 3.12 a cada push na `main` e em todo
pull request, e também testa o serviço `etl` do Docker Compose.
