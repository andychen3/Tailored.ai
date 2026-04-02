import logging
import os
from dotenv import load_dotenv
from pinecone import Pinecone, IndexEmbed

logger = logging.getLogger(__name__)

load_dotenv()

INDEX_NAME = "tailored"
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

pc = Pinecone(api_key=PINECONE_API_KEY)

if not pc.has_index(INDEX_NAME):
    pc.create_index_for_model(
        name=INDEX_NAME,
        cloud="aws",
        region="us-east-1",
        embed=IndexEmbed(
            model="llama-text-embed-v2",
            metric="cosine",
            field_map={"text": "chunk_text"},
        ),
    )
    logger.info("Created new Pinecone index: %s", INDEX_NAME)
else:
    logger.info("Connected to existing Pinecone index: %s", INDEX_NAME)

index = pc.Index(INDEX_NAME)
