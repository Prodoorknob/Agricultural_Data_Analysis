
import fs from 'fs';
import readline from 'readline';
import path from 'path';

const rawDataDir = 'C:\\Users\\rajas\\Documents\\VS_Code\\Agricultural_Data_Analysis\\raw_data';
const files = [
    'nass_quickstats_data_animals_products.csv',
    'nass_quickstats_data_Economics.csv',
    'nass_crops_field_crops.csv',
    'nass_crops_fruit_tree.csv'
];

async function inspectFile(filename) {
    const filePath = path.join(rawDataDir, filename);
    console.log(`\n--- Inspecting ${filename} ---`);

    try {
        const fileStream = fs.createReadStream(filePath);
        const rl = readline.createInterface({
            input: fileStream,
            crlfDelay: Infinity
        });

        let lineCount = 0;
        let headers = [];

        for await (const line of rl) {
            if (lineCount === 0) {
                headers = line.split(',');
                console.log('Headers:', headers);
            } else if (lineCount <= 5) {
                console.log(`Row ${lineCount}:`, line);
            } else {
                break;
            }
            lineCount++;
        }
    } catch (error) {
        console.error(`Error reading ${filename}:`, error.message);
    }
}

async function main() {
    for (const file of files) {
        await inspectFile(file);
    }
}

main();
