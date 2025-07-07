// server.js - Enhanced Image Analyzer Server with Location Detection
const express = require("express");
const cors = require("cors");
const axios = require("axios");
const puppeteer = require("puppeteer");
const { URL } = require("url");

const app = express();

// Middleware
app.use(cors());
app.use(express.json({ limit: "50mb" })); // Increased limit for large image URL lists
app.use(express.urlencoded({ limit: "50mb", extended: true }));

// Request logging middleware
app.use((req, res, next) => {
  const timestamp = new Date().toISOString();
  const bodySize = req.headers["content-length"]
    ? `${Math.round(req.headers["content-length"] / 1024)}KB`
    : "unknown";
  console.log(
    `${timestamp} - ${req.method} ${req.path} - Body size: ${bodySize}`
  );
  next();
});

// Helper functions
async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isNonImageContentType(contentType) {
  if (!contentType) return false;

  const lowerContentType = contentType.toLowerCase();

  // List of non-image content types to filter out
  const nonImageTypes = [
    "text/html",
    "text/plain",
    "text/css",
    "text/javascript",
    "text/xml",
    "application/json",
    "application/javascript",
    "application/x-javascript",
    "application/xml",
    "application/xhtml",
    "application/pdf",
    "application/octet-stream",
    "application/zip",
    "application/x-www-form-urlencoded",
    "video/",
    "audio/",
  ];

  return (
    nonImageTypes.some((type) => lowerContentType.includes(type)) ||
    !lowerContentType.includes("image/")
  );
}

function getWebsiteName(url) {
  try {
    const domain = new URL(url).hostname.replace("www.", "");
    return domain.split(".")[0];
  } catch {
    return "website";
  }
}

function shouldIgnoreUrl(url) {
  const ignoredDomains = [
    "facebook.com",
    "google.com",
    "fbcdn.net",
    "googleusercontent.com",
    "twitter.com",
    "instagram.com",
  ];
  try {
    const domain = new URL(url).hostname;
    return ignoredDomains.some((d) => domain.includes(d));
  } catch {
    return false;
  }
}

function isValidImageUrl(url) {
  // Enhanced list of valid image extensions including modern formats
  const validImageExtensions = [
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".tiff",
    ".tif",
    ".avif",
    ".heic",
    ".heif",
    ".jxl",
    ".jp2",
    ".jpx",
    ".j2k",
    ".wdp",
    ".jxr",
    ".dng",
    ".cr2",
    ".nef",
    ".arw",
    ".raw",
  ];

  try {
    const urlObj = new URL(url);
    const pathname = urlObj.pathname.toLowerCase();
    const extension = pathname.split(".").pop();

    // Check for obvious non-image patterns
    const nonImagePatterns = [
      "/api/",
      "/ajax/",
      "/json/",
      "/xml/",
      ".json",
      ".xml",
      ".html",
      ".htm",
      ".php",
      ".jsp",
      ".asp",
      ".js",
      ".css",
      ".pdf",
      ".doc",
      ".zip",
      ".mp4",
      ".avi",
      ".mov",
      ".mp3",
      ".wav",
    ];

    // Filter out obvious non-image URLs
    if (nonImagePatterns.some((pattern) => pathname.includes(pattern))) {
      return false;
    }

    // Check for valid image extensions (enhanced pattern)
    return (
      validImageExtensions.includes(`.${extension}`) ||
      url.match(
        /\.(jpg|jpeg|png|gif|webp|svg|ico|bmp|tiff|tif|avif|heic|heif|jxl|jp2|jpx|j2k|wdp|jxr|dng|cr2|nef|arw|raw)(\?.*)?$/i
      )
    );
  } catch {
    return false;
  }
}

function makeAbsoluteUrl(baseUrl, relativeUrl) {
  try {
    if (relativeUrl.startsWith("http")) {
      return relativeUrl; // Already absolute
    }

    const base = new URL(baseUrl);

    if (relativeUrl.startsWith("//")) {
      return base.protocol + relativeUrl; // Protocol-relative
    }

    if (relativeUrl.startsWith("/")) {
      return base.origin + relativeUrl; // Root-relative
    }

    // Relative to current path
    return new URL(relativeUrl, baseUrl).href;
  } catch {
    return null;
  }
}

