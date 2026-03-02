"""
Annex A PDF Parser
Extracts reference tables from Annex A sections in PDF files.
"""

import pdfplumber
import pandas as pd
import re
from pathlib import Path
from typing import List, Dict, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnnexAParser:
    """Parser for extracting Annex A reference tables from PDF files."""
    
    def __init__(self, pdf_folder: str = "data", output_file: str = "annex_a_references.csv"):
        self.pdf_folder = Path(pdf_folder)
        self.output_file = output_file
        self.results = []
        
    def extract_ndid_from_title(self, title: str) -> tuple[Optional[str], str]:
        """
        Extract NDID/Document control number from title if it's merged.
        Common patterns: 
        - Starts with alphanumeric codes like "C-28-395-000/NY-001"
        - Followed by the actual title
        
        Returns: (ndid, cleaned_title)
        """
        if not title or pd.isna(title):
            return None, ""
        
        # Pattern to match document control numbers at the start
        # Examples: C-28-395-000/NY-001, B-GN-181-105/FP-E00, AL11, etc.
        patterns = [
            r'^([A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+/[A-Z]+-[A-Z0-9]+)\s+(.+)',  # C-28-395-000/NY-001
            r'^([A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+/[A-Z]+-[A-Z0-9]+)\s*(.+)',   # Without space
            r'^([A-Z]+-[A-Z0-9]+-[A-Z0-9]+/[A-Z]+-[A-Z0-9]+)\s+(.+)',  # B-GN-181-105/FP-E00
            r'^([A-Z]+[0-9]+)\s+(.+)',  # AL11
            r'^([A-Z]\s+[A-Z]+-[0-9]+-[0-9]+-[0-9]+/[A-Z]+-[A-Z0-9]+)\s+(.+)',  # C C-24-535-000/NY-Z02
        ]
        
        for pattern in patterns:
            match = re.match(pattern, title.strip())
            if match:
                ndid = match.group(1).strip()
                cleaned_title = match.group(2).strip()
                return ndid, cleaned_title
        
        return None, title.strip()
    
    def clean_cell_value(self, value) -> str:
        """Clean cell value by removing extra whitespace and handling None."""
        if value is None or pd.isna(value):
            return ""
        return str(value).strip().replace('\n', ' ').replace('  ', ' ')
    
    def is_reference_table(self, table: List) -> bool:
        """
        Check if a table is the Annex A reference table by examining headers.
        """
        if not table or len(table) == 0:
            return False
        
        # Combine first few rows to handle headers split across rows
        header_text = ""
        for row in table[:4]:  # Check first 4 rows
            if not row:
                continue
            row_text = ' '.join([str(cell).upper() if cell else '' for cell in row])
            header_text += " " + row_text
        
        # Look for key header terms in the combined header text
        has_ref = 'REF' in header_text
        has_ndid = 'NDID' in header_text or ('DOCUMENT' in header_text and 'CONTROL' in header_text)
        has_title = 'TITLE' in header_text and 'REFERENCE' in header_text
        
        return has_ref and has_ndid and has_title
    
    def parse_table_row(self, row: List, qsp_filename: str) -> Optional[Dict]:
        """
        Parse a single table row and extract reference data.
        
        Expected columns: REF #, NDID/DOCUMENT CONTROL NO, TITLE OF REFERENCE
        Can handle multi-column layouts with empty cells.
        """
        if not row or len(row) < 2:
            return None
        
        # Clean all cell values
        cleaned_row = [self.clean_cell_value(cell) for cell in row]
        
        # Find the reference number (first non-empty cell, typically in column 0 or 1)
        ref_num = ""
        for i in range(min(2, len(cleaned_row))):
            if cleaned_row[i]:
                ref_num = cleaned_row[i]
                break
        
        # Skip header rows and empty rows
        if not ref_num or ref_num.upper() in ['REF #', 'REF', '#', '', 'TEACHING POINTS']:
            return None
        
        # Skip rows that look like non-reference content
        ref_lower = ref_num.lower()
        skip_keywords = ['teaching', 'method:', 'media:', 'environment:', 'instructional', 
                        'demonstrate', 'describe', 'explain', 'practice', 'identify',
                        'operate', 'select', 'illuminate', 'comply', 'recall', 'official']
        if any(keyword in ref_lower for keyword in skip_keywords):
            return None
        
        # Valid reference numbers should be short (typically 1-4 characters like A, A1, A2, A10)
        if len(ref_num) > 5:
            return None
        
        # Extract NDID and Title from remaining columns
        # For multi-column layouts, find non-empty cells after the ref number
        remaining_cells = [cell for cell in cleaned_row[2:] if cell]
        
        if len(remaining_cells) == 0:
            # No data after ref number
            return None
        elif len(remaining_cells) == 1:
            # Only one value - could be either NDID or Title
            ndid = ""
            title = remaining_cells[0]
        else:
            # Two or more values - first is NDID, rest is Title
            ndid = remaining_cells[0]
            title = ' '.join(remaining_cells[1:])
        
        # Handle different column structures for backward compatibility
        if not ndid and not title and len(cleaned_row) >= 3:
            # Fallback to simple 3-column structure
            ndid = cleaned_row[1]
            title = cleaned_row[2]
        
        # Try to extract NDID from title if NDID column is empty
        if not ndid and title:
            extracted_ndid, cleaned_title = self.extract_ndid_from_title(title)
            if extracted_ndid:
                ndid = extracted_ndid
                title = cleaned_title
        
        # Skip rows without meaningful content
        if not title and not ndid:
            return None
        
        return {
            'qsp_filename': qsp_filename,
            'reference_number': ref_num,
            'ndid_document_control_no': ndid,
            'title_of_reference': title
        }
    
    def find_annex_a_pages(self, pdf) -> List[int]:
        """Find pages that contain 'ANNEX A - MAIN REFERENCES' section."""
        annex_pages = []
        
        for page_num, page in enumerate(pdf.pages):
            try:
                text = page.extract_text()
                if not text:
                    continue
                
                text_upper = text.upper()
                # Look specifically for "ANNEX A - MAIN REFERENCES" or "ANNEX A – MAIN REFERENCES"
                if ('ANNEX A' in text_upper and 'MAIN REFERENCE' in text_upper):
                    annex_pages.append(page_num)
                    logger.info(f"Found 'ANNEX A - MAIN REFERENCES' on page {page_num + 1}")
            except Exception as e:
                logger.warning(f"Error processing page {page_num + 1}: {str(e)}")
                continue
        
        return annex_pages
    
    def extract_tables_from_page(self, page) -> List:
        """Extract all tables from a page."""
        tables = page.extract_tables()
        return tables if tables else []
    
    def process_pdf(self, pdf_path: Path):
        """Process a single PDF file and extract Annex A references."""
        logger.info(f"Processing: {pdf_path.name}")
        qsp_filename = pdf_path.name
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Find pages with Annex A
                annex_pages = self.find_annex_a_pages(pdf)
                
                if not annex_pages:
                    logger.warning(f"No 'ANNEX A' found in {pdf_path.name}")
                    return
                
                # Extract tables from Annex A pages and subsequent pages
                for page_num in annex_pages:
                    # Check current page and next few pages for tables
                    for offset in range(3):  # Check up to 3 pages after Annex A
                        if page_num + offset < len(pdf.pages):
                            try:
                                page = pdf.pages[page_num + offset]
                                tables = self.extract_tables_from_page(page)
                                
                                for table in tables:
                                    # Only process tables that look like reference tables
                                    if not self.is_reference_table(table):
                                        continue
                                        
                                    logger.info(f"Found reference table on page {page_num + offset + 1}")
                                    for row in table:
                                        parsed_row = self.parse_table_row(row, qsp_filename)
                                        if parsed_row:
                                            self.results.append(parsed_row)
                                            logger.debug(f"Extracted: {parsed_row}")
                            except Exception as e:
                                logger.warning(f"Error extracting tables from page {page_num + offset + 1}: {str(e)}")
                                continue
                
                logger.info(f"Extracted {len([r for r in self.results if r['qsp_filename'] == qsp_filename])} references from {pdf_path.name}")
                
        except Exception as e:
            logger.error(f"Error processing {pdf_path.name}: {str(e)}")
    
    def process_all_pdfs(self):
        """Process all PDF files in the data folder."""
        pdf_files = list(self.pdf_folder.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning(f"No PDF files found in {self.pdf_folder}")
            return
        
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        for pdf_path in pdf_files:
            self.process_pdf(pdf_path)
    
    def save_results(self):
        """Save extracted results to CSV file."""
        if not self.results:
            logger.warning("No results to save")
            return
        
        df = pd.DataFrame(self.results)
        df.to_csv(self.output_file, index=False, encoding='utf-8-sig')
        logger.info(f"Results saved to {self.output_file}")
        logger.info(f"Total records: {len(df)}")
        logger.info(f"Unique QSP files: {df['qsp_filename'].nunique()}")
    
    def run(self):
        """Run the complete parsing process."""
        logger.info("Starting Annex A Parser")
        logger.info(f"PDF folder: {self.pdf_folder.absolute()}")
        
        self.process_all_pdfs()
        self.save_results()
        
        logger.info("Parsing complete!")


def main():
    """Main entry point."""
    parser = AnnexAParser(pdf_folder="data", output_file="annex_a_references.csv")
    parser.run()


if __name__ == "__main__":
    main()
