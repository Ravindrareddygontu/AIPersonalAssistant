const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

// Sizes for different icon formats
const sizes = [16, 32, 48, 64, 128, 256, 512, 1024];

async function generateRoundedIcons() {
    const svgPath = path.join(__dirname, 'static', 'icons', 'icon.svg');
    const svgContent = fs.readFileSync(svgPath, 'utf8');
    
    console.log('Generating rounded icons from SVG...');
    
    for (const size of sizes) {
        const outputPath = size === 1024 
            ? path.join(__dirname, 'static', 'icon.png')
            : path.join(__dirname, 'static', 'icons', `icon-${size}.png`);
        
        try {
            await sharp(Buffer.from(svgContent))
                .resize(size, size)
                .png()
                .toFile(outputPath);
            
            console.log(`✓ Generated ${outputPath} (${size}x${size})`);
        } catch (err) {
            console.error(`✗ Failed to generate ${size}x${size}:`, err.message);
        }
    }
    
    console.log('\nDone! All rounded icons generated.');
}

generateRoundedIcons().catch(console.error);

