import fs from 'fs';
import path from 'path';
import { parquetRead, parquetMetadata } from 'hyparquet';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const relativePath = process.argv[2] || '../sample_aws_data/NATIONAL_SUMMARY_LABOR.parquet';
const filePath = path.resolve(process.cwd(), relativePath);

console.log('Reading:', filePath);

try {
    const buffer = fs.readFileSync(filePath);
    const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);

    const metadata = parquetMetadata(arrayBuffer);
    console.log('\n--- METADATA ---');
    if (metadata.row_groups.length > 0) {
        const columns = metadata.row_groups[0].columns;
        const headers = columns.map(c => c.meta_data.path_in_schema[0]);
        console.log('Columns:', headers);
    }

    console.log('\n--- DATA (First 10 Rows) ---');
    parquetRead({
        file: arrayBuffer,
        onComplete: (data) => {
            // header mapping
            const columns = metadata.row_groups[0].columns;
            const headers = columns.map(c => c.meta_data.path_in_schema[0]);

            const rows = data.slice(0, 10).map(row => {
                const obj = {};
                headers.forEach((h, i) => {
                    obj[h] = row[i];
                });
                return obj;
            });
            console.log(rows);

            // Quick stats on unique values for important columns
            console.log('\n--- UNIQUE VALUES ---');
            const uniqueStates = new Set();
            const uniqueCommodities = new Set();
            const uniqueStats = new Set();
            const uniqueYears = new Set();
            const uniqueRegions = new Set();
            const uniqueClass = new Set();

            data.forEach(row => {
                const obj = {};
                headers.forEach((h, i) => {
                    obj[h] = row[i];
                });
                if (obj.state_name) uniqueStates.add(obj.state_name);
                if (obj.commodity_desc) uniqueCommodities.add(obj.commodity_desc);
                if (obj.statisticcat_desc) uniqueStats.add(obj.statisticcat_desc);
                if (obj.year) uniqueYears.add(obj.year);
                if (obj.region_desc) uniqueRegions.add(obj.region_desc);
                if (obj.class_desc) uniqueClass.add(obj.class_desc);
            });

            console.log('States:', Array.from(uniqueStates).slice(0, 10));
            console.log('Commodities:', Array.from(uniqueCommodities));
            console.log('Statistic Categories:', Array.from(uniqueStats));
            console.log('Years:', Array.from(uniqueYears).sort());
            console.log('Class Desc:', Array.from(uniqueClass));
        }
    });

} catch (e) {
    console.error('Error:', e);
}
