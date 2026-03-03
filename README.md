# Annex A PDF Parser

This tool extracts reference tables from Annex A sections in QSP PDF files.

## Features

- Automatically locates "ANNEX A" sections in PDF files
- Extracts reference tables with:
  - Reference number (REF #)
  - NDID/Document Control Number
  - Title of Reference
- Handles cases where NDID is merged with the title
- Processes multiple PDF files in batch
- Outputs to CSV format

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Download PDFs from Azure Blob Storage

Download QSP PDF files from the Azure storage account to the `data/` folder:

```bash
python download_blobs.py
```

The script uses **DefaultAzureCredential** for authentication (Azure CLI login, managed identity, etc.). Make sure you're logged in via `az login` or have a managed identity configured.

You can override the defaults with environment variables:
- `AZURE_STORAGE_ACCOUNT` (default: `ndrcnntgdevniobe`)
- `AZURE_CONTAINER_NAME` (default: `qsps`)

The script skips files that already exist locally with the same size.

### Run the parser
```bash
python annex_parser.py
```

3. The results will be saved to `annex_a_references.csv` with the following columns:
   - `qsp_filename`: Name of the source PDF file
   - `reference_number`: The REF # (A, A1, A2, etc.)
   - `ndid_document_control_no`: The document control number
   - `title_of_reference`: The title/description of the reference

## How It Works

1. **PDF Scanning**: Scans all PDF files in the `data/` folder
2. **Annex A Detection**: Finds pages containing "ANNEX A" text
3. **Table Extraction**: Extracts tables from Annex A pages and subsequent pages
4. **Data Parsing**: Parses each row to extract reference data
5. **NDID Separation**: Detects and separates NDID codes that are merged with titles using regex patterns
6. **CSV Export**: Saves all extracted data to a CSV file

## Document Control Number Patterns

The parser recognizes various NDID/Document Control Number patterns including:
- `C-28-395-000/NY-001` (full format)
- `B-GN-181-105/FP-E00` (variant format)
- `AL11` (short format)
- `C C-24-535-000/NY-Z02` (format with space)

## Troubleshooting

- **No results**: Check if PDFs contain "ANNEX A" text
- **Missing data**: Some PDFs may have complex table formats - see logs for details
- **Merged NDID**: If NDID codes aren't being separated correctly, you can adjust the regex patterns in `extract_ndid_from_title()` method

## Logs

The script provides detailed logging showing:
- Which PDFs are being processed
- Where "ANNEX A" was found
- Number of references extracted per file
- Any errors encountered

## Customization

You can modify the script to:
- Change the input folder (default: `data/`)
- Change the output file name (default: `annex_a_references.csv`)
- Adjust NDID detection patterns
- Export to different formats (Excel, JSON)
