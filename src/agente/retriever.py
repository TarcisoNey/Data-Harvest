"""Retriever dos manuais técnicos.

Quando a coleção do ChromaDB existe (criada por src/rag_ingest.py), a busca
é HÍBRIDA: junta a busca semântica do Chroma (embeddings multilíngues do
multilingual-e5-small, de src/embeddings.py) com uma busca por palavras-chave
(BM25) sobre os mesmos documentos, e combina as duas listas por Reciprocal
Rank Fusion (RRF). A semântica entende sinônimos ("mancal do fuso" ~
"rolamento do spindle"); o BM25 garante termos exatos ("Makino-L2", "torque").

Sem ChromaDB, usa só o BM25 sobre data/processed/relatorios/documentos_rag.jsonl
e os .md/.txt de data/manuais/. Todos devolvem o mesmo formato (Trecho).
"""
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "buscar_manuais",
        "description": (
            "Busca trechos nos manuais técnicos e relatórios de manutenção indexados. "
            "Use para procedimentos, limites e faixas de operação recomendadas, "
            "diagnósticos de falha, causas e recomendações de manutenção."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "O que procurar, em linguagem natural (ex.: 'pressão hidráulica baixa causa e ação').",
                }
            },
            "required": ["consulta"],
        },
    },
}


@dataclass
class Trecho:
    id: str
    texto: str
    fonte: str
    score: float

    def como_dict(self):
        return {"id": self.id, "fonte": self.fonte, "score": round(self.score, 3), "texto": self.texto}


def _fonte(id_: str, meta: dict | None) -> str:
    """Nome legível da origem do trecho, pelos metadados ou, sem eles, pelo id."""
    meta = meta or {}
    fonte = meta.get("fonte") or meta.get("source") or meta.get("arquivo")
    if not fonte:  # ids do rag_ingest antigo: "relatorio_downtime.md_chunk_3"
        m = re.match(r"(.+?)_chunk_(\d+)$", id_)
        fonte = f"{m.group(1)} (trecho {m.group(2)})" if m else id_
    if meta.get("secao"):
        fonte = f"{fonte} - {meta['secao']}"
    elif meta.get("tipo") and meta["tipo"] != "manual" and meta.get("pagina") is None:
        fonte = f"{fonte} ({meta['tipo']})"
    if meta.get("pagina") is not None:
        fonte = f"{fonte}, p. {meta['pagina']}"
    return fonte


# ---------------------------------------------------------------------------
# BM25 (palavras-chave, sem dependências)
# ---------------------------------------------------------------------------
_STOPWORDS = set(
    "a o as os um uma de da do das dos em no na nos nas e ou que para por com sem "
    "como qual quais quando onde se ao aos the of and to in is".split()
)


def _tokens(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9_]+", texto) if t not in _STOPWORDS and len(t) > 1]


def _quebrar(texto: str, tamanho: int = 900, sobreposicao: int = 150) -> list[str]:
    if len(texto) <= tamanho:
        return [texto]
    partes, inicio = [], 0
    while inicio < len(texto):
        partes.append(texto[inicio: inicio + tamanho])
        inicio += tamanho - sobreposicao
    return partes


def carregar_documentos(fontes: list[Path]) -> list[tuple[str, str, str]]:
    """Lê .jsonl (id/text/metadata) e .md/.txt. Devolve (id, texto, fonte)."""
    docs = []
    for fonte in fontes:
        arquivos = sorted(fonte.glob("**/*")) if fonte.is_dir() else [fonte]
        for arq in arquivos:
            if not arq.is_file():
                continue
            if arq.suffix == ".jsonl":
                for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines()):
                    if linha.strip():
                        d = json.loads(linha)
                        meta = d.get("metadata", {})
                        docs.append((d.get("id", f"{arq.stem}_{n}"), d["text"],
                                     f"{arq.name} ({meta.get('tipo', 'documento')})"))
            elif arq.suffix in {".md", ".txt"}:
                for n, parte in enumerate(_quebrar(arq.read_text(encoding="utf-8"))):
                    docs.append((f"{arq.stem}_chunk{n}", parte, arq.name))
    return docs


