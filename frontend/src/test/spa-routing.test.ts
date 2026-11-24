import { describe, it, expect } from 'vitest';

/**
 * Simulates the CloudFront Function 'SpaRoutingFunction' defined in infrastructure/template.yaml.
 * Verifies that client-side SPA routes are rewritten to /index.html while static asset requests
 * containing file extensions are preserved, allowing S3 to return genuine 404/403 responses.
 */
function simulateCloudFrontSpaRouting(uri: string): { rewrittenUri: string; isRewritten: boolean } {
  let rewrittenUri = uri;
  // Check if URI is root or lacks a file extension (e.g., /admin, /locations/123)
  if (uri === '/' || !uri.includes('.')) {
    rewrittenUri = '/index.html';
    return { rewrittenUri, isRewritten: true };
  }
  return { rewrittenUri, isRewritten: false };
}

/**
 * Simulates CloudFront distribution response logic given an S3 origin status.
 */
function simulateDistributionResponse(uri: string, s3ObjectExists: boolean, s3Authorized: boolean) {
  const { rewrittenUri, isRewritten } = simulateCloudFrontSpaRouting(uri);

  if (isRewritten) {
    // S3 serves the existing /index.html with HTTP 200
    return {
      status: 200,
      contentType: 'text/html',
      servedUri: rewrittenUri,
    };
  }

  // Request targeted a specific asset path
  if (!s3Authorized) {
    return {
      status: 403,
      contentType: 'application/xml',
      servedUri: uri,
      error: 'AccessDenied',
    };
  }

  if (!s3ObjectExists) {
    return {
      status: 404,
      contentType: 'application/xml',
      servedUri: uri,
      error: 'NoSuchKey',
    };
  }

  const ext = uri.split('.').pop()?.toLowerCase();
  const contentTypes: Record<string, string> = {
    js: 'application/javascript',
    css: 'text/css',
    png: 'image/png',
    jpg: 'image/jpeg',
    svg: 'image/svg+xml',
    mp4: 'video/mp4',
    json: 'application/json',
  };

  return {
    status: 200,
    contentType: contentTypes[ext || ''] || 'application/octet-stream',
    servedUri: uri,
  };
}

describe('CloudFront SPA Routing & Missing Asset Correctness', () => {
  it('rewrites valid client-side SPA routes to /index.html (route refresh safety)', () => {
    const spaRoutes = [
      '/',
      '/locations',
      '/locations/iitb-mess-h12-14',
      '/locations/vitap-canteen-1',
      '/recommendations',
      '/historical',
      '/admin',
      '/admin/reports',
    ];

    for (const route of spaRoutes) {
      const res = simulateDistributionResponse(route, true, true);
      expect(res.status).toBe(200);
      expect(res.contentType).toBe('text/html');
      expect(res.servedUri).toBe('/index.html');
    }
  });

  it('preserves genuine 404 status for missing JavaScript assets', () => {
    const res = simulateDistributionResponse('/assets/missing-bundle-999.js', false, true);
    expect(res.status).toBe(404);
    expect(res.servedUri).toBe('/assets/missing-bundle-999.js');
    expect(res.contentType).not.toBe('text/html');
  });

  it('preserves genuine 404 status for missing CSS assets', () => {
    const res = simulateDistributionResponse('/assets/theme-nonexistent.css', false, true);
    expect(res.status).toBe(404);
    expect(res.servedUri).toBe('/assets/theme-nonexistent.css');
    expect(res.contentType).not.toBe('text/html');
  });

  it('preserves genuine 404 status for missing image and video assets', () => {
    const missingMedia = ['/images/banner-404.png', '/icons/logo-missing.svg', '/media/drone-bg.mp4'];

    for (const mediaUri of missingMedia) {
      const res = simulateDistributionResponse(mediaUri, false, true);
      expect(res.status).toBe(404);
      expect(res.servedUri).toBe(mediaUri);
      expect(res.contentType).not.toBe('text/html');
    }
  });

  it('preserves genuine 403 status on S3 access denial without masking as 200 index.html', () => {
    const res = simulateDistributionResponse('/restricted/secret-asset.json', true, false);
    expect(res.status).toBe(403);
    expect(res.servedUri).toBe('/restricted/secret-asset.json');
    expect(res.contentType).not.toBe('text/html');
  });
});
