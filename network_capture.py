import sys
import time
import json
import csv
import os
import tempfile
import smtplib
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# SMTP server configuration
# SMTP_SERVER = "10.1.1.1"
# SMTP_PORT = 25

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

GMAIL_EMAIL = "double.m.admiin@gmail.com"  # Replace with your Gmail
GMAIL_PASSWORD = "trti mnkl prpn ltaw" 

# Email configuration
FROM_EMAIL = "double.m.admiin@gmail.com"
TO_EMAIL = "abdelrahman.ata@orange.com"
SUBJECT_PREFIX = "Images Report"

def setup_driver():
    """Setup Chrome driver with DevTools Protocol enabled"""
    # Specify the path to ChromeDriver
    chromedriver_path = r"C:\ChromeDriverExact\chromedriver-win32\chromedriver-win32\chromedriver.exe"
    
    # Check if ChromeDriver exists at the specified path
    if not os.path.exists(chromedriver_path):
        raise FileNotFoundError(f"ChromeDriver not found at: {chromedriver_path}")
    
    chrome_options = Options()
    
    # Add these lines to specify a unique user data directory
    temp_dir = tempfile.mkdtemp()
    chrome_options.add_argument(f"--user-data-dir={temp_dir}")
    
    # Enable DevTools Protocol
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Enable logging for network requests
    chrome_options.add_experimental_option('perfLoggingPrefs', {
        'enableNetwork': True,
        'enablePage': False,
    })
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    # Create service object with the ChromeDriver path
    service = Service(chromedriver_path)
    
    return webdriver.Chrome(service=service, options=chrome_options)

def is_valid_image_url(url):
    """Check if URL is a valid image URL (including base64 data: URLs)"""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Allow data:image/ URLs (base64 encoded images)
    if url_lower.startswith('data:image/'):
        return True
    
    # Filter out other invalid URLs
    invalid_prefixes = [
        'data:',           # Other data URLs (not images)
        'chrome://',       # Chrome internal URLs
        'chrome-extension://',  # Chrome extension URLs
        'moz-extension://',     # Firefox extension URLs
        'about:',          # Browser internal pages
        'javascript:',     # JavaScript URLs
        'blob:',           # Blob URLs (though some might be valid)
    ]
    
    # Check for data: URLs that are NOT images
    if url_lower.startswith('data:') and not url_lower.startswith('data:image/'):
        return False
    
    # Filter out other invalid prefixes
    for prefix in invalid_prefixes:
        if url_lower.startswith(prefix):
            return False
    
    # Must be HTTP/HTTPS or data:image/
    if not (url_lower.startswith('http://') or url_lower.startswith('https://') or url_lower.startswith('data:image/')):
        return False
    
    return True

def is_same_domain_url(image_url, target_url):
    """Check if image URL belongs to the same domain as target URL"""
    try:
        # Base64 data URLs are considered same-domain (embedded in the page)
        if image_url.lower().startswith('data:image/'):
            return True
            
        image_parsed = urlparse(image_url)
        target_parsed = urlparse(target_url)
        
        # Get domains without www prefix
        image_domain = image_parsed.netloc.lower()
        target_domain = target_parsed.netloc.lower()
        
        # Remove www. prefix for comparison
        if image_domain.startswith('www.'):
            image_domain = image_domain[4:]
        if target_domain.startswith('www.'):
            target_domain = target_domain[4:]
        
        # Check if domains match or if image domain is a subdomain of target
        return (image_domain == target_domain or 
                image_domain.endswith('.' + target_domain) or
                target_domain.endswith('.' + image_domain))
        
    except Exception:
        return False

def filter_same_domain_images(image_data, target_url):
    """Filter images to only include those from the same domain as target URL"""
    filtered_images = []
    removed_count = 0
    removed_domains = set()
    
    for img in image_data:
        if is_same_domain_url(img['url'], target_url):
            filtered_images.append(img)
        else:
            removed_count += 1
            try:
                removed_domain = urlparse(img['url']).netloc.lower()
                if removed_domain.startswith('www.'):
                    removed_domain = removed_domain[4:]
                removed_domains.add(removed_domain)
            except:
                pass
    
    if removed_count > 0:
        print(f"✓ Filtered out {removed_count} external domain images:")
        for domain in sorted(removed_domains):
            print(f"  - {domain}")
    
    return filtered_images

def format_file_size(size_bytes):
    """Format file size exactly like DevTools does"""
    if size_bytes == 0:
        return "0 B"
    elif size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def parse_size_to_bytes(size_str):
    """Convert size string back to bytes for calculations"""
    if size_str == "(unknown)" or not size_str:
        return 0
    
    size_str = size_str.upper().replace(' ', '')
    
    if 'KB' in size_str:
        return int(float(size_str.replace('KB', '')) * 1024)
    elif 'MB' in size_str:
        return int(float(size_str.replace('MB', '')) * 1024 * 1024)
    elif 'GB' in size_str:
        return int(float(size_str.replace('GB', '')) * 1024 * 1024 * 1024)
    elif 'B' in size_str:
        return int(size_str.replace('B', ''))
    else:
        return 0

