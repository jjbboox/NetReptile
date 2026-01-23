# NetReptile

A command-line tool to fetch complete web page content using Playwright and save it to a file.

## Features

- Fetches complete HTML content including JavaScript-rendered content
- Supports modern websites with dynamic content
- Configurable timeout settings
- Verbose logging option
- Automatic URL validation and correction
- **Container extraction**: Extract text from specific HTML elements using CSS selectors or XPath

## Installation

1. Clone or download this repository
2. Create a virtual environment (recommended):
   ```bash
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Install browser binaries:
   ```bash
   playwright install
   ```

## Usage

Basic usage:
```bash
python netreptile.py <url> <output_file>
```

### Basic Examples:
```bash
# Fetch example.com and save to example.html
python netreptile.py https://example.com example.html

# Fetch with custom timeout (60 seconds)
python netreptile.py https://example.com example.html --timeout 60000

# Enable verbose logging
python netreptile.py https://example.com example.html --verbose

# URL without protocol (will automatically add https://)
python netreptile.py example.com example.html
```

### Container Extraction Examples:
```bash
# Extract text from all elements with class "article-content"
python netreptile.py https://news.example.com news.txt --selector ".article-content"

# Extract text from all div elements with class "post" using XPath
python netreptile.py https://forum.example.com posts.txt --selector "//div[@class='post']" --selector-type xpath

# Extract text from all paragraph elements
python netreptile.py https://blog.example.com blog_content.txt --selector "p"

# Extract text from multiple article containers
python netreptile.py https://magazine.example.com articles.txt --selector ".article" --verbose
```

## Command Line Arguments

- `url`: The URL of the web page to fetch (required)
- `output_file`: Path to the output file where content will be saved (required)
- `--config`: Path to JSON configuration file (can contain timeout, selector, selector_type)
- `--timeout`: Navigation timeout in milliseconds (overrides config file if provided, default: 30000)
- `--selector`: CSS selector or XPath to find specific containers for text extraction (overrides config file if provided, optional)
- `--selector-type`: Type of selector: 'css' or 'xpath' (overrides config file if provided, default: 'css')
- `--verbose`: Enable verbose logging

## Configuration File

You can use a JSON configuration file to specify `timeout`, `selector`, and `selector_type` parameters. Command line arguments override configuration file values.

### Configuration File Format

Create a JSON file with the following structure:

```json
{
    "timeout": 45000,
    "selector": ".article-content",
    "selector_type": "css"
}
```

- `timeout`: Navigation timeout in milliseconds (integer)
- `selector`: CSS selector or XPath string (string)
- `selector_type`: "css" or "xpath" (string, optional, default: "css")

### Examples

**Using configuration file:**
```bash
# Load parameters from config.json
python netreptile.py https://example.com output.html --config config.json

# Load from config.json but override timeout via command line
python netreptile.py https://example.com output.html --config config.json --timeout 60000

# Load from config.json but override selector via command line
python netreptile.py https://example.com output.html --config config.json --selector ".main-content"
```

**Configuration file examples:**

`config_news.json`:
```json
{
    "timeout": 60000,
    "selector": ".article-content",
    "selector_type": "css"
}
```

`config_forum.json`:
```json
{
    "timeout": 30000,
    "selector": "//div[@class='post']",
    "selector_type": "xpath"
}
```

`config_basic.json`:
```json
{
    "timeout": 45000
}
```

### Priority Order

1. Command line arguments (highest priority)
2. Configuration file values
3. Default values (lowest priority)

## How It Works

### Basic Mode (without selector):
1. Launches a headless Chromium browser using Playwright
2. Navigates to the specified URL
3. Waits for the page to fully load (including network idle)
4. Captures the complete HTML content
5. Saves the content to the specified output file

### Container Extraction Mode (with selector):
1. Launches a headless Chromium browser using Playwright
2. Navigates to the specified URL
3. Waits for the page to fully load (including network idle)
4. Finds all elements matching the CSS selector or XPath
5. Extracts text content from each matching element
6. Combines extracted text with separators
7. Saves the extracted text to the specified output file

## HTML Tag Parser

The project now includes an additional tool `html_tag_parser.py` for extracting specific HTML tags from text files.

### Features

- Extract specific HTML tags (e.g., `<a>`, `<div>`, `<p>`, `<img>`) from text/HTML files
- Multiple extraction modes:
  - Extract complete HTML tags
  - Extract only text content (without tags)
  - Extract specific attributes (e.g., `href` from `<a>` tags, `src` from `<img>` tags)
- Support for both BeautifulSoup (accurate) and regex (fast) parsing methods
- Customizable output separator
- UTF-8 encoding support with fallback

### Usage

```bash
python html_tag_parser.py <input_file> <tag_name> <output_file> [options]
```

### Examples

```bash
# Extract all <a> tags from input.html and save to links.txt
python html_tag_parser.py input.html a links.txt

