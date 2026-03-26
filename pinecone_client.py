import os
from dotenv import load_dotenv
from pinecone import Pinecone, IndexEmbed

load_dotenv()

pc = Pinecone(
    api_key=os.getenv("PINECONE_API_KEY"),
)

if not pc.has_index("tailored"):
    pc.create_index_for_model(
        name="tailored",
        cloud="aws",
        region="us-east-1",
        embed=IndexEmbed(model="llama-text-embed-v2", field_map={"text": "chunk_text"}),
    )


index = pc.Index("tailored")
