"""Indexa os documentos do RAG no ChromaDB (coleção usada pelo agente).

Fontes indexadas:
  - data/processed/relatorios/documentos_rag.jsonl: os relatórios gerados por
    src/relatorios.py, já divididos em um documento por assunto (sensor,
    diagnóstico, recomendação...), com metadados;
  - data/manuais/**/*.pdf, *.md e *.txt: manuais técnicos. PDFs são lidos
    página a página (a página vai nos metadados, para citação); markdown é
    dividido pelas seções. Partes grandes viram blocos de ~800 caracteres.

Os vetores são calculados pelo modelo multilíngue de src/embeddings.py
(multilingual-e5-small), o mesmo que o agente usa nas perguntas. O nome do
modelo fica nos metadados da coleção, e o agente confere antes de buscar.

A coleção é recriada a cada execução, então rodar de novo não duplica nem
deixa trechos antigos para trás.

Uso (na raiz do repositório):
    python src/rag_ingest.py
"""
import json
import re
import sys
from pathlib import Path

import chromadb

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.embeddings import MODELO, EmbedderE5  # noqa: E402
CHROMA_PATH = RAIZ / "chroma_db"
COLECAO = "manuais_rag"
JSONL_RELATORIOS = RAIZ / "data/processed/relatorios/documentos_rag.jsonl"
PASTA_MANUAIS = RAIZ / "data/manuais"


def chunk_text(text, chunk_size=800, overlap=100):
    """
    Divide um texto longo em blocos (chunks) menores (entre 500 e 1000 caracteres)
    com sobreposição para manter o contexto. Tenta cortar no fim de uma frase
    ou parágrafo em vez de no meio de uma palavra.
    """
    if len(text) <= chunk_size:
        return [text]
    chunks, inicio = [], 0
    while inicio < len(text):
        fim = min(inicio + chunk_size, len(text))
        if fim < len(text):
            corte = max(text.rfind("\n", inicio, fim), text.rfind(". ", inicio, fim))
            if corte > inicio + chunk_size // 2:
                fim = corte + 1
        chunks.append(text[inicio:fim].strip())
        if fim >= len(text):
            break
        inicio = max(fim - overlap, inicio + 1)
    return [c for c in chunks if c]


def dividir_por_secoes(texto):
    """Quebra um markdown nos títulos (#, ##, ###). Devolve (título, conteúdo)."""
    partes = re.split(r"(?m)^(#{1,3} .+)$", texto)
    secoes, titulo = [], ""
    if partes[0].strip():
        secoes.append(("", partes[0].strip()))
    for i in range(1, len(partes), 2):
        titulo = partes[i].lstrip("#").strip()
        conteudo = partes[i + 1].strip() if i + 1 < len(partes) else ""
        if conteudo:
            secoes.append((titulo, conteudo))
    return secoes


def ler_relatorios(caminho=None):
    caminho = caminho or JSONL_RELATORIOS
    if not caminho.is_file():
        print(f"Aviso: {caminho} não encontrado (gere com: python src/relatorios.py).")
        return []
    docs = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            d = json.loads(linha)
            meta = {k: v for k, v in (d.get("metadata") or {}).items() if v is not None}
            meta.update(fonte=caminho.name, tipo=meta.get("tipo", "relatorio"))
            docs.append((d["id"], d["text"], meta))
    print(f"Processado: {caminho.name} -> {len(docs)} documentos.")
    return docs


def ler_pdf(arq):
    """Devolve [(pagina, texto)] de um PDF com texto (PDF escaneado não tem texto)."""
    from pypdf import PdfReader

    paginas = []
    for n, pagina in enumerate(PdfReader(arq).pages, 1):
        texto = re.sub(r"[ \t]+", " ", pagina.extract_text() or "").strip()
        if texto:
            paginas.append((n, texto))
    return paginas


def ler_manuais(pasta=None):
    """Lê .md, .txt e .pdf de data/manuais (e subpastas)."""
    pasta = pasta or PASTA_MANUAIS
    if not pasta.is_dir():
        return []
    docs = []
    for arq in sorted(pasta.rglob("*")):
        if arq.suffix.lower() not in {".md", ".txt", ".pdf"} or not arq.is_file():
            continue
        base = {"fonte": arq.name, "tipo": "manual"}
        n = 0
        try:
            if arq.suffix.lower() == ".pdf":
                partes = [({**base, "pagina": pag}, texto) for pag, texto in ler_pdf(arq)]
                if not partes:
                    print(f"Aviso: {arq.name} não tem texto extraível (PDF escaneado?). Ignorado.")
            else:
                texto = arq.read_text(encoding="utf-8")
                secoes = dividir_por_secoes(texto) if arq.suffix.lower() == ".md" else [("", texto)]
                partes = [({**base, "secao": titulo}, conteudo) for titulo, conteudo in secoes]
        except Exception as erro:
            print(f"Erro ao ler {arq.name}: {erro}")
            continue
        for meta, conteudo in partes:
            titulo = meta.get("secao", "")
            for chunk in chunk_text(conteudo, chunk_size=800, overlap=100):
                docs.append((f"{arq.relative_to(pasta).as_posix()}_chunk_{n}",
                             f"{titulo}\n{chunk}" if titulo else chunk, meta))
                n += 1
        print(f"Processado: {arq.name} -> {n} chunks gerados.")
    return docs


def process_and_store_documents():
    """Lê as fontes, recria a coleção e guarda tudo no ChromaDB."""
    docs = ler_relatorios() + ler_manuais()
    if not docs:
        print("Total de chunks gerados: 0. Nenhum documento encontrado.")
        return

    ids = [d[0] for d in docs]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        raise ValueError(f"IDs repetidos: {sorted(repetidos)}")

    print(f"Calculando embeddings ({MODELO}) de {len(docs)} chunks...")
    vetores = EmbedderE5().documentos([d[1] for d in docs])

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        client.delete_collection(COLECAO)  # recria do zero: sem trechos antigos
    except Exception:
        pass
    collection = client.create_collection(
        name=COLECAO,
        metadata={"hnsw:space": "cosine", "embedding_model": MODELO},
        embedding_function=None,  # os vetores vêm de src/embeddings.py
    )
    collection.add(ids=ids, embeddings=vetores, documents=[d[1] for d in docs],
                   metadatas=[d[2] for d in docs])
    print(f"\n🚀 Sucesso! Total de {collection.count()} chunks indexados em {CHROMA_PATH} ({COLECAO}).")


if __name__ == "__main__":
    process_and_store_documents()