# Extract href attributes from all <a> tags
python html_tag_parser.py input.html a links.txt --attr href

# Extract only text content from <p> tags
python html_tag_parser.py input.txt p paragraphs.txt --text-only

# Extract <img> tags with src attributes
python html_tag_parser.py input.html img images.txt --attr src

# Extract complete <div> tags
python html_tag_parser.py input.html div output.txt --include-tag

# Use regex-based extraction (faster but less accurate)
python html_tag_parser.py input.html a output.txt --regex

# Use custom separator between extracted items
python html_tag_parser.py input.html span output.txt --separator " | "
```

### Command Line Arguments

- `input_file`: Path to the input file containing HTML/text content (required)
- `tag_name`: HTML tag name to extract (e.g., a, div, p, span, img) (required)
- `output_file`: Path to the output file where extracted content will be saved (required)
- `--attr`: Extract specific attribute instead of tag content (e.g., href, src, class)
- `--text-only`: Extract only text content (without HTML tags)
- `--include-tag`: Include the complete HTML tag in output
- `--regex`: Use regex-based extraction instead of BeautifulSoup (faster but less accurate)
- `--separator`: Separator between extracted items in output file (default: newline)
- `--verbose`: Enable verbose logging

## Requirements

- Python 3.7 or higher
- Playwright library
- BeautifulSoup4 library (for html_tag_parser.py)
- Chromium browser (automatically installed by Playwright)

## License

MIT

---

# NetReptile (中文说明)

使用 Playwright 库抓取完整网页内容并保存到文件的命令行工具。

## 功能特点

- 抓取完整的 HTML 内容，包括 JavaScript 渲染的内容
- 支持具有动态内容的现代网站
- 可配置的超时设置
- 详细日志记录选项
- 自动 URL 验证和修正
- **容器提取功能**：使用 CSS 选择器或 XPath 从特定 HTML 元素中提取文本

## 安装

1. 克隆或下载此仓库
2. 创建虚拟环境（推荐）：
   ```bash
   python -m venv .venv
   ```
3. 激活虚拟环境：
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`
4. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
5. 安装浏览器二进制文件：
   ```bash
   playwright install
   ```

## 使用方法

基本用法：
```bash
python netreptile.py <url> <输出文件>
```

### 基础示例：
```bash
# 抓取 example.com 并保存到 example.html
python netreptile.py https://example.com example.html

# 使用自定义超时（60秒）
python netreptile.py https://example.com example.html --timeout 60000

# 启用详细日志记录
python netreptile.py https://example.com example.html --verbose

# 不带协议的 URL（会自动添加 https://）
python netreptile.py example.com example.html
```

### 容器提取示例：
```bash
# 从所有 class 为 "article-content" 的元素中提取文本
python netreptile.py https://news.example.com news.txt --selector ".article-content"

# 使用 XPath 从所有 class 为 "post" 的 div 元素中提取文本
python netreptile.py https://forum.example.com posts.txt --selector "//div[@class='post']" --selector-type xpath

# 从所有段落元素中提取文本
python netreptile.py https://blog.example.com blog_content.txt --selector "p"

# 从多个文章容器中提取文本（启用详细日志）
python netreptile.py https://magazine.example.com articles.txt --selector ".article" --verbose
```

