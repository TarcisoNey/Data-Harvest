"""Configuração do agente RAG (lida do .env / variáveis de ambiente).

LLM
    O cliente usa a API no formato da OpenAI. O Gemini (Google AI Studio)
    e o Ollama aceitam esse mesmo formato, então o código é um só:

    Gemini (padrão) - gere a chave em https://aistudio.google.com/apikey:
        GEMINI_API_KEY=...
        LLM_MODEL=gemini-3.5-flash-lite   # opcional; qualquer modelo listado no AI Studio
        LLM_MODEL_RESERVA=gemini-3.6-flash # opcional; usado quando o principal dá 503/429

    OpenAI:
        OPENAI_API_KEY=sk-...
        LLM_MODEL=gpt-4o-mini

    Modelo local com Ollama (precisa de um modelo com suporte a tools,
    ex.: llama3.1, qwen2.5):
        LLM_BASE_URL=http://localhost:11434/v1
        LLM_MODEL=qwen2.5
        OPENAI_API_KEY=ollama        # qualquer valor, o Ollama ignora

Dados
    Banco SQL          o PostgreSQL do projeto, com a conexão do .env
                       (POSTGRES_*, DB_HOST, DB_PORT; veja src/database.py)
    CHROMA_PATH        pasta do ChromaDB persistido (padrão: chroma_db, criada por src/rag_ingest.py)
    CHROMA_COLLECTION  coleção dos manuais técnicos (padrão: manuais_rag)
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")  # sempre o .env da raiz, de onde quer que se rode
except ImportError:  # python-dotenv é opcional
    pass

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# gemini-3.5-flash-lite: rápido, barato e estável. Os Flash maiores (ex.: 3.8)
# vivem dando 503 (sobrecarga) no plano gratuito.
MODELO_PADRAO = {"gemini": "gemini-3.5-flash-lite", "openai": "gpt-4o-mini", "local": "qwen2.5"}


def _provedor():
    """gemini se GEMINI_API_KEY estiver definida; senão local (LLM_BASE_URL) ou openai."""
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("LLM_BASE_URL"):
        return "local"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "gemini"


def _caminho(variavel, padrao):
    valor = Path(os.getenv(variavel, padrao))
    return valor if valor.is_absolute() else RAIZ / valor


@dataclass
class Config:
    provedor: str = field(default_factory=_provedor)
    llm_model: str = ""
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    # Modelo usado quando o principal continua indisponível (503/429) depois
    # das novas tentativas. Vazio = sem reserva.
    llm_model_reserva: str | None = field(default_factory=lambda: os.getenv("LLM_MODEL_RESERVA") or None)
    # Só é enviada se LLM_TEMPERATURE estiver no .env: os modelos Gemini mais
    # novos ignoram temperature/top_p/top_k.
    llm_temperature: float | None = field(
        default_factory=lambda: float(os.environ["LLM_TEMPERATURE"]) if os.getenv("LLM_TEMPERATURE") else None)
    # Quanto o modelo "pensa" antes de responder (reasoning_effort da API).
    # Gemini Flash-Lite: não envia (o padrão do modelo, "minimal", já é o mais
    # rápido). Outros Gemini 3 Flash: "low" (o padrão da API é "high", lento
    # para um chat). Use LLM_REASONING_EFFORT=low/medium/high para escolher, ou
    # "padrao" para não enviar o parâmetro.
    llm_reasoning_effort: str | None = field(default_factory=lambda: os.getenv("LLM_REASONING_EFFORT"))
    llm_max_tentativas: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TENTATIVAS", "4")))

    chroma_path: Path = field(default_factory=lambda: _caminho("CHROMA_PATH", "chroma_db"))
    chroma_collection: str = field(default_factory=lambda: os.getenv("CHROMA_COLLECTION", "manuais_rag"))

    # Fontes usadas enquanto o ChromaDB não estiver pronto
    documentos_fallback: list[Path] = field(default_factory=lambda: [
        RAIZ / "data/processed/relatorios/documentos_rag.jsonl",
        RAIZ / "data/manuais",  # .md / .txt soltos nessa pasta, se existir
    ])

    max_passos: int = 6       # chamadas de ferramenta por pergunta
    max_linhas_sql: int = 50  # linhas devolvidas ao LLM por consulta
    k_trechos: int = 4        # trechos de manual por busca

    def __post_init__(self):
        self.llm_model = self.llm_model or os.getenv("LLM_MODEL") or MODELO_PADRAO[self.provedor]
        if self.llm_reasoning_effort is None and self.provedor == "gemini" and "lite" not in self.llm_model:
            self.llm_reasoning_effort = "low"
        if (self.llm_reasoning_effort or "").strip().lower() in {"", "padrao", "padrão", "default"}:
            self.llm_reasoning_effort = None
        if self.provedor == "gemini":
            self.llm_api_key = self.llm_api_key or os.getenv("GEMINI_API_KEY")
            self.llm_base_url = self.llm_base_url or GEMINI_BASE_URL
        elif self.provedor == "local":
            self.llm_api_key = self.llm_api_key or os.getenv("OPENAI_API_KEY") or "ollama"
            self.llm_base_url = self.llm_base_url or os.getenv("LLM_BASE_URL")
        else:
            self.llm_api_key = self.llm_api_key or os.getenv("OPENAI_API_KEY")


def criar_cliente_llm(config: Config):
    """Cria o cliente do LLM (Gemini, OpenAI ou Ollama, todos no formato da OpenAI)."""
    from openai import OpenAI

    if not config.llm_api_key:
        raise RuntimeError(
            "LLM não configurado. Defina GEMINI_API_KEY no .env "
            "(chave do Google AI Studio: https://aistudio.google.com/apikey)."
        )
    # max_retries: o SDK repete sozinho, com espera crescente, os erros
    # temporários (429, 500, 502, 503, 504) antes de desistir.
    return OpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url,
                  max_retries=config.llm_max_tentativas, timeout=60)
