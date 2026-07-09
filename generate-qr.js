const QRCode = require("qrcode");
const fs = require("fs");
const path = require("path");

const content = process.argv[2] || "https://hungpq.dev/ar-demo";
const outArg = process.argv[3] || "qr.png";
const outName = outArg.includes("/") ? outArg : `qrcodes/${outArg}`;
const outPath = path.join(__dirname, outName);

fs.mkdirSync(path.dirname(outPath), { recursive: true });

QRCode.toFile(
  outPath,
  content,
  { width: 512, margin: 2, errorCorrectionLevel: "H" },
  (err) => {
    if (err) throw err;
    console.log(`QR saved to ${outPath} (content: ${content})`);
  }
);