## 命令行参数

- `url`: 要抓取的网页 URL（必需）
- `output_file`: 保存内容的输出文件路径（必需）
- `--config`: JSON 配置文件路径（可包含 timeout、selector、selector_type）
- `--timeout`: 导航超时（毫秒，覆盖配置文件中的设置，默认：30000）
- `--selector`: CSS 选择器或 XPath，用于查找要提取文本的特定容器（覆盖配置文件中的设置，可选）
- `--selector-type`: 选择器类型：'css' 或 'xpath'（覆盖配置文件中的设置，默认：'css'）
- `--verbose`: 启用详细日志记录

## 工作原理

### 基础模式（不使用选择器）：
1. 使用 Playwright 启动无头 Chromium 浏览器
2. 导航到指定的 URL
3. 等待页面完全加载（包括网络空闲）
4. 捕获完整的 HTML 内容
5. 将内容保存到指定的输出文件

### 容器提取模式（使用选择器）：
1. 使用 Playwright 启动无头 Chromium 浏览器
2. 导航到指定的 URL
3. 等待页面完全加载（包括网络空闲）
4. 查找所有匹配 CSS 选择器或 XPath 的元素
5. 从每个匹配元素中提取文本内容
6. 使用分隔符组合提取的文本
7. 将提取的文本保存到指定的输出文件

## HTML 标签解析器

项目现在包含一个额外的工具 `html_tag_parser.py`，用于从文本文件中提取特定的 HTML 标签。

### 功能特点

- 从文本/HTML 文件中提取特定的 HTML 标签（例如 `<a>`、`<div>`、`<p>`、`<img>`）
- 多种提取模式：
  - 提取完整的 HTML 标签
  - 仅提取文本内容（不含标签）
  - 提取特定属性（例如从 `<a>` 标签提取 `href`，从 `<img>` 标签提取 `src`）
- 支持 BeautifulSoup（准确）和正则表达式（快速）两种解析方法
- 可自定义的输出分隔符
- 支持 UTF-8 编码，并提供回退机制

### 使用方法

```bash
python html_tag_parser.py <输入文件> <标签名> <输出文件> [选项]
```

### 示例

```bash
# 从 input.html 中提取所有 <a> 标签并保存到 links.txt
python html_tag_parser.py input.html a links.txt

# 从所有 <a> 标签中提取 href 属性
python html_tag_parser.py input.html a links.txt --attr href

# 仅从 <p> 标签中提取文本内容
python html_tag_parser.py input.txt p paragraphs.txt --text-only

# 提取带有 src 属性的 <img> 标签
python html_tag_parser.py input.html img images.txt --attr src

# 提取完整的 <div> 标签
python html_tag_parser.py input.html div output.txt --include-tag

# 使用基于正则表达式的提取（更快但准确性较低）
python html_tag_parser.py input.html a output.txt --regex

# 使用自定义分隔符分隔提取的项目
python html_tag_parser.py input.html span output.txt --separator " | "
```

### 命令行参数

- `input_file`: 包含 HTML/文本内容的输入文件路径（必需）
- `tag_name`: 要提取的 HTML 标签名称（例如 a、div、p、span、img）（必需）
- `output_file`: 保存提取内容的输出文件路径（必需）
- `--attr`: 提取特定属性而不是标签内容（例如 href、src、class）
- `--text-only`: 仅提取文本内容（不含 HTML 标签）
- `--include-tag`: 在输出中包含完整的 HTML 标签
- `--regex`: 使用基于正则表达式的提取而不是 BeautifulSoup（更快但准确性较低）
- `--separator`: 输出文件中提取项目之间的分隔符（默认：换行符）
- `--verbose`: 启用详细日志记录

## 系统要求

- Python 3.7 或更高版本
- Playwright 库
- BeautifulSoup4 库（用于 html_tag_parser.py）
- Chromium 浏览器（由 Playwright 自动安装）

## 许可证

MIT
