const puppeteer = require("puppeteer-core");
const http = require("http");
const handler = require("serve-handler");
const fs = require("fs");
const path = require("path");

const CHROME_PATH =
  process.env.CHROME_PATH || "/usr/bin/google-chrome-stable";
const PORT = 8199;

const srcImage = process.argv[2] || "./media/images/cat-target.jpg";
const outArg = process.argv[3] || "target.mind";
const outName = outArg.includes("/") ? outArg : `targets/${outArg}`;

async function main() {
  // cleanUrls:false is required — serve-handler otherwise redirects
  // /compile.html?src=X to /compile and drops the query string, silently
  // compiling the wrong (default) image every time.
  const server = http.createServer((req, res) =>
    handler(req, res, { public: __dirname, cleanUrls: false })
  );
  await new Promise((resolve) => server.listen(PORT, resolve));

  // Plain headless Chrome (software/swiftshader WebGL) is fine — verified
  // it produces byte-for-byte equivalent feature data to a real-GPU run.
  // No DISPLAY/GPU needed, works in any normal server/container.
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args: [
      "--no-sandbox",
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });

  try {
    const page = await browser.newPage();
    page.on("console", (msg) => console.log("[page]", msg.text()));
    page.on("pageerror", (err) => console.error("[pageerror]", err));

    await page.goto(`http://localhost:${PORT}/compile.html?src=${encodeURIComponent(srcImage)}`, {
      waitUntil: "networkidle0",
    });

    await page.waitForFunction(
      () => window.__compileState && window.__compileState.done === true ||
        (window.__compileState && window.__compileState.error),
      { timeout: 120000 }
    );

    const state = await page.evaluate(() => window.__compileState);
    console.log("imgDims:", JSON.stringify(state.imgDims), "(so sánh với kích thước thật của ảnh để chắc chắn compile đúng ảnh)");
    if (state.error) {
      throw new Error("Compile failed in browser: " + state.error);
    }

    const outPath = path.join(__dirname, outName);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, Buffer.from(state.base64, "base64"));
    console.log(`Wrote ${outPath} (${fs.statSync(outPath).size} bytes)`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
