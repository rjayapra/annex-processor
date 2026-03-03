"""
Annex A PDF Parser
Extracts reference tables from Annex A sections in PDF files.
"""

import csv
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
    
    CSV_FIELDNAMES = ['qsp_filename', 'reference_number', 'ndid_document_control_no', 'title_of_reference']

    def __init__(self, pdf_folder: str = "data", output_file: str = "annex_a_references.csv"):
        self.pdf_folder = Path(pdf_folder)
        self.output_file = output_file
        self.results = []
        self._csv_file = None
        self._csv_writer = None

    def _init_csv(self):
        """Open the CSV file and write the header row."""
        self._csv_file = open(self.output_file, 'w', newline='', encoding='utf-8-sig')
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=self.CSV_FIELDNAMES)
        self._csv_writer.writeheader()

    def _write_row(self, row: Dict):
        """Write a single parsed row to the CSV file immediately."""
        if self._csv_writer is None:
            self._init_csv()
        self._csv_writer.writerow(row)
        self._csv_file.flush()

    def _close_csv(self):
        """Close the CSV file handle."""
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
        
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
    
    def parse_references_from_text(self, text: str, qsp_filename: str) -> List[Dict]:
        """
        Fallback parser: extract references from raw page text when no
        structured table is found.  Handles lines like:
            A1  A-AD-121-C01/FP-000 - Staff and Writing Procedures ...
        Multi-line entries (continuation lines without a ref code) are
        appended to the previous entry.
        """
        results = []
        if not text:
            return results

        lines = text.split('\n')

        # Regex for a reference line: starts with a ref code like A1, B12, C3, D1, etc.
        ref_line_re = re.compile(
            r'^\s*([A-D]\d{1,3})\s+(.+)',  # e.g.  A1  <rest of line>
        )

        current_ref = None
        current_text = ""

        # Lines to skip
        skip_re = re.compile(
            r'^(ANNEX|QSP|Ref\b|Code\b|Chapters?\s|A\s*=|B\s*=|C\s*=|D\s*=|A\s*-\s*\d|Qty|Required)',
            re.IGNORECASE,
        )

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            m = ref_line_re.match(stripped)
            if m:
                # Save previous entry
                if current_ref and current_text:
                    ndid, title = self.extract_ndid_from_title(current_text.strip())
                    results.append({
                        'qsp_filename': qsp_filename,
                        'reference_number': current_ref,
                        'ndid_document_control_no': ndid or '',
                        'title_of_reference': title,
                    })
                current_ref = m.group(1)
                current_text = m.group(2)
            elif current_ref and not skip_re.match(stripped):
                # Continuation line for the current reference
                current_text += ' ' + stripped

        # Flush last entry
        if current_ref and current_text:
            ndid, title = self.extract_ndid_from_title(current_text.strip())
            results.append({
                'qsp_filename': qsp_filename,
                'reference_number': current_ref,
                'ndid_document_control_no': ndid or '',
                'title_of_reference': title,
            })

        return results

    def is_annex_a_heading_page(self, text: str) -> bool:
        """
        Return True only when the page contains a real ANNEX A heading
        (not merely a Table-of-Contents line that mentions it).
        TOC lines typically include dot leaders (…, .) or page numbers.
        """
        if not text:
            return False
        for line in text.split('\n'):
            line_stripped = line.strip().upper()
            # Accept the heading itself (possibly with dash or en-dash)
            if re.match(r'^ANNEX\s+A\s*[–\-]\s*MAIN\s+REFERENCE', line_stripped):
                # Reject TOC entries: they contain dot-leaders or trailing page refs
                if '…' in line or '.....' in line or re.search(r'[A-Z]\s*-\s*\d+\s*$', line.strip()):
                    continue
                return True
        return False

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
                if ('ANNEX A' in text_upper and 'MAIN REFERENCE' in text_upper
                        and self.is_annex_a_heading_page(text)):
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
                    found_table = False
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
                                    
                                    found_table = True
                                    logger.info(f"Found reference table on page {page_num + offset + 1}")
                                    for row in table:
                                        parsed_row = self.parse_table_row(row, qsp_filename)
                                        if parsed_row:
                                            self.results.append(parsed_row)
                                            self._write_row(parsed_row)
                                            logger.debug(f"Extracted: {parsed_row}")
                            except Exception as e:
                                logger.warning(f"Error extracting tables from page {page_num + offset + 1}: {str(e)}")
                                continue

                    # Fallback: parse references from raw text when no
                    # structured table was found on the Annex A page(s)
                    if not found_table:
                        logger.info(f"No structured table found for Annex A on page {page_num + 1}; using text-based extraction")
                        for offset in range(3):
                            if page_num + offset < len(pdf.pages):
                                page_text = pdf.pages[page_num + offset].extract_text() or ''
                                text_refs = self.parse_references_from_text(page_text, qsp_filename)
                                for parsed_row in text_refs:
                                    self.results.append(parsed_row)
                                    self._write_row(parsed_row)
                                    logger.debug(f"Extracted (text): {parsed_row}")
                                if text_refs:
                                    found_table = True  # prevent duplicate extraction
                
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
        """Finalize the CSV file and log a summary."""
        self._close_csv()

        if not self.results:
            logger.warning("No results to save")
            return

        df = pd.DataFrame(self.results)
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
