import sharp from "sharp";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// SVG content — teal gradient background, white scope mark (ring + dot + handle)
const logoSvg = `
<svg width="512" height="512" viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="512" height="512" rx="112" fill="#14B8A6"/>
  <circle cx="256" cy="256" r="96" stroke="white" stroke-width="28" fill="none"/>
  <circle cx="256" cy="256" r="28" fill="white"/>
  <line x1="322" y1="190" x2="420" y2="92" stroke="white" stroke-width="28" stroke-linecap="round"/>
</svg>`;

const sizes = [
  { name: "logo-512.png",   size: 512  },  // GitHub org avatar
  { name: "logo-256.png",   size: 256  },  // General use, Twitter profile
  { name: "logo-128.png",   size: 128  },  // Smaller contexts
  { name: "logo-64.png",    size: 64   },  // Favicon source
  { name: "favicon-32.png", size: 32   },  // Favicon 32x32
  { name: "favicon-16.png", size: 16   },  // Favicon 16x16
];

for (const { name, size } of sizes) {
  await sharp(Buffer.from(logoSvg))
    .resize(size, size)
    .png({ quality: 100, compressionLevel: 9 })
    .toFile(join(__dirname, name));
  console.log(`✓ ${name} (${size}x${size})`);
}

console.log("\nDone! Use logo-512.png for GitHub avatar.");
