#!/usr/bin/env python3
"""
HTML Tag Parser - Extract specific HTML tags from text files

Usage:
    python html_tag_parser.py <input_file> <tag_name> <output_file> [options]
    
Examples:
    # Extract all <a> tags from input.html and save to links.txt
    python html_tag_parser.py input.html a links.txt
    
    # Extract all <p> tags from input.txt and save to paragraphs.txt
    python html_tag_parser.py input.txt p paragraphs.txt
    
    # Extract tags with specific attribute
    python html_tag_parser.py input.html a links.txt --attr href
    
    # Extract only text content (without tags)
    python html_tag_parser.py input.html div output.txt --text-only
    
    # Extract with custom separator
    python html_tag_parser.py input.html span output.txt --separator " | "
"""

import argparse
import sys
import re
from pathlib import Path
from bs4 import BeautifulSoup
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def read_file_content(file_path: str) -> str:
    """
    Read content from a file with UTF-8 encoding.
    
    Args:
        file_path: Path to the input file
        
    Returns:
        File content as string
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path} with any encoding: {e}")
            raise
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        raise


def extract_tags_with_regex(content: str, tag_name: str, include_attrs: bool = False) -> list:
    """
    Extract HTML tags using regex (simple method).
    
    Args:
        content: HTML content as string
        tag_name: Name of the tag to extract (e.g., 'a', 'div', 'p')
        include_attrs: Whether to include tag attributes in the output
        
    Returns:
        List of extracted tag strings
    """
    # Pattern to match opening tags, self-closing tags, and closing tags
    # This pattern captures the entire tag including attributes
    pattern = rf'<{tag_name}[^>]*/?>|</{tag_name}>'
    
    # Find all matches
    matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
    
    if not include_attrs:
        # If not including attributes, just return the tag names
        return [f'<{tag_name}>' if not match.startswith(f'</{tag_name}') else f'</{tag_name}>' 
                for match in matches]
    
    return matches


def extract_tags_with_bs4(content: str, tag_name: str, extract_attr: str = None, 
                          text_only: bool = False, include_tag: bool = False) -> list:
    """
    Extract HTML tags using BeautifulSoup (more robust method).
    
    Args:
        content: HTML content as string
        tag_name: Name of the tag to extract (e.g., 'a', 'div', 'p')
        extract_attr: Specific attribute to extract (e.g., 'href', 'src')
        text_only: Whether to extract only text content (without tags)
        include_tag: Whether to include the tag itself in output
        
    Returns:
        List of extracted content
    """
    try:
        soup = BeautifulSoup(content, 'html.parser')
        tags = soup.find_all(tag_name)
        
        results = []
        
        for tag in tags:
            if extract_attr:
                # Extract specific attribute
                if tag.has_attr(extract_attr):
                    results.append(tag[extract_attr])
            elif text_only:
                # Extract only text content
                text = tag.get_text(strip=True)
                if text:
                    results.append(text)
            elif include_tag:
                # Include the tag itself
                results.append(str(tag))
            else:
                # Default: get string representation
                results.append(str(tag))
        
        return results
    except Exception as e:
        logger.error(f"Error parsing HTML with BeautifulSoup: {e}")
        return []


def save_results(results: list, output_file: str, separator: str = '\n') -> None:
    """
    Save extracted results to a file.
    
    Args:
        results: List of extracted items
        output_file: Path to output file
        separator: Separator between items
    """
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            if separator == '\n':
                # Write each result on a new line
                for result in results:
                    f.write(f"{result}\n")
            else:
                # Join with custom separator
                f.write(separator.join(results))
        
        logger.info(f"Saved {len(results)} items to {output_file}")
        print(f"Successfully saved {len(results)} items to: {output_file}")
        
    except Exception as e:
        logger.error(f"Error saving to {output_file}: {e}")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Extract specific HTML tags from text files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.html a links.txt
  %(prog)s input.txt p paragraphs.txt --text-only
  %(prog)s input.html a links.txt --attr href
  %(prog)s input.html img images.txt --attr src
  %(prog)s input.html div output.txt --include-tag
  %(prog)s input.html span output.txt --separator " | "
  %(prog)s input.html a output.txt --regex
        """
    )
    
    parser.add_argument(
        'input_file',
        help='Path to the input file containing HTML/text content'
    )
    
    parser.add_argument(
        'tag_name',
        help='HTML tag name to extract (e.g., a, div, p, span, img)'
    )
    
    parser.add_argument(
        'output_file',
        help='Path to the output file where extracted content will be saved'
    )
    
    parser.add_argument(
        '--attr',
        dest='extract_attr',
        help='Extract specific attribute instead of tag content (e.g., href, src, class)'
    )
    
    parser.add_argument(
        '--text-only',
        action='store_true',
        help='Extract only text content (without HTML tags)'
    )
    
    parser.add_argument(
        '--include-tag',
        action='store_true',
        help='Include the complete HTML tag in output'
    )
    
    parser.add_argument(
        '--regex',
        action='store_true',
        help='Use regex-based extraction instead of BeautifulSoup (faster but less accurate)'
    )
    
    parser.add_argument(
        '--separator',
        default='\n',
        help='Separator between extracted items in output file (default: newline)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")
    
    # Validate arguments
    if not Path(args.input_file).exists():
        logger.error(f"Input file not found: {args.input_file}")
        sys.exit(1)
    
    # Read input file
    try:
        logger.info(f"Reading input file: {args.input_file}")
        content = read_file_content(args.input_file)
        logger.info(f"Read {len(content)} characters from input file")
    except Exception as e:
        logger.error(f"Failed to read input file: {e}")
        sys.exit(1)
    
    # Extract tags
    if args.regex:
        logger.info(f"Extracting <{args.tag_name}> tags using regex")
        results = extract_tags_with_regex(content, args.tag_name, include_attrs=args.include_tag)
    else:
        logger.info(f"Extracting <{args.tag_name}> tags using BeautifulSoup")
        results = extract_tags_with_bs4(
            content, 
            args.tag_name, 
            extract_attr=args.extract_attr,
            text_only=args.text_only,
            include_tag=args.include_tag
        )
    
    # Check if any results were found
    if not results:
        logger.warning(f"No <{args.tag_name}> tags found in the input file")
        print(f"Warning: No <{args.tag_name}> tags found in {args.input_file}")
    
    # Save results
    try:
        save_results(results, args.output_file, args.separator)
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        sys.exit(1)
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Input file: {args.input_file}")
    print(f"  Tag: <{args.tag_name}>")
    if args.extract_attr:
        print(f"  Extracted attribute: {args.extract_attr}")
    elif args.text_only:
        print(f"  Extracted: Text content only")
    elif args.include_tag:
        print(f"  Extracted: Complete HTML tags")
    else:
        print(f"  Extracted: Tag content")
    print(f"  Method: {'Regex' if args.regex else 'BeautifulSoup'}")
    print(f"  Items found: {len(results)}")
    print(f"  Output file: {args.output_file}")


if __name__ == "__main__":
    main()
