const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const sizes = [16, 32, 48, 64, 128, 256, 512, 1024];

function createCircleMask(size) {
    const circle = Buffer.from(
        `<svg width="${size}" height="${size}">
            <circle cx="${size/2}" cy="${size/2}" r="${size/2}" fill="white"/>
        </svg>`
    );
    return circle;
}

async function generateRoundedIcons() {
    const inputPath = path.join(__dirname, 'static', 'icon.png');

    console.log('Generating round icons...');

    for (const size of sizes) {
        try {
            const resized = await sharp(inputPath)
                .resize(size, size)
                .toBuffer();

            const roundedBuffer = await sharp(resized)
                .composite([{
                    input: createCircleMask(size),
                    blend: 'dest-in'
                }])
                .png()
                .toBuffer();

            const outputPath = path.join(__dirname, 'static', 'icons', `icon-${size}.png`);
            await sharp(roundedBuffer).toFile(outputPath);
            console.log(`✓ Generated ${outputPath} (${size}x${size})`);
        } catch (err) {
            console.error(`✗ Failed to generate ${size}x${size}:`, err.message);
        }
    }

    // Generate main round icon for Electron
    try {
        const size = 512;
        const resized = await sharp(inputPath)
            .resize(size, size)
            .toBuffer();

        const roundedBuffer = await sharp(resized)
            .composite([{
                input: createCircleMask(size),
                blend: 'dest-in'
            }])
            .png()
            .toBuffer();

        const outputPath = path.join(__dirname, 'static', 'icon-round.png');
        await sharp(roundedBuffer).toFile(outputPath);
        console.log(`✓ Generated ${outputPath} (${size}x${size}) - Electron icon`);
    } catch (err) {
        console.error(`✗ Failed to generate icon-round.png:`, err.message);
    }

    console.log('\nDone! All round icons generated.');
}

generateRoundedIcons().catch(console.error);

