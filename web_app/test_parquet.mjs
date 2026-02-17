
import { parquetRead, parquetMetadata } from 'hyparquet';
import fs from 'fs';

async function testHyparquet() {
    const filename = 'web_app/final_data/IN.parquet';
    console.log(`Reading ${filename}...`);

    if (!fs.existsSync(filename)) {
        console.error('File not found!');
        return;
    }

    const buffer = fs.readFileSync(filename);
    const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);

    console.log('Metadata...');
    const metadata = parquetMetadata(arrayBuffer);

    if (!metadata || !metadata.row_groups || metadata.row_groups.length === 0) {
        console.error('No row groups or metadata!');
        return;
    }

    const columnHelpers = metadata.row_groups[0].columns;
    const headers = columnHelpers.map(c => c.meta_data.path_in_schema[0]);
    console.log('Headers:', headers);

    console.log('Reading data...');
    // Mock the same logic as serviceData.ts
    await new Promise((resolve, reject) => {
        parquetRead({
            file: arrayBuffer,
            onComplete: (data) => {
                console.log(`Read ${data.length} rows.`);

                // Map first row
                if (data.length > 0) {
                    const row = data[0];
                    const obj = {};
                    headers.forEach((header, index) => {
                        obj[header] = row[index];
                    });
                    console.log('First Row:', obj);
                }

                // Check for AREA PLANTED specifically
                // headers might be mismatched with data indices?
                // Let's verify headers order vs data order

                const statIdx = headers.indexOf('statisticcat_desc');
                const commIdx = headers.indexOf('commodity_desc');

                if (statIdx === -1) {
                    console.error('statisticcat_desc not found in headers!');
                } else {
                    const planted = data.filter(r => r[statIdx] === 'AREA PLANTED');
                    console.log(`Found ${planted.length} AREA PLANTED rows.`);
                    if (planted.length > 0) {
                        console.log('Sample planted row:', planted[0]);
                    }
                }

                resolve();
            }
        });
    });
}

testHyparquet().catch(console.error);
