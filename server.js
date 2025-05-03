// server.js
const express = require("express");
const cors = require("cors");
const axios = require("axios");
const app = express();

// Middleware
app.use(cors());
app.use(express.json());

// Image size analysis endpoint
app.post("/api/analyze-images", async (req, res) => {
  try {
    const { urls } = req.body;
    if (!urls || !Array.isArray(urls)) {
      return res
        .status(400)
        .json({ error: "Invalid request. URLs array required." });
    }

    const results = await Promise.all(
      urls.map(async (url) => {
        try {
          // First try HEAD request
          const headResponse = await axios.head(url);
          const contentLength = headResponse.headers["content-length"];

          if (contentLength) {
            return {
              url,
              sizeBytes: parseInt(contentLength),
              success: true,
            };
          }

          // If HEAD fails or no content-length, try GET request (but only fetch partial content)
          const getResponse = await axios.get(url, {
            responseType: "stream",
            timeout: 5000,
          });

          return {
            url,
            sizeBytes: parseInt(getResponse.headers["content-length"]) || 0,
            success: true,
          };
        } catch (error) {
          console.error(`Error fetching ${url}:`, error.message);
          return {
            url,
            sizeBytes: 0,
            success: false,
            error: error.message,
          };
        }
      })
    );

    res.json({ results });
  } catch (error) {
    console.error("Server error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
