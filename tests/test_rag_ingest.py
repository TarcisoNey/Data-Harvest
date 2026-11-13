"""Testa o ingest do ChromaDB e a leitura pelo retriever do agente, juntos.

O modelo de embedding real (src/embeddings.py) é trocado por um falso e
determinístico, para o teste não baixar ~120 MB nem depender de rede.

Uso (na raiz):  python -m pytest tests/test_rag_ingest.py -v
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

chromadb = pytest.importorskip("chromadb")

import src.embeddings as embeddings  # noqa: E402
import src.rag_ingest as ingest  # noqa: E402
from src.agente.retriever import ChromaRetriever, RetrieverHibrido  # noqa: E402


class EmbedderFalso:
    """Saco de palavras com hash: textos com as mesmas palavras ficam próximos."""

    def _vetor(self, texto):
        v = np.zeros(embeddings.DIMENSAO)
        for palavra in texto.lower().split():
            v[int(hashlib.md5(palavra.encode()).hexdigest(), 16) % embeddings.DIMENSAO] += 1
        return (v / (np.linalg.norm(v) or 1)).tolist()

    def documentos(self, textos):
        return [self._vetor(t) for t in textos]

    def consulta(self, texto):
        return self._vetor(texto)


@pytest.fixture
def indice(tmp_path, monkeypatch):
    manuais = tmp_path / "manuais"
    manuais.mkdir()
    (manuais / "manual.md").write_text(
        "# Manual\n\n## Sistema hidráulico\n\nPressão nominal entre 100 e 130 bar.\n\n"
        "## Refrigeração\n\nTrocar o coolant a cada 500 horas.\n", encoding="utf-8")
    monkeypatch.setattr(ingest, "CHROMA_PATH", tmp_path / "chroma_db")
    monkeypatch.setattr(ingest, "PASTA_MANUAIS", manuais)
    monkeypatch.setattr(ingest, "EmbedderE5", EmbedderFalso)
    monkeypatch.setattr(embeddings, "EmbedderE5", EmbedderFalso)
    ingest.process_and_store_documents()
    return tmp_path / "chroma_db"


def test_ingest_indexa_relatorios_e_manuais_com_metadados(indice):
    col = chromadb.PersistentClient(path=str(indice)).get_collection(ingest.COLECAO)
    assert col.metadata["embedding_model"] == embeddings.MODELO
    g = col.get(include=["metadatas"])
    fontes = {m["fonte"] for m in g["metadatas"]}
    assert fontes == {"documentos_rag.jsonl", "manual.md"}
    assert {m.get("secao") for m in g["metadatas"] if m["fonte"] == "manual.md"} == {
        "Sistema hidráulico", "Refrigeração"}


def test_rodar_de_novo_nao_duplica(indice):
    antes = chromadb.PersistentClient(path=str(indice)).get_collection(ingest.COLECAO).count()
    ingest.process_and_store_documents()
    depois = chromadb.PersistentClient(path=str(indice)).get_collection(ingest.COLECAO).count()
    assert antes == depois


def test_retriever_hibrido_le_o_indice(indice):
    ret = RetrieverHibrido(ChromaRetriever(indice, ingest.COLECAO))
    assert "multilingual-e5-small" in ret.nome
    trechos = ret.buscar("trocar o coolant", 3)
    assert trechos[0].fonte == "manual.md - Refrigeração"
