"""
Selector Processor Module

This module provides functions for processing complex selector configurations
with support for nested selectors, exclusions, and custom separators.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


async def process_selector_config(page, selector_config: Dict[str, Any], parent_element=None) -> List[str]:
    """
    Process a single selector configuration and return extracted texts.
    
    Args:
        page: Playwright page object
        selector_config: Selector configuration dictionary
        parent_element: Optional parent element to search within
        
    Returns:
        List of extracted text strings
    """
    selector = selector_config.get('selector')
    selector_type = selector_config.get('selector_type', 'css')
    separator = selector_config.get('separator', '\n')
    exclusions = selector_config.get('Exclusions', [])
    exclusions = selector_config.get('exclusions', exclusions)  # Support both capital and lowercase
    nested_selectors = selector_config.get('selectors', [])
    replace_rules = selector_config.get('replace', [])
    
    if not selector:
        logger.warning(f"Missing selector in config: {selector_config}")
        return []
    
    logger.debug(f"Processing selector: {selector} (type: {selector_type})")
    
    # Find elements based on selector type
    if selector_type == 'css':
        if parent_element:
            elements = await parent_element.query_selector_all(selector)
        else:
            elements = await page.query_selector_all(selector)
    elif selector_type == 'xpath':
        if parent_element:
            elements = await parent_element.query_selector_all(f'xpath={selector}')
        else:
            elements = await page.query_selector_all(f'xpath={selector}')
    else:
        logger.warning(f"Unsupported selector type: {selector_type}, skipping")
        return []
    
    if not elements:
        logger.debug(f"No elements found matching selector: {selector}")
        return []
    
    # Process each element
    all_extracted_texts = []
    
    for i, element in enumerate(elements):
        try:
            # Apply exclusions if specified
            if exclusions:
                # Create a copy of the element to work with
                element_copy = element
                # Remove excluded elements
                for exclusion in exclusions:
                    if exclusion.startswith('.'):
                        # CSS class exclusion
                        excluded_elements = await element_copy.query_selector_all(exclusion)
                    else:
                        # Tag name exclusion
                        excluded_elements = await element_copy.query_selector_all(exclusion)
                    
                    for excluded in excluded_elements:
                        try:
                            await excluded.evaluate("node => node.remove()")
                        except Exception as e:
                            logger.debug(f"Failed to remove excluded element: {e}")
            
            # Process nested selectors if specified
            if nested_selectors:
                nested_texts = []
                for nested_config in nested_selectors:
                    # Recursively process nested selectors
                    nested_results = await process_selector_config(page, nested_config, element)
                    nested_texts.extend(nested_results)
                
                if nested_texts:
                    # Join nested texts with their separator
                    nested_content = separator.join(nested_texts)
                    all_extracted_texts.append(nested_content)
            else:
                # Extract text directly from the element
                # Use inner_text() instead of text_content() to preserve line breaks from <br> tags
                text = await element.inner_text()
                if text and text.strip():
                    all_extracted_texts.append(text.strip())
                    
        except Exception as e:
            logger.warning(f"Failed to process element {i+1}: {e}")
    
    # Apply replace rules if specified
    if replace_rules and all_extracted_texts:
        logger.debug(f"Applying {len(replace_rules)} replace rules")
        for i, text in enumerate(all_extracted_texts):
            for replace_rule in replace_rules:
                target_tag = replace_rule.get('target_tag')
                replace_str = replace_rule.get('replace_str')
                
                if target_tag and replace_str is not None:
                    # Create regex pattern to match HTML tags
                    # This will match both opening and closing tags
                    # Also handle self-closing tags like <br/>
                    pattern = rf'<{target_tag}[^>]*/?>|</{target_tag}>'
                    import re
                    # Replace all occurrences of the tag with replace_str
                    new_text = re.sub(pattern, replace_str, text)
                    if new_text != text:
                        logger.debug(f"Replaced {target_tag} tags with '{replace_str}' in text {i+1}")
                        text = new_text
            
            all_extracted_texts[i] = text
    
    return all_extracted_texts


async def process_selectors(page, selectors: List[Dict[str, Any]]) -> str:
    """
    Process multiple selector configurations and return combined text.
    
    Args:
        page: Playwright page object
        selectors: List of selector configurations
        
    Returns:
        Combined text from all selectors
    """
    if not selectors:
        return ""
    
    all_results = []
    
    for selector_config in selectors:
        try:
            results = await process_selector_config(page, selector_config)
            if results:
                # Get separator for this selector configuration
                separator = selector_config.get('separator', '\n')
                # Join results for this selector with its separator
                selector_content = separator.join(results)
                # If separator is not the default and we have content, append the separator
                # This ensures that separators like "\n\n" are added after the content
                if separator != '\n' and selector_content:
                    selector_content += separator
                all_results.append(selector_content)
        except Exception as e:
            logger.error(f"Failed to process selector config {selector_config}: {e}")
    
    if not all_results:
        return ""
    
    # Join all selector results with newline
    return "\n".join(all_results)
