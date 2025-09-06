from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import time
import json
import requests
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse, urljoin
import re
from bs4 import BeautifulSoup
import mimetypes
import base64

app = Flask(__name__)
CORS(app)

# Configuration
REQUEST_TIMEOUT = 15  # seconds
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def get_session():
    """Create a requests session with headers"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    return session

def is_valid_image_url(url):
    """Check if URL is a valid image URL (including base64 data: URLs) - EXACT match with network_capture.py"""
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
    """Check if image URL belongs to the same domain as target URL - EXACT match with network_capture.py"""
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

def get_extension_from_mime_type(mime_type):
    """Extract extension from MIME type - EXACT match with network_capture.py"""
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
    """Extract information from base64 data:image/ URL - EXACT match with network_capture.py"""
    try:
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

def get_extension_from_url(url):
    """Extract extension from URL or filename - EXACT match with network_capture.py"""
    url_lower = url.lower()
    
    # Common image extensions
    extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif']
    
    for ext in extensions:
        if f'.{ext}' in url_lower:
            if ext == 'jpeg':
                return 'jpg'  # Normalize jpeg to jpg
            return ext
    
    return 'unknown'

def format_file_size(size_bytes):
    """Format file size exactly like DevTools does - EXACT match with network_capture.py"""
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

def extract_images_from_html(html_content, base_url):
    """Extract image URLs from HTML content with comprehensive search"""
    image_urls = set()
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all img tags with src and data-src
        img_tags = soup.find_all('img')
        for img in img_tags:
            # Regular src attribute
            src = img.get('src')
            if src:
                full_url = make_absolute_url(src, base_url)
                if is_valid_image_url(full_url):
                    image_urls.add(full_url)
            
            # Lazy loading attributes
            for attr in ['data-src', 'data-lazy-src', 'data-original', 'data-srcset']:
                data_src = img.get(attr)
                if data_src:
                    # Handle srcset format (multiple URLs)
                    if 'srcset' in attr:
                        urls = parse_srcset(data_src)
                        for url in urls:
                            full_url = make_absolute_url(url, base_url)
                            if is_valid_image_url(full_url):
                                image_urls.add(full_url)
                    else:
                        full_url = make_absolute_url(data_src, base_url)
                        if is_valid_image_url(full_url):
                            image_urls.add(full_url)
        
        # Find picture elements with source tags
        picture_tags = soup.find_all('picture')
        for picture in picture_tags:
            sources = picture.find_all('source')
            for source in sources:
                srcset = source.get('srcset')
                if srcset:
                    urls = parse_srcset(srcset)
                    for url in urls:
                        full_url = make_absolute_url(url, base_url)
                        if is_valid_image_url(full_url):
                            image_urls.add(full_url)
        
        # Find CSS background images in style tags
        style_tags = soup.find_all('style')
        for style in style_tags:
            if style.string:
                css_images = extract_css_images(style.string, base_url)
                image_urls.update(css_images)
        
        # Find inline style background images
        elements_with_style = soup.find_all(attrs={'style': True})
        for element in elements_with_style:
            style = element.get('style', '')
            css_images = extract_css_images(style, base_url)
            image_urls.update(css_images)
        
        # Look for common image container patterns
        for selector in ['.image', '.img', '.photo', '.picture', '[data-bg]', '[data-background]']:
            try:
                elements = soup.select(selector)
                for element in elements:
                    for attr in element.attrs:
                        if 'src' in attr or 'url' in attr or 'image' in attr:
                            value = element.get(attr)
                            if value and isinstance(value, str):
                                full_url = make_absolute_url(value, base_url)
                                if is_valid_image_url(full_url):
                                    image_urls.add(full_url)
            except:
                continue
        
    except Exception as e:
        print(f"Error parsing HTML: {str(e)}")
    
    return list(image_urls)

def make_absolute_url(url, base_url):
    """Convert relative URL to absolute URL"""
    if not url:
        return url
        
    # Already absolute or data URL
    if url.startswith(('http://', 'https://', 'data:')):
        return url
    
    # Protocol-relative URL
    if url.startswith('//'):
        return 'https:' + url
    
    # Absolute path
    if url.startswith('/'):
        return urljoin(base_url, url)
    
    # Relative path
    return urljoin(base_url, url)

def parse_srcset(srcset):
    """Parse srcset attribute to extract URLs"""
    urls = []
    if not srcset:
        return urls
    
    # Split by comma and extract URLs (ignore width/density descriptors)
    parts = srcset.split(',')
    for part in parts:
        url = part.strip().split()[0]  # Take first part (URL) before any descriptors
        if url:
            urls.append(url)
    
    return urls

def extract_css_images(css_content, base_url):
    """Extract image URLs from CSS content"""
    image_urls = set()
    
    # Find all url() patterns in CSS
    url_patterns = [
        r'background-image:\s*url\(["\']?([^"\'()]+)["\']?\)',
        r'background:\s*[^;]*url\(["\']?([^"\'()]+)["\']?\)',
        r'content:\s*url\(["\']?([^"\'()]+)["\']?\)',
        r'list-style-image:\s*url\(["\']?([^"\'()]+)["\']?\)',
    ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, css_content, re.IGNORECASE)
        for match in matches:
            full_url = make_absolute_url(match.strip(), base_url)
            if is_valid_image_url(full_url):
                image_urls.add(full_url)
    
    return image_urls

def get_image_info_detailed(url, session):
    """Get detailed image information similar to network_capture.py"""
    try:
        # Handle base64 data URLs
        if url.lower().startswith('data:image/'):
            mime_type, size_bytes, extension = get_base64_image_info(url)
            if mime_type:
                return {
                    'url': url,
                    'name': f"base64_image_{extension}",
                    'size': format_file_size(size_bytes) if size_bytes > 0 else "(unknown)",
                    'size_bytes': size_bytes,
                    'type': extension,
                    'contentType': mime_type,
                    'success': True,
                    'status': 200
                }
            else:
                return {
                    'url': url,
                    'name': 'base64_image.unknown',
                    'size': "(unknown)",
                    'size_bytes': 0,
                    'type': 'unknown',
                    'contentType': 'unknown',
                    'success': False,
                    'status': 'Invalid base64'
                }
        
        # For HTTP/HTTPS URLs, try HEAD first, then GET with range
        try:
            # Try HEAD request first
            response = session.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            
            # If HEAD fails, try GET with small range
            if response.status_code >= 400:
                response = session.get(url, timeout=REQUEST_TIMEOUT, 
                                     headers={'Range': 'bytes=0-1023'}, 
                                     allow_redirects=True)
            
            if response.status_code >= 400:
                # Try one more time with regular GET but short timeout
                try:
                    response = session.get(url, timeout=5, allow_redirects=True, stream=True)
                    # Read only first chunk to verify it's an image
                    chunk = next(response.iter_content(1024), b'')
                    response.close()
                except:
                    return create_failed_image_info(url, response.status_code)
            
            # Get content info from headers
            content_type = response.headers.get('content-type', '').lower()
            content_length = response.headers.get('content-length')
            
            # Verify it's an image by content-type or URL extension
            is_image_mime = content_type.startswith('image/')
            url_extension = get_extension_from_url(url)
            
            if not is_image_mime and url_extension == 'unknown':
                return create_failed_image_info(url, 'Not an image')
            
            # If no MIME type but valid extension, construct MIME type
            if not is_image_mime and url_extension != 'unknown':
                content_type = f'image/{url_extension}'
            
            # Get file size
            size_bytes = 0
            if content_length:
                try:
                    size_bytes = int(content_length)
                except ValueError:
                    size_bytes = 0
            
            # Extract filename
            filename = url.split('/')[-1].split('?')[0].split('#')[0]
            if not filename or '.' not in filename:
                extension = get_extension_from_mime_type(content_type)
                if extension == 'unknown':
                    extension = get_extension_from_url(url)
                filename = f"image.{extension}" if extension != 'unknown' else 'image'
            
            # Get extension
            extension = get_extension_from_mime_type(content_type)
            if extension == 'unknown':
                extension = get_extension_from_url(url)
            
            return {
                'url': url,
                'name': filename,
                'size': format_file_size(size_bytes) if size_bytes > 0 else "(unknown)",
                'size_bytes': size_bytes,
                'type': extension,
                'contentType': content_type,
                'success': True,
                'status': response.status_code
            }
            
        except requests.exceptions.RequestException as e:
            return create_failed_image_info(url, f'Request failed: {str(e)}')
    
    except Exception as e:
        return create_failed_image_info(url, f'Error: {str(e)}')

def create_failed_image_info(url, status):
    """Create failed image info object"""
    filename = url.split('/')[-1].split('?')[0][:50] if url else 'unknown'
    return {
        'url': url,
        'name': filename,
        'size': "(unknown)",
        'size_bytes': 0,
        'type': 'unknown',
        'contentType': 'unknown',
        'success': False,
        'status': status
    }

def filter_same_domain_images(image_data, target_url):
    """Filter images to only include those from the same domain - matches network_capture.py"""
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

def extract_images_from_website(url, options=None):
    """Extract images from a website with comprehensive analysis"""
    if options is None:
        options = {}
    
    print(f"Extracting images from: {url}")
    
    session = get_session()
    
    try:
        # Get the main page
        print("Loading page and capturing network requests...")
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        # Extract images from HTML
        print("Analyzing HTML content for images...")
        image_urls = extract_images_from_html(response.text, url)
        
        # Remove duplicates
        unique_urls = list(set(image_urls))
        
        print(f"Found {len(unique_urls)} unique image URLs")
        
        # Filter same-domain images first (like network_capture.py)
        same_domain_urls = [img_url for img_url in unique_urls if is_same_domain_url(img_url, url)]
        
        print(f"After domain filtering: {len(same_domain_urls)} same-domain images")
        
        # Get detailed info for each image
        print("Getting detailed image information...")
        image_data = []
        for i, img_url in enumerate(same_domain_urls):
            print(f"Processing image {i+1}/{len(same_domain_urls)}: {img_url[:60]}...")
            img_info = get_image_info_detailed(img_url, session)
            image_data.append(img_info)
            
            # Small delay to avoid overwhelming the server
            time.sleep(0.1)
        
        # Filter out failed requests (like network_capture.py only shows successful ones)
        valid_images = [img for img in image_data if img['success']]
        
        # Sort by size (largest first) like network_capture.py
        image_data.sort(key=lambda x: x['size_bytes'], reverse=True)
        
        print(f"Final result: {len(valid_images)} valid images")
        
        return image_data, same_domain_urls
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching website: {str(e)}")
        raise Exception(f"Failed to fetch website: {str(e)}")
    except Exception as e:
        print(f"Error extracting images: {str(e)}")
        raise Exception(f"Failed to extract images: {str(e)}")

# API Routes

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'method': 'requests_only',
        'features': 'network_capture_compatible'
    })

@app.route('/api/extract-images', methods=['POST'])
def extract_images():
    try:
        data = request.get_json()
        url = data.get('url')
        options = data.get('options', {})
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'URL is required'
            }), 400
        
        print(f"Starting image extraction for: {url}")
        
        # Extract images using comprehensive method
        image_data, image_urls = extract_images_from_website(url, options)
        
        # Filter valid images
        valid_images = [img for img in image_data if img.get('success', False)]
        
        print(f"Extraction complete: {len(image_data)} total, {len(valid_images)} valid")
        
        return jsonify({
            'success': True,
            'imageUrls': image_urls,
            'imageData': image_data,
            'stats': {
                'total': len(image_data),
                'valid': len(valid_images),
                'sameDomain': len(image_data),
                'filtered': 0  # Already filtered by domain
            }
        })
        
    except Exception as e:
        print(f"Error extracting images: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analyze-images', methods=['POST'])
def analyze_images():
    try:
        data = request.get_json()
        
        # For URL analysis, we already have the image data from extraction
        if 'imageData' in data:
            # Use pre-extracted image data (more accurate)
            image_data = data['imageData']
            
            # Convert to expected format for frontend
            results = []
            for img in image_data:
                results.append({
                    'url': img['url'],
                    'filename': img['name'],
                    'type': img['type'],
                    'contentType': img['contentType'],
                    'sizeBytes': img['size_bytes'],
                    'sizeKB': f"{img['size_bytes'] / 1024:.1f}" if img['size_bytes'] > 0 else "0.0",
                    'sizeMB': f"{img['size_bytes'] / (1024 * 1024):.3f}" if img['size_bytes'] > 0 else "0.000",
                    'success': img['success'],
                    'status': 'Success' if img['success'] else str(img.get('status', 'Failed')),
                    'locationInfo': None
                })
            
            valid_count = len([r for r in results if r['success']])
            
            return jsonify({
                'success': True,
                'results': results,
                'summary': {
                    'totalProcessed': len(results),
                    'validImages': valid_count,
                    'filtered': len(results) - valid_count
                }
            })
        
        # For direct URL analysis (Image URLs Analysis mode)
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({
                'success': False,
                'error': 'URLs or imageData required'
            }), 400
        
        print(f"Analyzing {len(urls)} image URLs directly")
        
        session = get_session()
        results = []
        
        for i, url in enumerate(urls):
            print(f"Analyzing URL {i+1}/{len(urls)}: {url[:60]}...")
            img_info = get_image_info_detailed(url, session)
            results.append({
                'url': img_info['url'],
                'filename': img_info['name'],
                'type': img_info['type'],
                'contentType': img_info['contentType'],
                'sizeBytes': img_info['size_bytes'],
                'sizeKB': f"{img_info['size_bytes'] / 1024:.1f}" if img_info['size_bytes'] > 0 else "0.0",
                'sizeMB': f"{img_info['size_bytes'] / (1024 * 1024):.3f}" if img_info['size_bytes'] > 0 else "0.000",
                'success': img_info['success'],
                'status': 'Success' if img_info['success'] else str(img_info.get('status', 'Failed'))
            })
            
            # Small delay to avoid overwhelming servers
            time.sleep(0.1)
        
        valid_count = len([r for r in results if r['success']])
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'totalProcessed': len(results),
                'validImages': valid_count,
                'filtered': len(results) - valid_count
            }
        })
        
    except Exception as e:
        print(f"Error analyzing images: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("Python Image Analysis Server starting...")
    print("Using enhanced requests-only method (no WebDriver required)")
    print("Compatible with network_capture.py results")
    print("Server will run on http://localhost:3000")
    print("Required packages: pip install flask flask-cors requests beautifulsoup4")
    
    app.run(host='0.0.0.0', port=3000, debug=True)