// Enhanced function to detect image location and context on the page
function getImageLocationDetectionScript() {
  return `
    (function() {
      function detectImageLocation(imgElement) {
        try {
          const rect = imgElement.getBoundingClientRect();
          const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
          
          // Get absolute coordinates
          const coordinates = {
            x: Math.round(rect.left + scrollLeft),
            y: Math.round(rect.top + scrollTop),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
          };

          // Detect page sections by analyzing parent elements
          const sections = [];
          let contextInfo = "";
          
          // Traverse up the DOM to find semantic sections
          let currentElement = imgElement;
          const maxTraversal = 10; // Limit traversal to avoid infinite loops
          let traversalCount = 0;
          
          while (currentElement && currentElement !== document.body && traversalCount < maxTraversal) {
            const tagName = currentElement.tagName ? currentElement.tagName.toLowerCase() : '';
            const className = currentElement.className ? currentElement.className.toString().toLowerCase() : '';
            const id = currentElement.id ? currentElement.id.toLowerCase() : '';
            
            // Check for semantic HTML5 elements
            if (['header', 'nav', 'main', 'aside', 'footer', 'section', 'article'].includes(tagName)) {
              if (tagName === 'header') sections.push('Header');
              else if (tagName === 'nav') sections.push('Navigation');
              else if (tagName === 'main') sections.push('Main');
              else if (tagName === 'aside') sections.push('Sidebar');
              else if (tagName === 'footer') sections.push('Footer');
              else if (tagName === 'section' || tagName === 'article') sections.push('Content');
            }
            
            // Check for common class/id patterns
            if (className || id) {
              const combined = (className + " " + id).toLowerCase();
              
              if (combined.includes('header') || combined.includes('top')) {
                sections.push('Header');
              } else if (combined.includes('nav') || combined.includes('menu') || combined.includes('navigation')) {
                sections.push('Navigation');
              } else if (combined.includes('sidebar') || combined.includes('aside') || combined.includes('widget')) {
                sections.push('Sidebar');
              } else if (combined.includes('footer') || combined.includes('bottom')) {
                sections.push('Footer');
              } else if (combined.includes('main') || combined.includes('content') || combined.includes('article')) {
                sections.push('Main');
              } else if (combined.includes('hero') || combined.includes('banner') || combined.includes('slider')) {
                sections.push('Main');
              }
            }
            
            currentElement = currentElement.parentElement;
            traversalCount++;
          }
          
          // If no sections detected, use position-based detection
          if (sections.length === 0) {
            const viewportHeight = window.innerHeight;
            const documentHeight = Math.max(
              document.body.scrollHeight,
              document.body.offsetHeight,
              document.documentElement.clientHeight,
              document.documentElement.scrollHeight,
              document.documentElement.offsetHeight
            );
            const relativeY = coordinates.y / documentHeight;
            
            if (relativeY < 0.2) {
              sections.push('Header');
            } else if (relativeY > 0.8) {
              sections.push('Footer');
            } else {
              sections.push('Main');
            }
          }
          
          // Remove duplicates and sort
          const uniqueSections = [...new Set(sections)];
          
          // Generate context information
          const altText = imgElement.alt || "";
          const title = imgElement.title || "";
          let figcaption = "";
          
          try {
            const figure = imgElement.closest('figure');
            if (figure) {
              const caption = figure.querySelector('figcaption');
              if (caption) {
                figcaption = caption.textContent || "";
              }
            }
          } catch (e) {
            // Ignore closest() errors in older browsers
          }
          
          if (altText) contextInfo += "Alt: " + altText.substring(0, 50);
          if (title) contextInfo += (contextInfo ? " | " : "") + "Title: " + title.substring(0, 50);
          if (figcaption) contextInfo += (contextInfo ? " | " : "") + "Caption: " + figcaption.substring(0, 50);
          
          return {
            coordinates,
            sections: uniqueSections.length > 0 ? uniqueSections : ['Unknown'],
            contextInfo: contextInfo || "No context available"
          };
        } catch (error) {
          return {
            coordinates: { x: 0, y: 0, width: 0, height: 0 },
            sections: ['Unknown'],
            contextInfo: "Error detecting location: " + error.message
          };
        }
      }

      // Extract images with location data
      function extractImagesWithLocation() {
        try {
          const imageData = [];
          const allImages = [];
          
          // Get all img elements
          const imgElements = document.querySelectorAll('img');
          imgElements.forEach((img) => {
            try {
              const urls = [];
              
              if (img.src) urls.push(img.src);
              if (img.getAttribute('data-src')) urls.push(img.getAttribute('data-src'));
              if (img.getAttribute('data-lazy-src')) urls.push(img.getAttribute('data-lazy-src'));
              if (img.getAttribute('data-original')) urls.push(img.getAttribute('data-original'));
              
              // Handle srcset
              if (img.srcset) {
                const srcsetUrls = img.srcset.split(',').map(s => s.trim().split(' ')[0]);
                urls.push(...srcsetUrls);
              }
              
              // Handle data-srcset
              if (img.getAttribute('data-srcset')) {
                const dataSrcsetUrls = img.getAttribute('data-srcset').split(',').map(s => s.trim().split(' ')[0]);
                urls.push(...dataSrcsetUrls);
              }
              
              // Get location data for this image
              const locationInfo = detectImageLocation(img);
              
              urls.forEach(url => {
                if (url && url.trim()) {
                  allImages.push(url.trim());
                  imageData.push({
                    url: url.trim(),
                    locationInfo: locationInfo
                  });
                }
              });
            } catch (e) {
              // Skip problematic images
            }
          });
          
          // Get images from picture elements
          try {
            const pictures = document.getElementsByTagName('picture');
            for (const picture of pictures) {
              const sources = picture.getElementsByTagName('source');
              const img = picture.querySelector('img');
              const locationInfo = img ? detectImageLocation(img) : {
                coordinates: { x: 0, y: 0, width: 0, height: 0 },
                sections: ['Unknown'],
                contextInfo: 'Picture element'
              };
              
              for (const source of sources) {
                if (source.srcset) {
                  const srcsetUrls = source.srcset.split(',');
                  srcsetUrls.forEach(url => {
                    const cleanUrl = url.trim().split(' ')[0];
                    if (cleanUrl) {
                      allImages.push(cleanUrl);
                      imageData.push({
                        url: cleanUrl,
                        locationInfo: locationInfo
                      });
                    }
                  });
                }
              }
            }
          } catch (e) {
            // Skip picture elements if there's an error
          }
          
          // Get CSS background images with location detection
          try {
            const elements = document.querySelectorAll('*');
            for (let i = 0; i < Math.min(elements.length, 1000); i++) { // Limit to first 1000 elements for performance
              const element = elements[i];
              try {
                const style = window.getComputedStyle(element);
                const bgImage = style.backgroundImage;
                
                if (bgImage && bgImage !== 'none') {
                  const matches = bgImage.match(/url\\(["']?(.*?)["']?\\)/g);
                  if (matches) {
                    const locationInfo = detectImageLocation(element);
                    matches.forEach(match => {
                      const url = match.replace(/url\\(["']?/, '').replace(/["']?\\)/, '');
                      if (url && url !== 'none') {
                        allImages.push(url);
                        imageData.push({
                          url: url,
                          locationInfo: locationInfo
                        });
                      }
                    });
                  }
                }
              } catch (e) {
                // Skip elements that cause errors
              }
            }
          } catch (e) {
            // Skip CSS background extraction if there's an error
          }
          
          return {
            imageUrls: allImages,
            locationData: imageData
          };
        } catch (error) {
          return {
            imageUrls: [],
            locationData: [],
            error: error.message
          };
        }
      }
      
      return extractImagesWithLocation();
    })();
  `;
}

