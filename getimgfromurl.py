#!/usr/bin/env python3
"""
Get Images from URL - Download all images from <img> tags within <pre> tags on a webpage

Usage:
    python getimgfromurl.py <url> <output_dir> [options]
    
Examples:
    # Download all images from <pre> tags on a webpage to specified directory
    python getimgfromurl.py https://example.com ./output
    
    # Download images with custom timeout
    python getimgfromurl.py https://example.com ./output --timeout 30000
    
    # Use specific user agent
    python getimgfromurl.py https://example.com ./output --user-agent "Custom Agent"
    
    # Specify image file extension
    python getimgfromurl.py https://example.com ./output --ext png
    
    # Use proxy
    python getimgfromurl.py https://example.com ./output --proxy http://proxy.example.com:8080
"""

import argparse
import sys
import os
import re
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse
import asyncio
import random
from typing import List, Optional
from playwright.async_api import async_playwright
import aiofiles

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_browser_context(p, url: str, timeout: int = 30000, user_agent: str = None, proxy: str = None):
    """
    Create browser context and navigate to URL using Playwright.
    
    Args:
        p: Playwright instance
        url: The URL to fetch
        timeout: Maximum navigation timeout in milliseconds
        user_agent: Custom user agent string
        proxy: Proxy URL (optional)
        
    Returns:
        Tuple of (browser, context, page, html_content)
    """
    # Launch browser (Chromium by default)
    launch_options = {'headless': True}
    
    if proxy:
        launch_options['proxy'] = {'server': proxy}
    
    browser = await p.chromium.launch(**launch_options)
    
    # Enhanced browser context options to avoid bot detection
    context_options = {
        'viewport': {'width': 1920, 'height': 1080},
        'locale': 'zh-CN',
        'timezone_id': 'Asia/Shanghai',
        'geolocation': {'latitude': 31.2304, 'longitude': 121.4737},
        'permissions': ['geolocation'],
        'color_scheme': 'light',
        'reduced_motion': 'reduce',
        'extra_http_headers': {
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    }
    
    if user_agent:
        context_options['user_agent'] = user_agent
    else:
        context_options['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    
    try:
        logger.info(f"Navigating to {url}")
        try:
            await page.goto(url, wait_until='networkidle', timeout=timeout)
        except Exception as e:
            logger.warning(f"Navigation timeout occurred: {e}")
            logger.info("Stopping page loading and continuing with already loaded content...")
            # Stop page loading
            await page.evaluate("window.stop()")
        
        # Wait for any dynamic content to load
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            logger.info("Continuing with current page state...")
        
        # Get the complete HTML content
        content = await page.content()
        logger.info(f"Successfully fetched HTML content from {url}")
        
        return browser, context, page, content
        
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        # Clean up on error
        await page.close()
        await context.close()
        await browser.close()
        raise


def extract_img_urls_from_pre_tags(html_content: str, base_url: str) -> List[str]:
    """
    Extract all image URLs from <img> tags within <pre> tags.
    
    Args:
        html_content: HTML content as string
        base_url: Base URL for resolving relative image URLs
        
    Returns:
        List of image URLs
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("BeautifulSoup4 is required. Install with: pip install beautifulsoup4")
        sys.exit(1)
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all <pre> tags
    pre_tags = soup.find_all('pre')
    
    if not pre_tags:
        logger.warning("No <pre> tags found on the page")
        return []
    
    logger.info(f"Found {len(pre_tags)} <pre> tags on the page")
    
    # Extract all <img> tags within <pre> tags
    img_urls = []
    for i, pre_tag in enumerate(pre_tags, 1):
        img_tags = pre_tag.find_all('img')
        
        if img_tags:
            logger.info(f"Found {len(img_tags)} <img> tags in <pre> tag #{i}")
            
            for img_tag in img_tags:
                if img_tag.has_attr('src'):
                    img_url = img_tag['src']
                    
                    # Resolve relative URLs
                    if not img_url.startswith(('http://', 'https://', 'data:')):
                        img_url = urljoin(base_url, img_url)
                    
                    # Skip data URLs
                    if img_url.startswith('data:'):
                        logger.debug(f"Skipping data URL image")
                        continue
                    
                    img_urls.append(img_url)
                    logger.debug(f"Found image URL: {img_url}")
    
    logger.info(f"Total image URLs found: {len(img_urls)}")
    return img_urls


async def wait_for_pre_images_loaded(page, timeout: int = 30000) -> bool:
    """
    Wait for all <img> tags within <pre> tags to load.
    
    Args:
        page: Playwright page object
        timeout: Maximum wait time in milliseconds
        
    Returns:
        True if images loaded successfully, False otherwise
    """
    try:
        logger.info("Waiting for images in <pre> tags to load...")
        
        # Wait for at least one <pre> tag to be present
        await page.wait_for_selector('pre', timeout=timeout)
        
        # Wait for images within <pre> tags to load
        # We'll use a JavaScript approach to check image loading status
        js_code = """
        () => {
            // Find all <img> tags within <pre> tags
            const preTags = document.querySelectorAll('pre');
            const allImages = [];
            
            for (const pre of preTags) {
                const images = pre.querySelectorAll('img');
                for (const img of images) {
                    allImages.push(img);
                }
            }
            
            // Check if all images are loaded
            if (allImages.length === 0) {
                return {count: 0, loaded: 0, allLoaded: true};
            }
            
            let loadedCount = 0;
            for (const img of allImages) {
                if (img.complete && img.naturalWidth > 0) {
                    loadedCount++;
                }
            }
            
            return {
                count: allImages.length,
                loaded: loadedCount,
                allLoaded: loadedCount === allImages.length
            };
        }
        """
        
        # Wait for images to load with timeout
        start_time = asyncio.get_event_loop().time()
        while True:
            result = await page.evaluate(js_code)
            
            if result['allLoaded'] or result['count'] == 0:
                logger.info(f"Images loaded: {result['loaded']}/{result['count']}")
                return True
            
            # Check timeout
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            if elapsed > timeout:
                logger.warning(f"Timeout waiting for images to load. Loaded: {result['loaded']}/{result['count']}")
                return False
            
            # Wait a bit before checking again
            await asyncio.sleep(0.5)
            
    except Exception as e:
        logger.warning(f"Error waiting for images to load: {e}")
        return False


def determine_file_extension(url: str, default_ext: str = 'jpg') -> str:
    """
    Determine file extension from URL or use default.
    
    Args:
        url: Image URL
        default_ext: Default extension if cannot determine from URL
        
    Returns:
        File extension (without dot)
    """
    # Try to extract extension from URL
    parsed_url = urlparse(url)
    path = parsed_url.path
    
    if '.' in path:
        ext = path.split('.')[-1].lower()
        # Remove query parameters if any
        ext = ext.split('?')[0]
        
        # Common image extensions
        valid_extensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico']
        
        if ext in valid_extensions:
            # Normalize jpeg to jpg
            if ext == 'jpeg':
                return 'jpg'
            return ext
    
    # Use default extension
    return default_ext


def format_filename(index: int, total: int, extension: str) -> str:
    """
    Format filename with leading zeros based on total count.
    
    Args:
        index: Image index (1-based)
        total: Total number of images
        extension: File extension
        
    Returns:
        Formatted filename
    """
    # Calculate number of digits needed
    # Use at least 2 digits for better readability (01, 02, etc.)
    digits = max(2, len(str(total)))
    
    # Format with leading zeros
    formatted_index = str(index).zfill(digits)
    
    return f"{formatted_index}.{extension}"


def read_list_file(list_file_path: str) -> List[tuple]:
    """
    Read list file for batch processing.
    Supports multiple formats:
    1. CSV format with quotes (e.g., "url","output_dir")
    2. Space/tab separated format (e.g., url output_dir)
    3. Single URL per line (for backward compatibility with netreptile.py format)
    
    Args:
        list_file_path: Path to the list file
        
    Returns:
        List of tuples (url, output_dir)
    """
    tasks = []
    
    try:
        with open(list_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Check if line contains an <a href> tag (like netreptile.py)
                # This needs to be handled first because HTML tags can contain quotes
                if '<a href=' in line.lower() or '<a href =' in line.lower():
                    # Try to extract URL from href attribute
                    import re
                    match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
                    if match:
                        extracted_url = match.group(1)
                        logger.debug(f"Line {line_num}: Extracted URL from <a href> tag: {extracted_url}")
                        
                        # Now we need to extract the output directory
                        # The output directory is typically after the HTML tag
                        # Remove the HTML tag part and get what's after it
                        tag_pattern = r'<a\s+href\s*=\s*["\'][^"\']+["\'][^>]*>.*?</a>'
                        line_without_tag = re.sub(tag_pattern, '', line, flags=re.IGNORECASE).strip()
                        
                        if line_without_tag:
                            # Output directory is what remains after removing the tag
                            output_dir = line_without_tag
                        else:
                            # If nothing remains, try to find output directory in the line
                            # Look for non-HTML parts
                            parts = re.split(r'\s+', line)
                            # Find the first part that doesn't look like HTML
                            for part in parts:
                                if not ('<' in part or '>' in part or 'href=' in part.lower()):
                                    output_dir = part
                                    break
                            else:
                                logger.warning(f"Line {line_num}: Could not find output directory in HTML tag line: {line}")
                                continue
                        
                        tasks.append((extracted_url, output_dir))
                        continue
                    else:
                        logger.warning(f"Line {line_num}: Could not extract URL from <a href> tag: {line}")
                        continue
                
                # Try to parse as CSV format first (with quotes)
                import csv
                import io
                
                # Check if line contains quoted fields (CSV format)
                if '"' in line or "'" in line:
                    try:
                        # Use csv.reader to parse the line
                        reader = csv.reader(io.StringIO(line))
                        parts = next(reader)
                        
                        if len(parts) >= 2:
                            # CSV format: first column is URL, second is output directory
                            url = parts[0].strip()
                            output_dir = parts[1].strip()
                            
                            # Remove surrounding quotes if present (including different quote types)
                            # Define all possible quote characters - including various Unicode quotes
                            left_quotes = ['"', "'", '“', '‘', '「', '『', '〈', '《', '【', '〔']
                            right_quotes = ['"', "'", '”', '’', '」', '』', '〉', '》', '】', '〕']
                            
                            # Also check for UTF-8 RIGHT DOUBLE QUOTATION MARK (U+201D)
                            # Add more Unicode quote characters
                            import unicodedata
                            
                            # Helper function to check if a character is some kind of quote
                            def is_quote_char(char):
                                if not char:
                                    return False
                                # Check common quote characters
                                if char in left_quotes or char in right_quotes:
                                    return True
                                # Check Unicode category
                                try:
                                    category = unicodedata.category(char)
                                    # Punctuation categories that might include quotes
                                    if category.startswith('P'):
                                        # Check common quote-like punctuation
                                        if char in '"\'':
                                            return True
                                        # Check if it looks like a quote
                                        name = unicodedata.name(char, '').upper()
                                        if 'QUOTATION' in name or 'QUOTE' in name or 'APOSTROPHE' in name:
                                            return True
                                except:
                                    pass
                                return False
                            
                            # Remove quotes from URL
                            if url and is_quote_char(url[0]) and is_quote_char(url[-1]):
                                url = url[1:-1]
                            
                            # Remove quotes from output directory
                            if output_dir and is_quote_char(output_dir[0]) and is_quote_char(output_dir[-1]):
                                output_dir = output_dir[1:-1]
                            
                            tasks.append((url, output_dir))
                            continue
                    except Exception as csv_error:
                        logger.debug(f"Line {line_num}: Failed to parse as CSV: {csv_error}, trying other formats")
                
                # Try space/tab separated format
                parts = line.split()
                
                if len(parts) >= 2:
                    # Space/tab separated format
                    url = parts[0]
                    output_dir = parts[1]
                    
                    tasks.append((url, output_dir))
                    continue
                
                # If we reach here, the line doesn't have enough parts
                logger.warning(f"Line {line_num}: insufficient columns (expected at least 2, got {len(parts)}): {line}")
        
        if not tasks:
            logger.error(f"No valid tasks found in list file: {list_file_path}")
            return []
        
        # Process URLs: validate and add https:// if needed
        processed_tasks = []
        for url, output_dir in tasks:
            # Validate URL format
            if not url.startswith(('http://', 'https://')):
                logger.warning(f"URL doesn't start with http:// or https://: {url}")
                # Try to add https:// if missing
                url = f"https://{url}"
                logger.info(f"Trying with: {url}")
            
            processed_tasks.append((url, output_dir))
        
        logger.info(f"Loaded {len(processed_tasks)} tasks from list file: {list_file_path}")
        return processed_tasks
        
    except FileNotFoundError:
        logger.error(f"List file not found: {list_file_path}")
        return []
    except Exception as e:
        logger.error(f"Error reading list file {list_file_path}: {e}")
        return []


async def extract_images_only(page, output_dir: Path, default_ext: str = 'jpg') -> dict:
    """
    Extract images from <pre> tags and save directly to output directory.
    
    Args:
        page: Playwright page object with loaded page
        output_dir: Directory where images will be saved
        default_ext: Default file extension for images
        
    Returns:
        Dictionary with extraction statistics
    """
    try:
        logger.info(f"Extracting images to: {output_dir}")
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all images in <pre> tags
        js_code = """
        () => {
            const preTags = document.querySelectorAll('pre');
            const images = [];
            
            for (const pre of preTags) {
                const imgElements = pre.querySelectorAll('img');
                for (const img of imgElements) {
                    // Skip data URLs
                    if (!img.src || img.src.startsWith('data:')) {
                        continue;
                    }
                    
                    // Get image information
                    images.push({
                        src: img.src,
                        currentSrc: img.currentSrc || img.src,
                        alt: img.alt || '',
                        width: img.naturalWidth || img.width || 0,
                        height: img.naturalHeight || img.height || 0
                    });
                }
            }
            
            return images;
        }
        """
        
        # Execute JavaScript to get image information
        images_info = await page.evaluate(js_code)
        
        if not images_info:
            logger.warning("No images found in <pre> tags")
            return {'total': 0, 'success': 0, 'failed': 0}
        
        logger.info(f"Found {len(images_info)} images in <pre> tags")
        
        successful_extractions = 0
        failed_extractions = 0
        
        # Download each image and save directly to output directory
        for i, img_info in enumerate(images_info, 1):
            try:
                # Determine file extension from URL
                ext = determine_file_extension(img_info['src'], default_ext)
                
                # Format filename for output
                output_filename = format_filename(i, len(images_info), ext)
                output_filepath = output_dir / output_filename
                
                # Add small delay to avoid rate limiting
                if i > 1:
                    await asyncio.sleep(0.5)
                
                # Download image using page.request.get()
                try:
                    response = await page.request.get(img_info['src'])
                    
                    if response.ok:
                        # Get the response body
                        image_data = await response.body()
                        
                        # Save to output directory
                        async with aiofiles.open(output_filepath, 'wb') as f:
                            await f.write(image_data)
                        
                        successful_extractions += 1
                        print(f"[{i}/{len(images_info)}] Extracted: {img_info['src']}")
                        print(f"     Saved to: {output_filepath.name}")
                    else:
                        logger.warning(f"Failed to download {img_info['src']}: HTTP {response.status}")
                        failed_extractions += 1
                        print(f"[{i}/{len(images_info)}] Failed: HTTP {response.status} - {img_info['src']}")
                        
                except Exception as e:
                    logger.warning(f"Error downloading image {i}: {e}")
                    failed_extractions += 1
                    print(f"[{i}/{len(images_info)}] Error: {img_info['src']} - {e}")
                    
            except Exception as e:
                failed_extractions += 1
                logger.error(f"Error processing image {i}: {e}")
                print(f"[{i}/{len(images_info)}] Error: {img_info['src']} - {e}")
        
        logger.info(f"Images extracted to: {output_dir}")
        
        return {
            'total': len(images_info),
            'success': successful_extractions,
            'failed': failed_extractions
        }
        
    except Exception as e:
        logger.error(f"Error in extract_images_only: {e}")
        return {'total': 0, 'success': 0, 'failed': 0}


async def process_single_task(url: str, output_dir: str, timeout: int, user_agent: str, 
                             proxy: str, ext: str, verbose: bool) -> dict:
    """
    Process a single URL task.
    
    Args:
        url: URL to process
        output_dir: Output directory for images
        timeout: Navigation timeout in milliseconds
        user_agent: Custom user agent string
        proxy: Proxy URL
        ext: Default file extension
        verbose: Verbose logging flag
        
    Returns:
        Dictionary with task statistics
    """
    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"URL doesn't start with http:// or https://: {url}")
        # Try to add https:// if missing
        url = f"https://{url}"
        logger.info(f"Trying with: {url}")
    
    # Create output directory path
    output_dir_path = Path(output_dir)
    
    playwright_instance = None
    browser = None
    context = None
    page = None
    
    try:
        # Create Playwright instance
        playwright_instance = await async_playwright().start()
        
        # Step 1: Create browser context and navigate to URL
        logger.info(f"Creating browser context and navigating to {url}")
        browser, context, page, html_content = await create_browser_context(
            playwright_instance,
            url, 
            timeout=timeout,
            user_agent=user_agent,
            proxy=proxy
        )
        
        # Step 2: Wait for images in <pre> tags to load
        logger.info("Waiting for images in <pre> tags to load...")
        images_loaded = await wait_for_pre_images_loaded(page, timeout=timeout)
        
        if not images_loaded:
            logger.warning("Images may not have fully loaded, but will try to save what's available")
        
        # Step 3: Extract images only (no page saving)
        logger.info("Extracting images...")
        stats = await extract_images_only(
            page,
            output_dir_path,
            default_ext=ext
        )
        
        if stats['total'] == 0:
            # Fallback: try to extract URLs from HTML
            logger.warning("No images extracted, falling back to HTML extraction...")
            img_urls = extract_img_urls_from_pre_tags(html_content, url)
            
            if img_urls:
                logger.info(f"Found {len(img_urls)} image URLs in HTML")
                print(f"Found {len(img_urls)} image URLs but could not extract them")
                print("Image URLs found:")
                for i, url_item in enumerate(img_urls, 1):
                    print(f"  {i}. {url_item}")
            else:
                logger.error("No images found in <pre> tags on the page")
                print("No images found in <pre> tags on the page")
            
            stats['has_fallback_urls'] = bool(img_urls)
            stats['fallback_urls'] = img_urls
        
        # Add URL and output directory to stats
        stats['url'] = url
        stats['output_dir'] = str(output_dir_path.absolute())
        
        return stats
        
    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        raise
    finally:
        # Clean up browser resources
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()


async def process_batch_tasks(tasks: List[tuple], timeout: int, user_agent: str, 
                             proxy: str, ext: str, verbose: bool) -> List[dict]:
    """
    Process multiple tasks in sequence.
    
    Args:
        tasks: List of tuples (url, output_dir)
        timeout: Navigation timeout in milliseconds
        user_agent: Custom user agent string
        proxy: Proxy URL
        ext: Default file extension
        verbose: Verbose logging flag
        
    Returns:
        List of task statistics dictionaries
    """
    all_stats = []
    
    print("\n" + "="*60)
    print("BATCH PROCESSING STARTED")
    print("="*60)
    print(f"Total tasks: {len(tasks)}")
    print("="*60)
    
    for i, (url, output_dir) in enumerate(tasks, 1):
        print(f"\n{'='*40}")
        print(f"Processing task {i}/{len(tasks)}")
        print(f"URL: {url}")
        print(f"Output directory: {output_dir}")
        print(f"{'='*40}\n")
        
        try:
            stats = await process_single_task(
                url=url,
                output_dir=output_dir,
                timeout=timeout,
                user_agent=user_agent,
                proxy=proxy,
                ext=ext,
                verbose=verbose
            )
            
            all_stats.append(stats)
            
            # Print task summary
            print(f"\nTask {i} completed:")
            print(f"  URL: {url}")
            print(f"  Output directory: {output_dir}")
            print(f"  Images found: {stats.get('total', 0)}")
            print(f"  Successfully extracted: {stats.get('success', 0)}")
            print(f"  Failed extractions: {stats.get('failed', 0)}")
            if stats.get('total', 0) > 0:
                print(f"  Success rate: {stats.get('success', 0)/stats.get('total', 0)*100:.1f}%")
            
            # Add delay between tasks to avoid rate limiting
            if i < len(tasks):
                print(f"\nWaiting 2 seconds before next task...")
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Failed to process task {i} ({url}): {e}")
            print(f"\nTask {i} failed: {e}")
            all_stats.append({
                'url': url,
                'output_dir': output_dir,
                'error': str(e),
                'total': 0,
                'success': 0,
                'failed': 0
            })
    
    return all_stats


async def main_async(args):
    """Main async function."""
    # Check if we're in batch mode or single mode
    if args.list_file:
        # Batch mode
        tasks = read_list_file(args.list_file)
        
        if not tasks:
            logger.error("No valid tasks found in list file. Exiting.")
            return
        
        # Process all tasks
        all_stats = await process_batch_tasks(
            tasks=tasks,
            timeout=args.timeout,
            user_agent=args.user_agent,
            proxy=args.proxy,
            ext=args.ext,
            verbose=args.verbose
        )
        
        # Print batch summary
        print("\n" + "="*60)
        print("BATCH PROCESSING SUMMARY")
        print("="*60)
        
        total_tasks = len(all_stats)
        successful_tasks = sum(1 for stats in all_stats if stats.get('success', 0) > 0 or stats.get('has_fallback_urls', False))
        failed_tasks = total_tasks - successful_tasks
        
        total_images = sum(stats.get('total', 0) for stats in all_stats)
        total_success = sum(stats.get('success', 0) for stats in all_stats)
        total_failed = sum(stats.get('failed', 0) for stats in all_stats)
        
        print(f"Total tasks processed: {total_tasks}")
        print(f"Successful tasks: {successful_tasks}")
        print(f"Failed tasks: {failed_tasks}")
        print(f"Total images found: {total_images}")
        print(f"Total successfully extracted: {total_success}")
        print(f"Total failed extractions: {total_failed}")
        
        if total_images > 0:
            print(f"Overall success rate: {total_success/total_images*100:.1f}%")
        
        print("\nTask details:")
        for i, stats in enumerate(all_stats, 1):
            if 'error' in stats:
                print(f"  {i}. {stats['url']} - ERROR: {stats['error']}")
            elif stats.get('has_fallback_urls', False):
                print(f"  {i}. {stats['url']} - Found {len(stats.get('fallback_urls', []))} URLs (not extracted)")
            else:
                print(f"  {i}. {stats['url']} - {stats.get('success', 0)}/{stats.get('total', 0)} images extracted")
        
        print("="*60)
        
    else:
        # Single mode
        if not args.url or not args.output_dir:
            logger.error("Both URL and output_dir are required in single mode")
            print("Error: Both URL and output_dir are required in single mode")
            print("Usage: python getimgfromurl.py <url> <output_dir> [options]")
            return
        
        stats = await process_single_task(
            url=args.url,
            output_dir=args.output_dir,
            timeout=args.timeout,
            user_agent=args.user_agent,
            proxy=args.proxy,
            ext=args.ext,
            verbose=args.verbose
        )
        
        # Print summary for single task
        if stats.get('total', 0) == 0 and not stats.get('has_fallback_urls', False):
            return
        
        print("\n" + "="*60)
        print("IMAGE EXTRACTION SUMMARY")
        print("="*60)
        print(f"URL: {stats['url']}")
        print(f"Images saved to: {stats['output_dir']}")
        print(f"Total images found: {stats.get('total', 0)}")
        print(f"Successfully extracted: {stats.get('success', 0)}")
        print(f"Failed extractions: {stats.get('failed', 0)}")
        if stats.get('total', 0) > 0:
            print(f"Success rate: {stats.get('success', 0)/stats.get('total', 0)*100:.1f}%")
        
        if stats.get('success', 0) > 0:
            print(f"\nImages saved with filenames:")
            # List saved files
            output_dir_path = Path(stats['output_dir'])
            for i in range(1, stats.get('success', 0) + 1):
                filename = format_filename(i, stats.get('total', 0), args.ext)
                filepath = output_dir_path / filename
                if filepath.exists():
                    print(f"  {filename} ({filepath.stat().st_size:,} bytes)")
        
        print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Download all images from <img> tags within <pre> tags on a webpage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Single URL mode
  %(prog)s https://example.com ./output
  %(prog)s https://example.com ./output --timeout 30000
  %(prog)s https://example.com ./output --user-agent "Custom Agent"
  %(prog)s https://example.com ./output --ext png
  %(prog)s https://example.com ./output --proxy http://proxy.example.com:8080
  %(prog)s https://example.com ./output --verbose
  
  # Batch mode with list file
  %(prog)s --list urls.txt
        """
    )
    
    # Mutually exclusive group for single URL vs batch mode
    group = parser.add_mutually_exclusive_group(required=True)
    
    group.add_argument(
        'url',
        nargs='?',
        help='URL of the web page to fetch images from (single mode)'
    )
    
    group.add_argument(
        '--list',
        dest='list_file',
        help='List file for batch processing (each line: URL output_dir)'
    )
    
    parser.add_argument(
        'output_dir',
        nargs='?',
        help='Directory where images will be saved (single mode)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=30000,
        help='Navigation and download timeout in milliseconds (default: 30000)'
    )
    
    parser.add_argument(
        '--user-agent',
        help='Custom user agent string'
    )
    
    parser.add_argument(
        '--ext',
        default='jpg',
        help='Default file extension for images (default: jpg)'
    )
    
    parser.add_argument(
        '--proxy',
        help='Proxy URL (e.g., http://proxy.example.com:8080)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle Windows-specific asyncio issues
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        # Run the main async function
        asyncio.run(main_async(args))
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
