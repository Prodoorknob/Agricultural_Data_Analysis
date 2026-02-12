import { NextRequest, NextResponse } from 'next/server';

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
    console.log(`[API] Proxying request to ${s3Url}`);

    try {
        const response = await fetch(s3Url);

        if (!response.ok) {
            return NextResponse.json(
                { error: `S3 Error: ${response.statusText}` },
                { status: response.status }
            );
        }

        const arrayBuffer = await response.arrayBuffer();

        // Return the binary data with appropriate headers
        return new NextResponse(arrayBuffer, {
            headers: {
                'Content-Type': 'application/octet-stream',
                'Cache-Control': 'public, max-age=3600'
            }
        });

    } catch (error) {
        console.error('[API] Fetch error:', error);
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
    }
}
