import pprint
import chromadb
import llama_index.core.retrievers
from chromadb.utils import embedding_functions
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.vector_stores import VectorStoreQuery
from llama_index.core import VectorStoreIndex, QueryBundle
from llama_index.core.schema import NodeWithScore
from typing import Any, List, Optional
from llama_index.core.vector_stores import (
    MetadataFilter,
    MetadataFilters,
    FilterOperator,
)
import re
from retriever.base_retriever import BaseRetriever


class ChromadbRetriever(llama_index.core.retrievers.BaseRetriever):
    """
    Retriever over a Chroma database vector store.
    Refer from https://docs.llamaindex.ai/en/stable\
    /examples/low_level/oss_ingestion_retrieval.html
    """

    def __init__(
            self,
            collection: chromadb.PersistentClient,
            embed_model: Any,
            query_mode: str = "default",
            similarity_top_k: int = 2,
    ) -> None:
        self._embed_model = embed_model
        self._query_mode = query_mode
        self._similarity_top_k = similarity_top_k
        self._vector_store = ChromaVectorStore(chroma_collection=collection)
        self._index = VectorStoreIndex.from_vector_store \
            (vector_store=self._vector_store, embed_model=embed_model)
        super().__init__()

    def _retrieve(self, query_str: QueryBundle) -> List[NodeWithScore]:
        query_embedding = self._embed_model.get_query_embedding(
            query_str
        )
        query_str = query_str.query_str.lower()
        filters = None
        if 'course' in query_str:
            pattern = r'(course|unit)\s*(\d{5})'
            _match = re.findall(pattern, query_str)
            if _match:
                filters = MetadataFilters(
                    filters=[
                        MetadataFilter(
                            key="Course Number", operator=FilterOperator.EQ, value=str(_match[0][1])
                        ),
                    ]
                )
        vector_store_query = VectorStoreQuery(
            query_embedding=query_embedding,
            similarity_top_k=self._similarity_top_k,
            mode=self._query_mode,
            filters=filters
        )
        query_result = self._vector_store.query(vector_store_query)

        nodes_with_scores = []
        for index, node in enumerate(query_result.nodes):
            score: Optional[float] = None
            if query_result.similarities is not None:
                score = query_result.similarities[index]
            nodes_with_scores.append(NodeWithScore(node=node, score=score))

        return nodes_with_scores


class EmbeddingRetriever(BaseRetriever):

    def retrieve(self, question: str, **kwargs):
        """
        top_n parameter is not being used here because it is being preset during initialization
        """
        doc_nodes = []
        for slave in self.slave_retrievers:
            doc_nodes.extend(slave.retrieve(question))

        doc_nodes.sort(key=lambda node: node.score, reverse=True)
        doc_nodes = doc_nodes[:self.top_n]
        docs = [node.text for node in doc_nodes]

        return docs

    def __init__(self, top_n: int = 5):
        embed_name = "BAAI/bge-large-en-v1.5"
        huggingface_ef = embedding_functions.HuggingFaceEmbeddingFunction(
            api_key="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",  # huggingface api
            model_name=embed_name
        )
        client = chromadb.PersistentClient(path="retriever/chroma_meta")
        embed_model = HuggingFaceEmbedding(model_name=embed_name)

        course_collection = client.get_collection(name="course_baai", embedding_function=huggingface_ef)
        paper_collection = client.get_collection(name="paper_baai", embedding_function=huggingface_ef)

        course_retriever = ChromadbRetriever(course_collection, embed_model,
                                             query_mode="default", similarity_top_k=top_n)
        paper_retriever = ChromadbRetriever(paper_collection, embed_model,
                                            query_mode="default", similarity_top_k=top_n)

        self.slave_retrievers = [course_retriever, paper_retriever]
        self.top_n = top_n


if __name__ == "__main__":
    retriever = EmbeddingRetriever(5)
    pprint.pprint(retriever.retrieve("What are some publication by Graham Neubig?"))