// Website image extraction endpoint with enhanced location detection
app.post("/api/extract-images", async (req, res) => {
  let browser;
  try {
    const { url, options = {} } = req.body;

    if (!url) {
      return res.status(400).json({
        success: false,
        error: "URL is required",
      });
    }

    // Validate URL format
    if (!url.match(/^https?:\/\//)) {
      return res.status(400).json({
        success: false,
        error: "URL must start with http:// or https://",
      });
    }

    const {
      scrollIterations = 3,
      scrollDelay = 2000,
      pageLoadWait = 5,
    } = options;

    // Validate options
    if (scrollIterations < 1 || scrollIterations > 50) {
      return res.status(400).json({
        success: false,
        error: "Scroll iterations must be between 1 and 50",
      });
    }

    if (scrollDelay < 500 || scrollDelay > 10000) {
      return res.status(400).json({
        success: false,
        error: "Scroll delay must be between 500 and 10000 ms",
      });
    }

    if (pageLoadWait < 3 || pageLoadWait > 60) {
      return res.status(400).json({
        success: false,
        error: "Page load wait must be between 3 and 60 seconds",
      });
    }

    console.log(
      `Starting enhanced image extraction with location detection for: ${url}`
    );

    // Launch Puppeteer with improved compatibility
    browser = await puppeteer.launch({
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-web-security",
        "--disable-features=VizDisplayCompositor",
        "--window-size=1920,1080",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
      ],
      defaultViewport: {
        width: 1920,
        height: 1080,
      },
    });

    const page = await browser.newPage();

    // Set user agent for better compatibility
    await page.setUserAgent(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    );

    console.log("Navigating to website...");
    try {
      await page.goto(url, {
        waitUntil: "networkidle2",
        timeout: 60000,
      });
    } catch (error) {
      console.log("Falling back to basic navigation...");
      await page.goto(url, {
        waitUntil: "domcontentloaded",
        timeout: 60000,
      });
    }

    console.log(`Waiting for page to load (${pageLoadWait} seconds)...`);
    await sleep(pageLoadWait * 1000);

    const allImageData = [];
    const allImageUrls = new Set();

    console.log(
      "Performing enhanced image discovery with location detection..."
    );

    // Method 1: Progressive scrolling with image extraction and location detection
    for (let i = 0; i < scrollIterations; i++) {
      console.log(`Scroll iteration ${i + 1} of ${scrollIterations}...`);

      // Scroll to different positions to trigger lazy loading
      const scrollPositions = [0, 0.25, 0.5, 0.75, 1.0];

      for (const position of scrollPositions) {
        await page.evaluate((pos) => {
          window.scrollTo(0, document.body.scrollHeight * pos);
        }, position);

        await sleep(scrollDelay / 5);

        // Extract images with location data at each scroll position
        const extractionResult = await page.evaluate(
          getImageLocationDetectionScript()
        );

        // Process the results
        extractionResult.imageUrls.forEach((imageUrl) => {
          allImageUrls.add(imageUrl);
        });

        // Store location data
        extractionResult.locationData.forEach((data) => {
          // Check if we already have this URL in our data
          const existingIndex = allImageData.findIndex(
            (item) => item.url === data.url
          );
          if (existingIndex === -1) {
            allImageData.push(data);
          } else {
            // Update with more detailed location info if available
            if (
              data.locationInfo &&
              data.locationInfo.sections.length >
                allImageData[existingIndex].locationInfo.sections.length
            ) {
              allImageData[existingIndex] = data;
            }
          }
        });
      }

      await sleep(scrollDelay);
    }

    console.log(
      `Found ${allImageUrls.size} images with location data from progressive scrolling`
    );

    // Method 2: Final comprehensive extraction after all scrolling
    console.log("Performing final comprehensive extraction...");
    const finalExtractionResult = await page.evaluate(
      getImageLocationDetectionScript()
    );

    // Merge final results
    finalExtractionResult.imageUrls.forEach((imageUrl) => {
      allImageUrls.add(imageUrl);
    });

    finalExtractionResult.locationData.forEach((data) => {
      const existingIndex = allImageData.findIndex(
        (item) => item.url === data.url
      );
      if (existingIndex === -1) {
        allImageData.push(data);
      }
    });

    await browser.close();

    // Process and filter URLs
    console.log("Processing and validating image URLs with location data...");
    const baseUri = new URL(url);
    const processedResults = [];
    const locationDataMap = new Map();

    // Create a map of URLs to location data
    allImageData.forEach((data) => {
      locationDataMap.set(data.url, data.locationInfo);
    });

    for (const imagePath of allImageUrls) {
      // Skip invalid URLs
      if (
        !imagePath ||
        imagePath.startsWith("data:") ||
        imagePath === "about:blank"
      ) {
        continue;
      }

      // Skip ignored domains
      if (shouldIgnoreUrl(imagePath)) {
        continue;
      }

      // Make absolute URL
      const absoluteUrl = makeAbsoluteUrl(url, imagePath);
      if (!absoluteUrl) {
        continue;
      }

      // Validate as image URL
      if (isValidImageUrl(absoluteUrl)) {
        processedResults.push({
          url: absoluteUrl,
          locationInfo: locationDataMap.get(imagePath) ||
            locationDataMap.get(absoluteUrl) || {
              coordinates: { x: 0, y: 0 },
              sections: ["Unknown"],
              contextInfo: "Location data not available",
            },
        });
      }
    }

    // Remove duplicates based on URL
    const uniqueResults = [];
    const seenUrls = new Set();

    processedResults.forEach((result) => {
      if (!seenUrls.has(result.url)) {
        seenUrls.add(result.url);
        uniqueResults.push(result);
      }
    });

    console.log(
      `Found ${uniqueResults.length} valid image URLs with location data after filtering`
    );

    // Separate URLs and location data for the response
    const imageUrls = uniqueResults.map((result) => result.url);
    const locationData = uniqueResults.reduce((acc, result) => {
      acc[result.url] = result.locationInfo;
      return acc;
    }, {});

    res.json({
      success: true,
      imageUrls: imageUrls,
      locationData: locationData,
      stats: {
        totalFound: allImageUrls.size,
        validImages: uniqueResults.length,
        websiteName: getWebsiteName(url),
        withLocationData: Object.keys(locationData).length,
      },
    });
  } catch (error) {
    console.error("Image extraction error:", error);

    if (browser) {
      await browser.close();
    }

    res.status(500).json({
      success: false,
      error: error.message || "Failed to extract images from website",
    });
  }
});

