import os
import chromadb

def chunk_text(text, chunk_size=800, overlap=100):
    """
    Divide um texto longo em blocos (chunks) menores (entre 500 e 1000 caracteres)
    com sobreposição para manter o contexto.
    """
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    return chunks

def process_and_store_documents(docs_dir="data"):
    """
    Varre a pasta 'data' recursivamente à procura de ficheiros .md ou .txt,
    aplica o chunking e guarda no ChromaDB.
    """
    # Inicializa o cliente persistente do ChromaDB
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="manuais_rag")

    all_ids = []
    all_documents = []
    
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        print(f"Aviso: A pasta '{docs_dir}' foi criada.")
        return

    # Varre recursivamente todas as subpastas em 'data'
    for root, dirs, files in os.walk(docs_dir):
        for filename in files:
            if filename.endswith((".md", ".txt")):
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        chunks = chunk_text(content, chunk_size=800, overlap=100)
                        
                        for idx, chunk in enumerate(chunks):
                            chunk_id = f"{filename}_chunk_{idx}"
                            all_ids.append(chunk_id)
                            all_documents.append(chunk)
                            
                    print(f"Processado: {filename} -> {len(chunks)} chunks gerados.")
                except Exception as e:
                    print(f"Erro ao ler {filename}: {e}")
                    
    # Insere os dados na base vetorial
    if all_documents:
        collection.add(
            documents=all_documents,
            ids=all_ids
        )
        print(f"\n🚀 Sucesso! Total de {len(all_documents)} chunks indexados no ChromaDB.")
    else:
        print("Total de chunks gerados: 0. Nenhum ficheiro compatível encontrado.")

if __name__ == "__main__":
    process_and_store_documents()