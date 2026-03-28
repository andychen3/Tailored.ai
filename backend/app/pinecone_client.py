import os
from dotenv import load_dotenv
from pinecone import Pinecone, IndexEmbed

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
    print(f"Created new Pinecone index: {INDEX_NAME}")
else:
    print(f"Connected to existing Pinecone index: {INDEX_NAME}")

index = pc.Index(INDEX_NAME)
