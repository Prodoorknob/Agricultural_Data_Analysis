const fs = require('fs');
const path = require('path');
const { parquetRead, parquetMetadata } = require('hyparquet');

const filePath = path.resolve(__dirname, '../../sample_aws_data/NATIONAL_SUMMARY_LANDUSE.parquet');

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

    console.log('\n--- DATA (First 5 Rows) ---');
    parquetRead({
        file: arrayBuffer,
        onComplete: (data) => {
            // header mapping
            const columns = metadata.row_groups[0].columns;
            const headers = columns.map(c => c.meta_data.path_in_schema[0]);

            const rows = data.slice(0, 5).map(row => {
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

            data.forEach(row => {
                const obj = {};
                headers.forEach((h, i) => {
                    obj[h] = row[i];
                });
                if (obj.state_name) uniqueStates.add(obj.state_name);
                if (obj.commodity_desc) uniqueCommodities.add(obj.commodity_desc);
                if (obj.statisticcat_desc) uniqueStats.add(obj.statisticcat_desc);
            });

            console.log('States:', Array.from(uniqueStates).slice(0, 10));
            console.log('Commodities:', Array.from(uniqueCommodities));
            console.log('Statistic Categories:', Array.from(uniqueStats));
        }
    });

} catch (e) {
    console.error('Error:', e);
}
