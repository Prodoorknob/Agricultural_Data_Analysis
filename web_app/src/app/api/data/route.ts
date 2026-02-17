import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const S3_BUCKET_URL = 'https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets';

export async function GET(request: NextRequest) {
    const searchParams = request.nextUrl.searchParams;
    const filename = searchParams.get('file');

    if (!filename) {
        return NextResponse.json({ error: 'File parameter is required' }, { status: 400 });
    }

    // Security check: simple path traversal prevention
    if (filename.includes('..') || !filename.endsWith('.parquet')) {
        return NextResponse.json({ error: 'Invalid file path' }, { status: 400 });
    }

    const s3Url = `${S3_BUCKET_URL}/${filename}`;

    // Check if we should use local data (Development Mode)
    // The filename from frontend will be like "partitioned_states/INDIANA.parquet" 
    // BUT our new structure is just "INDIANA.parquet" inside final_data
    // Let's strip the directory prefix if present for local serving
    const localFilename = filename.split('/').pop();
    // Use path.join to ensure correct separators on Windows
    const localPath = path.join(process.cwd(), 'final_data', localFilename || '');

    // Determine if running on Vercel (production) or locally
    const isVercel = process.env.VERCEL === '1';
    const localFileExists = !isVercel && fs.existsSync(localPath);

    console.log(`[API] Request for ${filename}`);
    console.log(`[API] Environment: ${isVercel ? 'Vercel (Production)' : 'Local Development'}`);
    if (!isVercel) {
        console.log(`[API] CWD: ${process.cwd()}`);
        console.log(`[API] Resolved Local Path: ${localPath}`);
        console.log(`[API] File Exists: ${localFileExists}`);
    }

    try {
        let arrayBuffer: ArrayBuffer;
        let contentType = 'application/octet-stream';

        // Try local file first (only in development, not on Vercel)
        if (localFileExists) {
            console.log(`[API] Serving local file: ${localPath}`);
            const fileBuffer = fs.readFileSync(localPath);
            arrayBuffer = fileBuffer.buffer.slice(fileBuffer.byteOffset, fileBuffer.byteOffset + fileBuffer.byteLength);
        } else {
            // On Vercel or if local file doesn't exist, proxy to S3
            console.log(`[API] ${isVercel ? '(Vercel) ' : ''}Proxying to S3: ${s3Url}`);
            const response = await fetch(s3Url, { cache: 'no-store' });

            if (!response.ok) {
                return NextResponse.json(
                    { error: `S3 Error: ${response.statusText}` },
                    { status: response.status }
                );
            }
            arrayBuffer = await response.arrayBuffer();
        }

        // Return the binary data with appropriate headers
        return new NextResponse(arrayBuffer, {
            headers: {
                'Content-Type': contentType,
                'Cache-Control': 'public, max-age=3600'
            }
        });

    } catch (error) {
        console.error('[API] Fetch error:', error);
        return NextResponse.json(
            { error: `Internal Server Error: ${error instanceof Error ? error.message : String(error)}` },
            { status: 500 }
        );
    }
}