def get_extension_from_mime_type(mime_type):
    """Extract extension from MIME type"""
    if not mime_type:
        return 'unknown'
    
    mime_type_lower = mime_type.lower()
    
    if 'jpeg' in mime_type_lower or mime_type_lower == 'image/jpg':
        return 'jpg'
    elif 'png' in mime_type_lower:
        return 'png'
    elif 'gif' in mime_type_lower:
        return 'gif'
    elif 'webp' in mime_type_lower:
        return 'webp'
    elif 'svg' in mime_type_lower:
        return 'svg'
    elif 'bmp' in mime_type_lower:
        return 'bmp'
    elif 'ico' in mime_type_lower or 'icon' in mime_type_lower:
        return 'ico'
    elif 'avif' in mime_type_lower:
        return 'avif'
    else:
        return 'unknown'

def get_base64_image_info(data_url):
    """Extract information from base64 data:image/ URL"""
    try:
        # Parse data URL: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...
        if not data_url.lower().startswith('data:image/'):
            return None, 0, 'unknown'
        
        # Split into header and data parts
        header, data = data_url.split(',', 1) if ',' in data_url else (data_url, '')
        
        # Extract MIME type from header: data:image/png;base64
        mime_part = header.split(';')[0].replace('data:', '')  # image/png
        
        # Get extension from MIME type
        extension = get_extension_from_mime_type(mime_part)
        
        # Calculate size from base64 data
        if data:
            # Remove any whitespace
            clean_data = data.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            # Base64 encoding: every 4 characters represent 3 bytes, minus padding
            padding = clean_data.count('=')
            size_bytes = (len(clean_data) * 3 // 4) - padding
        else:
            size_bytes = 0
        
        return mime_part, size_bytes, extension
        
    except Exception:
        return None, 0, 'unknown'

def format_data_url_for_display(data_url, max_length=50):
    """Format data URL for display in tables"""
    if not data_url.lower().startswith('data:image/'):
        return data_url
    
    # Show format: data:image/png;base64,[50 chars]...
    try:
        header, data = data_url.split(',', 1) if ',' in data_url else (data_url, '')
        if data:
            preview_data = data[:max_length] + '...' if len(data) > max_length else data
            return f"{header},{preview_data}"
        return header
    except:
        return data_url[:100] + '...' if len(data_url) > 100 else data_url

def get_extension_from_url(url):
    """Extract extension from URL or filename"""
    url_lower = url.lower()
    
    # Common image extensions
    extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif']
    
    for ext in extensions:
        if f'.{ext}' in url_lower:
            if ext == 'jpeg':
                return 'jpg'  # Normalize jpeg to jpg
            return ext
    
    return 'unknown'

def extract_all_network_data(driver, url):
    """Extract ALL network data first, then filter for images"""
    print(f"Opening URL: {url}")
    
    # Enable network domain in DevTools Protocol
    driver.execute_cdp_cmd('Network.enable', {})
    driver.execute_cdp_cmd('Page.enable', {})
    
    # Navigate to the URL
    driver.get(url)
    
    # Wait for page to load and network requests to complete
    print("Loading page and capturing ALL network requests...")
    time.sleep(8)
    
    # Scroll to trigger lazy-loaded content
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(2)
    
    # Get network logs (exact same data DevTools Network tab uses)
    logs = driver.get_log('performance')
    
    # Process ALL network data first
    requests = {}
    all_network_data = []
    
    for log in logs:
        try:
            message = json.loads(log['message'])
            method = message['message']['method']
            
            if method == 'Network.requestWillBeSent':
                params = message['message']['params']
                request_id = params['requestId']
                request = params['request']
                
                requests[request_id] = {
                    'url': request['url'],
                    'method': request.get('method', 'GET'),
                    'resourceType': None,
                    'mimeType': '',
                    'size': 0,
                    'transferSize': 0,
                    'status': None
                }
                
            elif method == 'Network.responseReceived':
                params = message['message']['params']
                request_id = params['requestId']
                response = params['response']
                
                if request_id in requests:
                    mime_type = response.get('mimeType')
                    # Handle None values properly
                    if mime_type is None:
                        mime_type = ''
                    
                    requests[request_id].update({
                        'mimeType': mime_type,
                        'status': response.get('status'),
                        'headers': response.get('headers', {})
                    })
                    
                    # Get content length from headers
                    headers = response.get('headers', {})
                    content_length = headers.get('content-length') or headers.get('Content-Length')
                    if content_length:
                        try:
                            requests[request_id]['size'] = int(content_length)
                        except:
                            pass
                            
            elif method == 'Network.loadingFinished':
                params = message['message']['params']
                request_id = params['requestId']
                
                if request_id in requests:
                    # Use encodedDataLength (same as DevTools "Size" column)
                    encoded_length = params.get('encodedDataLength', 0)
                    if encoded_length > 0:
                        requests[request_id]['transferSize'] = encoded_length
                        if requests[request_id]['size'] == 0:
                            requests[request_id]['size'] = encoded_length
                            
        except (json.JSONDecodeError, KeyError):
            continue
    
    # Convert all requests to list format
    for request_id, request_data in requests.items():
        url_path = request_data['url']
        
        # Extract filename
        filename = url_path.split('/')[-1].split('?')[0].split('#')[0]
        if not filename:
            filename = url_path.split('/')[-1][:50] if url_path.split('/')[-1] else 'unknown'
        
        # Format size
        size = request_data.get('size', 0) or request_data.get('transferSize', 0)
        if size > 0:
            size_display = format_file_size(size)
        else:
            size_display = "(unknown)"
        
        # Get MIME type - handle None properly
        mime_type = request_data.get('mimeType', '')
        if mime_type is None:
            mime_type = ''
        
        all_network_data.append({
            'name': filename,
            'size': size_display,
            'size_bytes': size,
            'type': mime_type,
            'url': url_path,
            'status': request_data.get('status', 'Unknown')
        })
    
    print(f"Captured {len(all_network_data)} total network requests")
    
    # Now filter for images only
    image_data = filter_images_from_data(all_network_data)
    
    return all_network_data, image_data

def filter_images_from_data(all_data):
    """Filter image requests from all network data"""
    image_data = []
    
    for item in all_data:
        url_path = item['url']
        mime_type = item['type']
        filename = item['name']
        
        # FIRST: Check if URL is valid (now includes data:image/ URLs)
        if not is_valid_image_url(url_path):
            continue
        
        # Handle base64 data:image/ URLs specially
        if url_path.lower().startswith('data:image/'):
            mime_type_from_url, size_bytes, extension = get_base64_image_info(url_path)
            
            if mime_type_from_url:
                # Create a descriptive filename for base64 images
                base64_filename = f"base64_image_{len(image_data) + 1}.{extension}"
                
                image_data.append({
                    'name': base64_filename,
                    'size': format_file_size(size_bytes) if size_bytes > 0 else "(unknown)",
                    'size_bytes': size_bytes,
                    'type': extension,
                    'url': url_path,
                    'status': 200,  # Embedded images are considered successfully loaded
                    'contentType': mime_type_from_url,
                    'success': True
                })
            continue
        
        # Handle regular HTTP/HTTPS URLs
        # Safely handle mime_type
        if mime_type is None:
            mime_type = ''
        
        mime_type_lower = mime_type.lower()
        url_lower = url_path.lower()
        filename_lower = filename.lower()
        
        # Image detection (multiple methods)
        is_image = (
            # Method 1: MIME type
            mime_type_lower.startswith('image/') or
            # Method 2: File extension in URL
            any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico', '.avif']) or
            # Method 3: File extension in filename
            any(ext in filename_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico', '.avif'])
        )
        
        if is_image:
            # Get extension - try MIME type first, then URL
            extension = get_extension_from_mime_type(mime_type)
            if extension == 'unknown':
                extension = get_extension_from_url(url_path)
            
            image_data.append({
                'name': item['name'],
                'size': item['size'],
                'size_bytes': item['size_bytes'],
                'type': extension,  # Now just the extension
                'url': item['url'],
                'status': item['status'],
                'contentType': mime_type,
                'success': item['status'] == 200 if item.get('status') else False
            })
    
    print(f"Filtered {len(image_data)} valid image requests from all data")
    return image_data

def extract_site_name(url):
    """Extract clean site name from URL"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Remove www. prefix
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Replace dots and special characters with underscores
    site_name = domain.replace('.', '_').replace('-', '_')
    
    # Remove any remaining special characters
    site_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in site_name)
    
    return site_name

def generate_filename(url, extension):
    """Generate filename with site name and current date in temp directory"""
    site_name = extract_site_name(url)
    current_date = datetime.now().strftime("%Y_%m_%d")
    filename = f"{site_name}_{current_date}_report.{extension}"
    
    # Use temp directory
    temp_dir = tempfile.gettempdir()
    full_path = os.path.join(temp_dir, filename)
    
    return full_path

def calculate_statistics(image_data):
    """Calculate statistics for the images"""
    total_bytes = sum(img['size_bytes'] for img in image_data)
    total_mb = total_bytes / (1024 * 1024)
    total_kb = total_bytes / 1024
    
    # Count image formats by extension
    format_counts = Counter()
    for img in image_data:
        extension = img['type'].upper()  # Convert to uppercase for display
        if extension == 'JPG':
            format_counts['JPEG'] += 1  # Display as JPEG for familiarity
        else:
            format_counts[extension] += 1
    
    # Count images over 500KB
    large_images = sum(1 for img in image_data if img['size_bytes'] >= 500 * 1024)
    
    return {
        'total_bytes': total_bytes,
        'total_mb': total_mb,
        'total_kb': total_kb,
        'format_counts': format_counts,
        'large_images': large_images
    }

def save_enhanced_csv(image_data, url, generation_time):
    """Save to CSV with summary on top and table underneath"""
    current_time = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
    stats = calculate_statistics(image_data)
    
    # Generate filename with site name and date in temp directory
    csv_filepath = generate_filename(url, 'csv')
    
    with open(csv_filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # === SUMMARY SECTION ===
        writer.writerow(['=== WEBSITE IMAGE ANALYSIS REPORT ==='])
        writer.writerow([])  # Empty row
        writer.writerow(['Website:', url])
        writer.writerow(['Date:', current_time])
        writer.writerow(['Time to Generate:', f'{generation_time:.2f} seconds'])
        writer.writerow(['Valid Images:', len(image_data)])
        writer.writerow(['Total Size:', f'{stats["total_mb"]:.2f} MB ({stats["total_kb"]:.2f} KB)'])
        writer.writerow([])  # Empty row
        
        # Format statistics
        writer.writerow(['=== Image Format Statistics ==='])
        total_images = len(image_data)
        for fmt, count in stats['format_counts'].most_common():
            percentage = (count / total_images * 100) if total_images > 0 else 0
            writer.writerow([f'{fmt}:', f'{count} ({percentage:.1f}%)'])
        writer.writerow([])  # Empty row
        writer.writerow([])  # Extra empty row before table
        
        # === TABLE SECTION ===
        writer.writerow(['=== DETAILED IMAGE LIST ==='])
        writer.writerow([])  # Empty row
        
        # Table header
        writer.writerow(['Name', 'Size', 'Type', 'URL'])
        
        # Image data
        for img in image_data:
            writer.writerow([img['name'], img['size'], img['type'], img['url']])
    
    print(f"✓ CSV report saved to: {csv_filepath}")
    return csv_filepath

def generate_html_report(image_data, url, generation_time):
    """Generate an enhanced HTML report with styling and statistics"""
    current_date = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
    stats = calculate_statistics(image_data)
    
    # Prepare the data for HTML
    valid_results = [img for img in image_data if img.get('success', False)]
    sorted_results = sorted(valid_results, key=lambda x: x['size_bytes'], reverse=True)
    
    # Calculate additional stats for HTML
    type_stats = {}
    for img in image_data:
        ext = img['type'].upper()
        if ext == 'JPG':
            ext = 'JPEG'
        type_stats[ext] = type_stats.get(ext, 0) + 1
    
    # Extract website display name
    parsed_url = urlparse(url)
    website_display_name = parsed_url.netloc
    
    # Prepare HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Image Analysis Report - {website_display_name}</title>
    <style>
        :root {{
            --primary-color: #2b6cb0;
            --primary-light: #4299e1;
            --secondary-color: #cbd5e0;
            --dark-color: #2d3748;
            --light-color: #f7fafc;
            --danger-color: #e53e3e;
            --success-color: #38a169;
            --warning-color: #ecc94b;
            --orange-color: #ff8c00;
            --border-radius: 8px;
            --box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            --transition: all 0.3s ease;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.7;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 0;
            background-color: #f9fafb;
        }}

        .container {{
            padding: 20px;
        }}

        h1, h2, h3 {{
            color: var(--dark-color);
            margin-bottom: 1rem;
        }}

        h1 {{
            font-size: 2.2rem;
            border-bottom: 3px solid var(--primary-color);
            padding-bottom: 10px;
            display: inline-block;
        }}

        h2 {{
            font-size: 1.8rem;
            position: relative;
        }}

        h2::after {{
            content: '';
            display: block;
            width: 50px;
            height: 4px;
            background: var(--primary-light);
            margin-top: 8px;
        }}

        .report-header {{
            background: linear-gradient(135deg, var(--primary-color), var(--primary-light));
            color: white;
            padding: 30px;
            border-radius: var(--border-radius);
            margin-bottom: 30px;
            box-shadow: var(--box-shadow);
            position: relative;
            overflow: hidden;
        }}

        .report-header::before {{
            content: '';
            position: absolute;
            top: -20px;
            right: -20px;
            width: 150px;
            height: 150px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 50%;
        }}

        .otools-link {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255, 255, 255, 0.2);
            padding: 10px 20px;
            border-radius: 25px;
            text-decoration: none;
            color: white;
            font-weight: bold;
            font-size: 0.9rem;
            transition: var(--transition);
            border: 2px solid rgba(255, 255, 255, 0.3);
            z-index: 10;
        }}

        .otools-link:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
            transform: translateY(-2px);
        }}

        .otools-link::before {{
            content: '🔗';
            margin-right: 8px;
        }}

        .report-header h1 {{
            color: white;
            border-bottom: 3px solid rgba(255, 255, 255, 0.5);
            margin-bottom: 15px;
        }}

        .report-header p {{
            margin-bottom: 10px;
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .report-header strong {{
            opacity: 1;
        }}

        .website-link {{
            color: #fcac4a;
            text-decoration: underline;
            transition: var(--transition);
            font-weight: bold;
        }}

        .website-link:hover {{
            color: #ff6a00;
        }}

        .red-highlight {{
            color: #dc2626 !important;
            font-weight: bold;
        }}

        .stats-container {{
            background-color: white;
            padding: 25px;
            border-radius: var(--border-radius);
            margin-bottom: 30px;
            box-shadow: var(--box-shadow);
        }}

        .stats-title {{
            margin-bottom: 15px;
            font-size: 1.3rem;
            color: var(--primary-color);
        }}

        .summary-items {{
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            margin-bottom: 30px;
        }}

        .summary-item {{
            flex: 1;
            min-width: 200px;
            padding: 15px;
            margin: 10px;
            background-color: var(--light-color);
            border-radius: var(--border-radius);
            border-left: 4px solid var(--primary-color);
            text-align: center;
        }}

        .summary-item strong {{
            display: block;
            font-size: 2rem;
            color: var(--primary-color);
            margin-bottom: 5px;
        }}

        .summary-item.danger strong {{
            color: #dc2626;
        }}

        .summary-item span {{
            color: var(--dark-color);
            font-size: 1.1rem;
        }}

        .stats-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .stats-item {{
            background-color: var(--light-color);
            padding: 15px;
            border-radius: var(--border-radius);
            min-width: 160px;
            flex-grow: 1;
            text-align: center;
            border-bottom: 3px solid var(--primary-light);
        }}

        .stats-item strong {{
            display: block;
            font-size: 1.5rem;
            color: var(--primary-color);
        }}

        .stats-item span {{
            font-size: 0.9rem;
            color: var(--dark-color);
        }}

        .table-container {{
            background-color: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: var(--box-shadow);
            overflow-x: auto;
        }}

        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 0 auto;
            font-size: 0.9rem;
            table-layout: fixed;
        }}

        th, td {{
            text-align: left;
            padding: 12px 15px;
            border-bottom: 1px solid #ddd;
            height: 70px;
            vertical-align: middle;
            overflow: hidden;
        }}

        th {{
            background-color: var(--primary-color);
            color: white;
            position: sticky;
            top: 0;
            font-weight: 600;
            height: auto;
        }}

        .url-cell {{
            width: 35%;
            max-width: 35%;
            word-break: break-all;
            font-size: 0.85rem;
            position: relative;
        }}

        .url-truncated {{
            display: block;
            width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-decoration: none;
            color: var(--primary-color);
            transition: var(--transition);
            position: relative;
        }}

        .url-truncated:hover {{
            color: var(--primary-light);
            text-decoration: underline;
        }}

        .url-truncated::after {{
            content: '...';
            position: absolute;
            right: 0;
            background: linear-gradient(to right, transparent, #fff 70%);
            padding-left: 20px;
            width: 30px;
        }}

        tr:nth-child(even) .url-truncated::after {{
            background: linear-gradient(to right, transparent, #f8f9fa 70%);
        }}

        tr:hover .url-truncated::after {{
            background: linear-gradient(to right, transparent, #ebf8ff 70%);
        }}

        .base64-link {{
            color: var(--primary-color);
            text-decoration: none;
            font-family: monospace;
            font-size: 0.8rem;
            padding: 4px 8px;
            background-color: #f1f5f9;
            border-radius: 4px;
            border: 1px solid #e2e8f0;
            transition: var(--transition);
            display: inline-block;
        }}

        .base64-link:hover {{
            background-color: #e2e8f0;
            color: var(--primary-light);
            text-decoration: underline;
        }}

        /* Highlighting for large images (500KB and above) - Changed to RED */
        .highlighted-row {{
            background-color: #fee2e2 !important;
            border-left: 4px solid #dc2626 !important;
        }}

        .highlighted-row .url-truncated::after {{
            background: linear-gradient(to right, transparent, #fef2f2 70%) !important;
        }}

        .highlighted-row:hover .url-truncated::after {{
            background: linear-gradient(to right, transparent, #fee2e2 70%) !important;
        }}

        .filename-cell {{ width: 15%; max-width: 15%; word-break: break-all; }}
        .preview-cell {{ width: 8%; text-align: center; }}
        .location-cell {{ width: 12%; }}
        .position-cell {{ width: 10%; font-size: 0.8rem; }}
        .size-cell {{ width: 8%; text-align: right; }}
        .type-cell {{ width: 8%; text-align: center; }}
        .content-type-cell {{ width: 12%; text-align: center; }}
        .status-cell {{ width: 8%; text-align: center; }}

        .image-link {{
            color: var(--primary-color);
            text-decoration: none;
            transition: var(--transition);
            display: block;
            width: 100%;
            white-space: nowrap;
            overflow: hidden;
        }}

        .image-link:hover {{
            color: var(--primary-light);
            text-decoration: underline;
        }}

        .image-preview {{
            width: 50px;
            height: 50px;
            object-fit: contain;
            border: 2px solid #ddd;
            border-radius: 4px;
            transition: transform 0.3s ease;
        }}

        .image-preview:hover {{
            transform: scale(2);
            z-index: 1000;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }}

        .status-success {{ 
            color: var(--success-color); 
            font-weight: bold; 
        }}
        
        .status-error {{ 
            color: var(--danger-color); 
            font-weight: bold; 
        }}

        .footer {{
            font-size: 0.9rem;
            color: #6c757d;
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            border-top: 1px solid #dee2e6;
            background-color: white;
            border-radius: var(--border-radius);
        }}

        @media only screen and (max-width: 768px) {{
            .summary-items {{
                flex-direction: column;
            }}
            
            .summary-item {{
                margin: 5px 0;
                min-width: 100%;
            }}
            
            .table-container {{
                padding: 15px 10px;
            }}
            
            th, td {{
                padding: 10px;
            }}
            
            .report-header {{
                padding: 20px;
            }}

            .otools-link {{
                position: static;
                display: block;
                margin-bottom: 15px;
                text-align: center;
            }}

            .image-preview {{
                width: 40px;
                height: 40px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="report-header">
            <a href="https://otools.net" target="_blank" class="otools-link">Visit OTools</a>
            <h1>Enhanced Image Analysis Report</h1>
            <p><strong>Website:</strong> <a href="{url}" class="website-link" target="_blank">{website_display_name}</a></p>
            <p><strong>Analysis Date:</strong> {current_date}</p>
            <p><strong>Tool:</strong> Selenium Network Capture</p>
            <p><strong>Highlighting:</strong> Images <span class="red-highlight">≥ 500 KB</span> are highlighted in red</p>
        </div>

        <h2>Image Statistics</h2>
        <div class="stats-container">
            <div class="summary-items">
                <div class="summary-item">
                    <strong>{len(valid_results)}</strong>
                    <span>Valid Images Found</span>
                </div>
                <div class="summary-item">
                    <strong>{stats['total_kb']:.1f} KB</strong>
                    <span>Total Size</span>
                </div>
                <div class="summary-item {'danger' if stats['large_images'] > 0 else ''}">
                    <strong>{stats['large_images']}</strong>
                    <span>Images <span class="red-highlight">&gt; 500KB</span></span>
                </div>
            </div>

            <div class="stats-title">Distribution by Image Format</div>
            <div class="stats-grid">
                {''.join([
                    f'''
                    <div class="stats-item">
                        <strong>{count}</strong>
                        <span>{fmt} ({(count / len(valid_results) * 100):.1f}%)</span>
                    </div>
                    '''
                    for fmt, count in type_stats.items() if count > 0
                ])}
            </div>
        </div>

        <h2>Image Results (Sorted by Size)</h2>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width: 5%;">#</th>
                        <th class="preview-cell">Preview</th>
                        <th class="filename-cell">Filename</th>
                        <th class="type-cell">Type</th>
                        <th class="content-type-cell">Content Type</th>
                        <th class="size-cell">Size (KB)</th>
                        <th class="status-cell">Status</th>
                        <th class="url-cell">URL</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join([
                        f'''
                        <tr class="{'highlighted-row' if img['size_bytes'] >= 500 * 1024 else ''}">
                            <td style="width: 5%; text-align: center;">{idx + 1}</td>
                            <td class="preview-cell">
                                <img src="{img['url']}" class="image-preview" alt="Preview" onerror="this.style.display='none'">
                            </td>
                            <td class="filename-cell">{img['name']}</td>
                            <td class="type-cell">{img['type'].upper()}</td>
                            <td class="content-type-cell">{img['contentType'] or 'Unknown'}</td>
                            <td class="size-cell">{img['size_bytes'] / 1024:.1f}</td>
                            <td class="status-cell {'status-success' if img['success'] else 'status-error'}">
                                {img['status']}
                            </td>
                            <td class="url-cell">
                                {'<a href="#" class="base64-link" onclick="showBase64Content(this); return false;" data-url="' + img["url"] + '">[Base64 Embedded Image - Click to View]</a>' if img['url'].lower().startswith('data:image/') else f'<a href="{img["url"]}" class="url-truncated" target="_blank" title="{img["url"]}">{img["url"][:60] + "..." if len(img["url"]) > 60 else img["url"]}</a>'}
            </td>
                        </tr>
                        '''
                        for idx, img in enumerate(sorted_results)
                    ])}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function showBase64Content(element) {{
            const base64Url = element.getAttribute('data-url');
            
            // Create a new window to display the base64 image
            const newWindow = window.open('', '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
            
            if (newWindow) {{
                newWindow.document.write(`
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Base64 Image Viewer</title>
                        <style>
                            body {{
                                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                                margin: 20px;
                                background-color: #f5f5f5;
                            }}
                            .container {{
                                max-width: 100%;
                                background: white;
                                padding: 20px;
                                border-radius: 8px;
                                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                            }}
                            .image-container {{
                                text-align: center;
                                margin: 20px 0;
                            }}
                            img {{
                                max-width: 100%;
                                max-height: 70vh;
                                border: 1px solid #ddd;
                                border-radius: 4px;
                            }}
                            .url-container {{
                                background: #f8f9fa;
                                padding: 15px;
                                border-radius: 4px;
                                margin: 20px 0;
                                word-break: break-all;
                                font-family: monospace;
                                font-size: 12px;
                                max-height: 200px;
                                overflow-y: auto;
                            }}
                            .copy-btn {{
                                background: #007bff;
                                color: white;
                                border: none;
                                padding: 8px 16px;
                                border-radius: 4px;
                                cursor: pointer;
                                margin: 10px 0;
                            }}
                            .copy-btn:hover {{
                                background: #0056b3;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h2>Base64 Embedded Image</h2>
                            <div class="image-container">
                                <img src="${{base64Url}}" alt="Base64 Image" onerror="this.style.display='none'; document.getElementById('error-msg').style.display='block';">
                                <div id="error-msg" style="display:none; color: red;">Error loading image</div>
                            </div>
                            <h3>Base64 Data URL:</h3>
                            <button class="copy-btn" onclick="copyToClipboard()">Copy URL to Clipboard</button>
                            <div class="url-container" id="url-content">${{base64Url}}</div>
                        </div>
                        <script>
                            function copyToClipboard() {{
                                const urlContent = document.getElementById('url-content').textContent;
                                navigator.clipboard.writeText(urlContent).then(function() {{
                                    alert('URL copied to clipboard!');
                                }}).catch(function() {{
                                    // Fallback for older browsers
                                    const textArea = document.createElement('textarea');
                                    textArea.value = urlContent;
                                    document.body.appendChild(textArea);
                                    textArea.select();
                                    document.execCommand('copy');
                                    document.body.removeChild(textArea);
                                    alert('URL copied to clipboard!');
                                }});
                            }}
                        </script>
                    </body>
                    </html>
                `);
                newWindow.document.close();
            }} else {{
                alert('Please allow pop-ups to view the base64 image content.');
            }}
        }}
    </script>
</body>
</html>"""
    
    # Save the HTML file
    html_filepath = generate_filename(url, 'html')
    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ HTML report saved to: {html_filepath}")
    return html_filepath

# def send_email_report(attachments, url, stats, generation_time, report_type):
#     """Send email with report attachments"""
#     try:
#         # Create message
#         msg = MIMEMultipart()
#         msg['From'] = FROM_EMAIL
#         msg['To'] = TO_EMAIL
#         msg['Subject'] = f"{SUBJECT_PREFIX} - {extract_site_name(url).replace('_', '.')}"
        
#         # Email body - REMOVED Generation Time and Website lines
#         current_time = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
#         parsed_url = urlparse(url)
#         website_display_name = parsed_url.netloc
        
#         body_text = f"""
# Image Analysis Report Generated

# Domain: {website_display_name}
# Analysis Date: {current_time}
# Report Type: {report_type.upper()}

# === Summary ===
# Valid Images Found: {len(stats.get('image_data', []))}
# Total Size: {stats['total_mb']:.2f} MB ({stats['total_kb']:.2f} KB)
# Images > 500KB: {stats['large_images']}

# === Format Distribution ===
# """
#         for fmt, count in stats['format_counts'].most_common():
#             total_images = len(stats.get('image_data', []))
#             percentage = (count / total_images * 100) if total_images > 0 else 0
#             body_text += f"{fmt}: {count} ({percentage:.1f}%)\n"
        
#         body_text += f"""
# Please find the {report_type.upper()} report(s) attached.

# """
        
#         msg.attach(MIMEText(body_text, 'plain'))
        
#         # Add attachments
#         for attachment_path in attachments:
#             if os.path.exists(attachment_path):
#                 with open(attachment_path, "rb") as attachment:
#                     part = MIMEBase('application', 'octet-stream')
#                     part.set_payload(attachment.read())
                
#                 encoders.encode_base64(part)
                
#                 filename = os.path.basename(attachment_path)
#                 part.add_header(
#                     'Content-Disposition',
#                     f'attachment; filename= {filename}'
#                 )
                
#                 msg.attach(part)
#                 print(f"✓ Attached: {filename}")
#             else:
#                 print(f"✗ Attachment not found: {attachment_path}")
        
#         # Send email
#         print(f"Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
#         server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        
#         # Send the email
#         text = msg.as_string()
#         server.sendmail(FROM_EMAIL, TO_EMAIL, text)
#         server.quit()
        
#         print(f"✓ Email sent successfully to {TO_EMAIL}")
#         return True
        
#     except Exception as e:
#         print(f"✗ Email sending failed: {str(e)}")
#         return False


def send_email_report(attachments, url, stats, generation_time, report_type):
    """Send email with report attachments using Gmail"""
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = GMAIL_EMAIL
        msg['To'] = TO_EMAIL
        msg['Subject'] = f"{SUBJECT_PREFIX} - {extract_site_name(url).replace('_', '.')}"
        
        # Email body
        current_time = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
        parsed_url = urlparse(url)
        website_display_name = parsed_url.netloc
        
        body_text = f"""
Image Analysis Report Generated

Domain: {website_display_name}
Analysis Date: {current_time}
Report Type: {report_type.upper()}

=== Summary ===
Valid Images Found: {len(stats.get('image_data', []))}
Total Size: {stats['total_mb']:.2f} MB ({stats['total_kb']:.2f} KB)
Images > 500KB: {stats['large_images']}

=== Format Distribution ===
"""
        for fmt, count in stats['format_counts'].most_common():
            total_images = len(stats.get('image_data', []))
            percentage = (count / total_images * 100) if total_images > 0 else 0
            body_text += f"{fmt}: {count} ({percentage:.1f}%)\n"
        
        body_text += f"""
Please find the {report_type.upper()} report(s) attached.

"""
        
        msg.attach(MIMEText(body_text, 'plain'))
        
        # Add attachments
        for attachment_path in attachments:
            if os.path.exists(attachment_path):
                with open(attachment_path, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                
                encoders.encode_base64(part)
                
                filename = os.path.basename(attachment_path)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {filename}'
                )
                
                msg.attach(part)
                print(f"✓ Attached: {filename}")
            else:
                print(f"✗ Attachment not found: {attachment_path}")
        
        # Send email using Gmail
        print(f"Connecting to Gmail SMTP server...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Enable TLS encryption
        server.login(GMAIL_EMAIL, GMAIL_PASSWORD)  # Login with credentials
        
        # Send the email
        text = msg.as_string()
        server.sendmail(GMAIL_EMAIL, TO_EMAIL, text)
        server.quit()
        
        print(f"✓ Email sent successfully to {TO_EMAIL}")
        return True
        
    except Exception as e:
        print(f"✗ Email sending failed: {str(e)}")
        return False

        #

        ########## replace ip with email 

def cleanup_temp_files(file_paths):
    """Clean up temporary files"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"✓ Cleaned up: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"✗ Could not clean up {file_path}: {str(e)}")

def print_results(image_data):
    """Print results in DevTools Network tab format"""
    if not image_data:
        print("No valid images found.")
        return
    
    print("\n" + "="*90)
    print("DEVTOOLS NETWORK TAB - VALID IMAGE REQUESTS")
    print("="*90)
    print(f"{'Name':<45} {'Size':<15} {'Type':<30}")
    print("-"*90)
    
    for img in image_data:
        name = img['name'][:44] if len(img['name']) > 44 else img['name']
        size = str(img['size'])[:14] if len(str(img['size'])) > 14 else str(img['size'])
        img_type = img['type'][:29] if len(img['type']) > 29 else img['type']
        
        print(f"{name:<45} {size:<15} {img_type:<30}")
    
    print("-"*90)
    print(f"Total: {len(image_data)} valid images")

def print_usage():
    """Print usage instructions"""
    print("\nUsage: python network_capture.py <URL> <REPORT_TYPE>")
    print("\nParameters:")
    print("  URL           - Website URL to analyze (e.g., https://example.com)")
    print("  REPORT_TYPE   - Type of report to generate:")
    print("                  'html' - Generate HTML report and send via email")
    print("                  'csv'  - Generate CSV report and send via email")
    print("                  'all'  - Generate both HTML and CSV reports and send via email")
    print("\nExamples:")
    print('  python network_capture.py "https://example.com" "html"')
    print('  python network_capture.py "https://example.com" "csv"')
    print('  python network_capture.py "https://example.com" "all"')
    print("\nNote: Reports will be generated in temp directory and sent via email, then cleaned up.")

def main():
    # Check command line arguments
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Get report type from command line argument (default to 'all' if not specified)
    if len(sys.argv) >= 3:
        report_type = sys.argv[2].lower()
    else:
        report_type = 'all'
    
    # Validate report type
    valid_report_types = ['html', 'csv', 'all']
    if report_type not in valid_report_types:
        print(f"\nError: Invalid report type '{report_type}'")
        print(f"Valid options are: {', '.join(valid_report_types)}")
        print_usage()
        sys.exit(1)
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    print(f"\nSelected report type: {report_type.upper()}")
    print(f"Output: Reports will be emailed to {TO_EMAIL}")
    
    driver = None
    start_time = time.time()
    generated_files = []
    
    try:
        print("Starting Chrome browser...")
        driver = setup_driver()
        
        # Extract ALL network data first, then filter for images
        all_data, image_data = extract_all_network_data(driver, url)
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_images = []
        for img in image_data:
            if img['url'] not in seen_urls:
                seen_urls.add(img['url'])
                unique_images.append(img)
        
        # Filter to only include images from the same domain as target URL
        domain_filtered_images = filter_same_domain_images(unique_images, url)
        
        # Sort by size (largest first)
        domain_filtered_images.sort(key=lambda x: x['size_bytes'], reverse=True)
        
        # Calculate generation time
        generation_time = time.time() - start_time
        
        # Calculate statistics for display and email
        stats = calculate_statistics(domain_filtered_images)
        stats['image_data'] = domain_filtered_images  # Add image data for email
        
        # === DISPLAY SUMMARY FIRST ===
        print(f"\n{'='*60}")
        print("WEBSITE IMAGE ANALYSIS SUMMARY")
        print(f"{'='*60}")
        print(f"Website: {url}")
        print(f"Date: {datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')}")
        print(f"Time to Generate: {generation_time:.2f} seconds")
        print(f"Valid Images: {len(domain_filtered_images)}")
        print(f"Total Size: {stats['total_mb']:.2f} MB ({stats['total_kb']:.2f} KB)")
        print()
        print("=== Image Format Statistics ===")
        for fmt, count in stats['format_counts'].most_common():
            percentage = (count / len(domain_filtered_images) * 100) if len(domain_filtered_images) > 0 else 0
            print(f"{fmt}: {count} ({percentage:.1f}%)")
        print()
        print("=== URL Filtering Applied ===")
        print("✓ Included: data:image/ URLs (base64 embedded images)")
        print("✓ Filtered out: other data: URLs (non-image)")
        print("✓ Filtered out: chrome:// URLs (browser internal)")
        print("✓ Filtered out: chrome-extension:// URLs")
        print("✓ Filtered out: blob: URLs")
        print("✓ Filtered out: External domain URLs (Google, Facebook, etc.)")
        print("✓ Only same-domain HTTP/HTTPS + base64 image URLs included")
        
        # === THEN DISPLAY TABLE ===
        print_results(domain_filtered_images)
        
        # Generate reports based on report_type
        print(f"\nGenerating {report_type.upper()} report(s)...")
        
        if report_type in ['csv', 'all']:
            csv_filepath = save_enhanced_csv(domain_filtered_images, url, generation_time)
            generated_files.append(csv_filepath)
        
        if report_type in ['html', 'all']:
            html_filepath = generate_html_report(domain_filtered_images, url, generation_time)
            generated_files.append(html_filepath)
        
        # Send email with attachments
        print(f"\nSending email to {TO_EMAIL}...")
        email_sent = send_email_report(generated_files, url, stats, generation_time, report_type)
        
        if email_sent:
            print(f"\n{'='*60}")
            print("EMAIL SENT SUCCESSFULLY!")
            print(f"Recipient: {TO_EMAIL}")
            print(f"Attachments: {len(generated_files)} file(s)")
            for file_path in generated_files:
                print(f"  - {os.path.basename(file_path)}")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print("EMAIL SENDING FAILED!")
            print("Files generated locally:")
            for file_path in generated_files:
                print(f"  - {file_path}")
            print(f"{'='*60}")
        
        # Clean up temporary files
        print("\nCleaning up temporary files...")
        cleanup_temp_files(generated_files)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up any generated files on error
        if generated_files:
            print("Cleaning up files due to error...")
            cleanup_temp_files(generated_files)
        
    finally:
        if driver:
            driver.quit()
            print("\nBrowser closed.")

if __name__ == "__main__":
    main()