// Enhanced image analysis endpoint with location data support
app.post("/api/analyze-images", async (req, res) => {
  try {
    const { urls, locationData } = req.body;

    if (!urls || !Array.isArray(urls)) {
      return res.status(400).json({
        error: "Invalid request. URLs array required.",
      });
    }

    // Check for reasonable limits
    if (urls.length > 1000) {
      return res.status(400).json({
        error: "Too many URLs. Maximum 1000 URLs per request.",
      });
    }

    console.log(`Analyzing ${urls.length} image URLs with location data...`);

    const results = await Promise.all(
      urls.map(async (url, index) => {
        try {
          console.log(
            `Processing image ${index + 1}/${urls.length}: ${url.substring(
              0,
              100
            )}...`
          );

          // First try HEAD request for metadata
          const headResponse = await axios.head(url, {
            timeout: 15000,
            headers: {
              "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
          });

          const contentLength = headResponse.headers["content-length"];
          const contentType = headResponse.headers["content-type"];

          // Filter out non-image content types (enhanced filtering)
          if (contentType && isNonImageContentType(contentType)) {
            console.log(
              `Filtered out URL: ${url.substring(
                0,
                100
              )}... (Content-Type: ${contentType})`
            );
            return {
              url,
              sizeBytes: 0,
              success: false,
              error: `Filtered: Non-image content type (${contentType})`,
              contentType,
              locationInfo: locationData ? locationData[url] : null,
            };
          }

          if (contentLength) {
            return {
              url,
              sizeBytes: parseInt(contentLength),
              success: true,
              contentType,
              locationInfo: locationData ? locationData[url] : null,
            };
          }

          // If HEAD fails or no content-length, try partial GET request
          const getResponse = await axios.get(url, {
            responseType: "stream",
            timeout: 10000,
            headers: {
              "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
              Range: "bytes=0-1023", // Only get first 1KB to check
            },
          });

          // Cancel the stream immediately
          getResponse.data.destroy();

          const size = parseInt(getResponse.headers["content-length"]) || 0;
          const type = getResponse.headers["content-type"];

          // Apply same content type filtering for GET requests
          if (type && isNonImageContentType(type)) {
            console.log(
              `Filtered out URL (GET): ${url.substring(
                0,
                100
              )}... (Content-Type: ${type})`
            );
            return {
              url,
              sizeBytes: 0,
              success: false,
              error: `Filtered: Non-image content type (${type})`,
              contentType: type,
              locationInfo: locationData ? locationData[url] : null,
            };
          }

          return {
            url,
            sizeBytes: size,
            success: true,
            contentType: type,
            locationInfo: locationData ? locationData[url] : null,
          };
        } catch (error) {
          console.error(`Error analyzing ${url}:`, error.message);

          return {
            url,
            sizeBytes: 0,
            success: false,
            error: error.message,
            contentType: "Unknown",
            locationInfo: locationData ? locationData[url] : null,
          };
        }
      })
    );

    // Filter out failed/filtered results for final count
    const successfulResults = results.filter((r) => r.success);
    const filteredResults = results.filter(
      (r) => !r.success && r.error && r.error.includes("Filtered:")
    );

    // Remove filtered results from the final response (don't show them at all)
    const finalResults = results.filter((r) => r.success);

    console.log(
      `Analysis complete: ${successfulResults.length}/${urls.length} successful`
    );
    console.log(
      `Filtered out ${filteredResults.length} non-image content types`
    );
    console.log(
      `Location data available for ${
        finalResults.filter((r) => r.locationInfo).length
      } images`
    );

    // Log summary of filtered content types
    if (filteredResults.length > 0) {
      const contentTypeCounts = {};
      filteredResults.forEach((result) => {
        const contentType = result.contentType || "Unknown";
        contentTypeCounts[contentType] =
          (contentTypeCounts[contentType] || 0) + 1;
      });

      console.log("Filtered content types summary:");
      Object.entries(contentTypeCounts).forEach(([type, count]) => {
        console.log(`  ${type}: ${count} URLs filtered`);
      });
    }

    res.json({
      results: finalResults,
      summary: {
        totalProcessed: urls.length,
        totalReturned: finalResults.length,
        successful: successfulResults.length,
        filtered: filteredResults.length,
        failed: urls.length - successfulResults.length - filteredResults.length,
        withLocationData: finalResults.filter((r) => r.locationInfo).length,
        filteredContentTypes: filteredResults.reduce((acc, result) => {
          const contentType = result.contentType || "Unknown";
          acc[contentType] = (acc[contentType] || 0) + 1;
          return acc;
        }, {}),
      },
    });
  } catch (error) {
    console.error("Server error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

// Health check endpoint
app.get("/api/health", (req, res) => {
  res.json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    features: {
      locationDetection: "enabled",
      enhancedImageFormats: "enabled",
      modernFormatsSupported: ["WebP", "AVIF", "HEIC", "JXL", "JPEG 2000"],
    },
    services: {
      puppeteer: "available",
      axios: "available",
    },
  });
});

// Error handling middleware
app.use((error, req, res, next) => {
  console.error("Unhandled error:", error);

  // Handle payload too large errors
  if (error.type === "entity.too.large") {
    return res.status(413).json({
      error: "Request payload too large",
      message:
        "Please reduce the number of URLs and try again. Maximum recommended: 1000 URLs per request.",
      limit: "50MB",
    });
  }

  // Handle JSON parsing errors
  if (error.type === "entity.parse.failed") {
    return res.status(400).json({
      error: "Invalid JSON format",
      message: "Please check your request format and try again.",
    });
  }

  res.status(500).json({
    error: "Internal server error",
    message: error.message,
  });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(
    `Enhanced Image Analyzer Server with Location Detection running on port ${PORT}`
  );
  console.log(`Available endpoints:`);
  console.log(
    `  POST /api/extract-images - Extract images from website URL with location data`
  );
  console.log(
    `  POST /api/analyze-images - Analyze image URLs with location information`
  );
  console.log(`  GET  /api/health - Health check with feature information`);
  console.log(`\nEnhanced features:`);
  console.log(
    `  ✓ Location detection (Header, Main, Sidebar, Footer, Navigation)`
  );
  console.log(`  ✓ Position coordinates and context information`);
  console.log(
    `  ✓ Support for all modern image formats (WebP, AVIF, HEIC, JXL, etc.)`
  );
  console.log(`  ✓ Enhanced image type detection and validation`);
});

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\nShutting down enhanced server gracefully...");
  process.exit(0);
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled Rejection at:", promise, "reason:", reason);
});

process.on("uncaughtException", (error) => {
  console.error("Uncaught Exception:", error);
  process.exit(1);
});
