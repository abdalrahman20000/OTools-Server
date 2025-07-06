// server.js - Enhanced Image Analyzer Server
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
    ".avif",
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
    ];

    // Filter out obvious non-image URLs
    if (nonImagePatterns.some((pattern) => pathname.includes(pattern))) {
      return false;
    }

    // Check for valid image extensions
    return (
      validImageExtensions.includes(`.${extension}`) ||
      url.match(/\.(jpg|jpeg|png|gif|webp|svg|ico|bmp|tiff|avif)(\?.*)?$/i)
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

// Website image extraction endpoint (matching PowerShell functionality)
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

    console.log(`Starting enhanced image extraction for: ${url}`);

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

    const allImageUrls = new Set();

    console.log("Performing enhanced image discovery...");

    // Method 1: Progressive scrolling with image extraction
    for (let i = 0; i < scrollIterations; i++) {
      console.log(`Scroll iteration ${i + 1} of ${scrollIterations}...`);

      // Scroll to different positions to trigger lazy loading
      const scrollPositions = [0, 0.25, 0.5, 0.75, 1.0];

      for (const position of scrollPositions) {
        await page.evaluate((pos) => {
          window.scrollTo(0, document.body.scrollHeight * pos);
        }, position);

        await sleep(scrollDelay / 5);

        // Extract images at each scroll position
        const images = await page.evaluate(() => {
          const imageUrls = [];

          // Get all img elements
          const imgElements = document.querySelectorAll("img");
          imgElements.forEach((img) => {
            if (img.src) imageUrls.push(img.src);
            if (img.getAttribute("data-src"))
              imageUrls.push(img.getAttribute("data-src"));
            if (img.getAttribute("data-lazy-src"))
              imageUrls.push(img.getAttribute("data-lazy-src"));

            // Handle srcset
            if (img.srcset) {
              const srcsetUrls = img.srcset
                .split(",")
                .map((s) => s.trim().split(" ")[0]);
              imageUrls.push(...srcsetUrls);
            }

            // Handle data-srcset
            if (img.getAttribute("data-srcset")) {
              const dataSrcsetUrls = img
                .getAttribute("data-srcset")
                .split(",")
                .map((s) => s.trim().split(" ")[0]);
              imageUrls.push(...dataSrcsetUrls);
            }
          });

          return imageUrls;
        });

        images.forEach((img) => allImageUrls.add(img));
      }

      await sleep(scrollDelay);
    }

    console.log(`Found ${allImageUrls.size} images from img elements`);

    // Method 2: Extract CSS background images
    console.log("Extracting CSS background images...");
    const backgroundImages = await page.evaluate(() => {
      const backgroundUrls = [];
      const elements = document.querySelectorAll("*");

      for (const element of elements) {
        const style = window.getComputedStyle(element);
        const bgImage = style.backgroundImage;

        if (bgImage && bgImage !== "none") {
          const matches = bgImage.match(/url\(["']?(.*?)["']?\)/g);
          if (matches) {
            matches.forEach((match) => {
              const url = match
                .replace(/url\(["']?/, "")
                .replace(/["']?\)/, "");
              if (url && url !== "none") {
                backgroundUrls.push(url);
              }
            });
          }
        }
      }

      return backgroundUrls;
    });

    backgroundImages.forEach((img) => allImageUrls.add(img));
    console.log(`Found ${backgroundImages.length} CSS background images`);

    // Method 3: JavaScript-based image discovery
    console.log("Using JavaScript to discover additional images...");
    const discoveredImages = await page.evaluate(() => {
      const allImages = [];

      // Get all img elements with various attributes
      const imgs = document.getElementsByTagName("img");
      for (const img of imgs) {
        if (img.src) allImages.push(img.src);
        if (img.getAttribute("data-src"))
          allImages.push(img.getAttribute("data-src"));
        if (img.getAttribute("data-lazy-src"))
          allImages.push(img.getAttribute("data-lazy-src"));
        if (img.getAttribute("data-original"))
          allImages.push(img.getAttribute("data-original"));
      }

      // Get images from picture elements
      const pictures = document.getElementsByTagName("picture");
      for (const picture of pictures) {
        const sources = picture.getElementsByTagName("source");
        for (const source of sources) {
          if (source.srcset) {
            const srcsetUrls = source.srcset.split(",");
            srcsetUrls.forEach((url) => {
              const cleanUrl = url.trim().split(" ")[0];
              if (cleanUrl) allImages.push(cleanUrl);
            });
          }
        }
      }

      // Get images from stylesheets (safe access)
      try {
        const stylesheets = document.styleSheets;
        for (const stylesheet of stylesheets) {
          try {
            const rules = stylesheet.cssRules || stylesheet.rules;
            if (rules) {
              for (const rule of rules) {
                if (rule.style && rule.style.backgroundImage) {
                  const bgImg = rule.style.backgroundImage;
                  const matches = bgImg.match(/url\("?([^"]*)"?\)/);
                  if (matches && matches[1]) {
                    allImages.push(matches[1]);
                  }
                }
              }
            }
          } catch (e) {
            // Cross-origin stylesheets may throw errors
          }
        }
      } catch (e) {
        // Stylesheet access may fail
      }

      return [...new Set(allImages)];
    });

    discoveredImages.forEach((img) => allImageUrls.add(img));
    console.log(`JavaScript discovery found additional images`);

    await browser.close();

    // Process and filter URLs
    console.log("Processing and validating image URLs...");
    const baseUri = new URL(url);
    const processedUrls = [];

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
        processedUrls.push(absoluteUrl);
      }
    }

    // Remove duplicates
    const uniqueUrls = [...new Set(processedUrls)];

    console.log(`Found ${uniqueUrls.length} valid image URLs after filtering`);

    res.json({
      success: true,
      imageUrls: uniqueUrls,
      stats: {
        totalFound: allImageUrls.size,
        validImages: uniqueUrls.length,
        websiteName: getWebsiteName(url),
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

// Image analysis endpoint (enhanced with content type filtering)
app.post("/api/analyze-images", async (req, res) => {
  try {
    const { urls } = req.body;

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

    console.log(`Analyzing ${urls.length} image URLs...`);

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
            };
          }

          if (contentLength) {
            return {
              url,
              sizeBytes: parseInt(contentLength),
              success: true,
              contentType,
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
            };
          }

          return {
            url,
            sizeBytes: size,
            success: true,
            contentType: type,
          };
        } catch (error) {
          console.error(`Error analyzing ${url}:`, error.message);

          return {
            url,
            sizeBytes: 0,
            success: false,
            error: error.message,
            contentType: "Unknown",
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
  console.log(`Enhanced Image Analyzer Server running on port ${PORT}`);
  console.log(`Available endpoints:`);
  console.log(`  POST /api/extract-images - Extract images from website URL`);
  console.log(`  POST /api/analyze-images - Analyze image URLs`);
  console.log(`  GET  /api/health - Health check`);
});

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\nShutting down server gracefully...");
  process.exit(0);
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled Rejection at:", promise, "reason:", reason);
});

process.on("uncaughtException", (error) => {
  console.error("Uncaught Exception:", error);
  process.exit(1);
});
// V2.7
