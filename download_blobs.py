"""
Azure Blob Storage Downloader
Downloads PDF files from an Azure Blob Storage container to the local data/ folder.
Uses DefaultAzureCredential for authentication (Azure CLI, managed identity, etc.).
"""

import os
import logging
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT", "ndrcnntgdevniobe")
CONTAINER_NAME = os.environ.get("AZURE_CONTAINER_NAME", "qsps")
DOWNLOAD_FOLDER = Path("data")


def get_container_client() -> ContainerClient:
    """Create a ContainerClient using DefaultAzureCredential."""
    account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
    credential = DefaultAzureCredential()
    return ContainerClient(account_url, CONTAINER_NAME, credential=credential)


def download_pdfs():
    """Download all PDF blobs from the container to the local data/ folder."""
    DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    container_client = get_container_client()
    logger.info(
        "Connecting to storage account '%s', container '%s'",
        STORAGE_ACCOUNT_NAME,
        CONTAINER_NAME,
    )

    downloaded = 0
    skipped = 0

    for blob in container_client.list_blobs():
        if not blob.name.lower().endswith(".pdf"):
            continue

        # Use only the filename (ignore any virtual directory prefixes)
        filename = Path(blob.name).name
        dest_path = DOWNLOAD_FOLDER / filename

        # Skip if the file already exists with the same size
        if dest_path.exists() and dest_path.stat().st_size == blob.size:
            logger.info("Skipping (already exists): %s", filename)
            skipped += 1
            continue

        logger.info("Downloading: %s (%d bytes)", filename, blob.size)
        blob_client = container_client.get_blob_client(blob.name)
        with open(dest_path, "wb") as f:
            stream = blob_client.download_blob()
            stream.readinto(f)
        downloaded += 1

    logger.info(
        "Done. Downloaded: %d, Skipped: %d, Total PDFs: %d",
        downloaded,
        skipped,
        downloaded + skipped,
    )


if __name__ == "__main__":
    download_pdfs()
