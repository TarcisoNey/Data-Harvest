"""Modelo de embedding multilíngue usado pelo banco vetorial.

O modelo padrão do Chroma (all-MiniLM-L6-v2) foi treinado em inglês e erra
bastante com textos em português. Aqui usamos o multilingual-e5-small
(intfloat, versão ONNX quantizada do Xenova): 384 dimensões, roda em CPU com
onnxruntime + tokenizers, que já vêm instalados com o chromadb.

O E5 espera prefixos: "passage: " nos documentos e "query: " nas perguntas.
Por isso o ingest (src/rag_ingest.py) e o retriever (src/agente/retriever.py)
calculam os vetores por esta classe, e não pela função padrão do Chroma.

Na primeira execução o modelo (~120 MB) é baixado do Hugging Face para o
cache do usuário. Para usar uma cópia local, aponte EMBEDDING_MODEL_DIR para
a pasta com model_quantized.onnx (ou onnx/model_quantized.onnx) e tokenizer.json.
"""
import os
from pathlib import Path

import numpy as np

MODELO = "multilingual-e5-small"
REPOSITORIO_HF = "Xenova/multilingual-e5-small"
DIMENSAO = 384
MAX_TOKENS = 512


def _arquivos_do_modelo():
    pasta = os.getenv("EMBEDDING_MODEL_DIR")
    if pasta:
        pasta = Path(pasta)
        modelo = next((p for p in (pasta / "model_quantized.onnx", pasta / "onnx/model_quantized.onnx")
                       if p.is_file()), None)
        tokenizer = pasta / "tokenizer.json"
        if modelo is None or not tokenizer.is_file():
            raise FileNotFoundError(f"EMBEDDING_MODEL_DIR={pasta} não tem model_quantized.onnx e tokenizer.json")
        return modelo, tokenizer
    from huggingface_hub import hf_hub_download

    arquivos = ("onnx/model_quantized.onnx", "tokenizer.json")
    try:  # já baixado: usa o cache sem consultar a internet (mais rápido e funciona offline)
        return tuple(Path(hf_hub_download(REPOSITORIO_HF, a, local_files_only=True)) for a in arquivos)
    except Exception:
        return tuple(Path(hf_hub_download(REPOSITORIO_HF, a)) for a in arquivos)


class EmbedderE5:
    nome = MODELO

    def __init__(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        modelo, tokenizer = _arquivos_do_modelo()
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>") or 1, pad_token="<pad>")
        opcoes = ort.SessionOptions()
        opcoes.log_severity_level = 3
        self.sessao = ort.InferenceSession(str(modelo), opcoes, providers=["CPUExecutionProvider"])
        self.entradas = {i.name for i in self.sessao.get_inputs()}

    def _vetores(self, textos, lote=32):
        saida = []
        for i in range(0, len(textos), lote):
            cod = self.tokenizer.encode_batch(textos[i:i + lote])
            ids = np.array([c.ids for c in cod], dtype=np.int64)
            mascara = np.array([c.attention_mask for c in cod], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mascara,
                    "token_type_ids": np.zeros_like(ids)}
            estados = self.sessao.run(None, {k: v for k, v in feed.items() if k in self.entradas})[0]
            m = mascara[..., None].astype(np.float32)
            media = (estados * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)  # mean pooling
            saida.append(media / np.linalg.norm(media, axis=1, keepdims=True))     # normalização L2
        return np.vstack(saida) if saida else np.zeros((0, DIMENSAO), dtype=np.float32)

    def documentos(self, textos):
        return self._vetores([f"passage: {t}" for t in textos]).tolist()

    def consulta(self, texto):
        return self._vetores([f"query: {texto}"])[0].tolist()