class RetrieverLocal:
    nome = "local (BM25)"

    def __init__(self, fontes: list[Path] | None = None, docs=None, k1: float = 1.5, b: float = 0.75):
        self.docs = docs if docs is not None else carregar_documentos(fontes or [])
        if not self.docs:
            raise FileNotFoundError(f"Nenhum documento encontrado em: {[str(f) for f in fontes or []]}")
        self.k1, self.b = k1, b
        self.tf = [Counter(_tokens(texto)) for _, texto, _ in self.docs]
        self.tam = [sum(c.values()) for c in self.tf]
        self.media = sum(self.tam) / len(self.tam)
        df = Counter(t for c in self.tf for t in c)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def buscar(self, consulta: str, k: int = 4) -> list[Trecho]:
        termos = _tokens(consulta)
        pontos = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in termos:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self.tam[i] / self.media)
                    )
            if s > 0:
                pontos.append((s, i))
        pontos.sort(reverse=True)
        return [Trecho(self.docs[i][0], self.docs[i][1], self.docs[i][2], s) for s, i in pontos[:k]]


# ---------------------------------------------------------------------------
# ChromaDB (semântica)
# ---------------------------------------------------------------------------
class ChromaRetriever:
    nome = "chromadb"

    def __init__(self, caminho: Path, colecao: str):
        import chromadb

        self.cliente = chromadb.PersistentClient(path=str(caminho))
        self.colecao = self.cliente.get_collection(colecao)
        if self.colecao.count() == 0:
            raise ValueError(f"Coleção '{colecao}' está vazia. Rode: python src/rag_ingest.py")
        # A pergunta precisa virar vetor com o MESMO modelo usado no ingest.
        from ..embeddings import MODELO, EmbedderE5

        modelo = (self.colecao.metadata or {}).get("embedding_model")
        if modelo == MODELO:
            self.embedder = EmbedderE5()
            self.nome = f"chromadb ({MODELO})"
        else:  # índice antigo, feito com a função padrão do Chroma
            self.embedder = None
            print("[retriever] Índice criado com o embedding padrão do Chroma. "
                  "Rode python src/rag_ingest.py para usar o modelo multilíngue.")

    def todos_documentos(self) -> list[tuple[str, str, str]]:
        g = self.colecao.get(include=["documents", "metadatas"])
        metas = g.get("metadatas") or [None] * len(g["ids"])
        return [(i, d, _fonte(i, m)) for i, d, m in zip(g["ids"], g["documents"], metas)]

    def buscar(self, consulta: str, k: int = 4) -> list[Trecho]:
        if self.embedder is not None:
            r = self.colecao.query(query_embeddings=[self.embedder.consulta(consulta)], n_results=k)
        else:
            r = self.colecao.query(query_texts=[consulta], n_results=k)
        metas = (r.get("metadatas") or [[None] * len(r["ids"][0])])[0]
        return [
            Trecho(id_, texto, _fonte(id_, meta), 1 / (1 + dist))
            for id_, texto, meta, dist in zip(r["ids"][0], r["documents"][0], metas, r["distances"][0])
        ]


class RetrieverHibrido:
    """Chroma + BM25 sobre os mesmos documentos, combinados por RRF."""

    def __init__(self, chroma: ChromaRetriever, rrf_k: int = 60):
        self.chroma = chroma
        self.nome = f"híbrido ({getattr(chroma, 'nome', 'chromadb')} + BM25)"
        self.bm25 = RetrieverLocal(docs=chroma.todos_documentos())
        self.rrf_k = rrf_k

    def buscar(self, consulta: str, k: int = 4) -> list[Trecho]:
        candidatos = max(k * 2, 6)
        pontos, trechos = {}, {}
        for lista in (self.chroma.buscar(consulta, candidatos), self.bm25.buscar(consulta, candidatos)):
            for posicao, t in enumerate(lista):
                pontos[t.id] = pontos.get(t.id, 0.0) + 1 / (self.rrf_k + posicao)
                trechos.setdefault(t.id, t)
        melhores = sorted(pontos, key=pontos.get, reverse=True)[:k]
        return [Trecho(i, trechos[i].texto, trechos[i].fonte, pontos[i]) for i in melhores]


# ---------------------------------------------------------------------------
def criar_retriever(config):
    """Híbrido se a coleção do ChromaDB existir; senão, só o BM25 local."""
    if config.chroma_path.exists():
        try:
            return RetrieverHibrido(ChromaRetriever(config.chroma_path, config.chroma_collection))
        except Exception as erro:  # coleção ausente/vazia, chromadb não instalado...
            print(f"[retriever] ChromaDB indisponível ({erro}); usando busca local.")
    return RetrieverLocal(config.documentos_fallback)
