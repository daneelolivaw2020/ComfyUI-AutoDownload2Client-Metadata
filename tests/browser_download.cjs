/* Local Firefox integration test; ComfyUI API/graph are stubs, extension is unmodified.
 * npm install --no-save playwright
 * npx playwright install firefox
 * python tests/export_fixture.py /tmp/fixture.json
 * node tests/browser_download.cjs /tmp/fixture.json /tmp/downloads
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { firefox } = require('playwright');

const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const output = path.resolve(process.argv[3]);
fs.mkdirSync(output, { recursive: true });
const extension = fs.readFileSync(path.join(__dirname, '../web/auto_download.js'), 'utf8');
const api = `export const api = new EventTarget();`;
const app = `import {api} from './api.js';
const nodes = [2, 99].map(id => ({id, dirty: 0, setDirtyCanvas() { this.dirty++; }}));
export const app = {graph: {findNodesByType() {return nodes;}},
 registerExtension(extension) {window.extension = extension; window.ready = extension.setup();}};
window.test = {nodes, api, setupAgain: () => window.extension.setup(),
 emit: data => api.dispatchEvent(new CustomEvent('auto_download_direct', {detail: data}))};`;
const child = `<!doctype html><title>AutoDownload test child</title>
<p>ComfyUI extension iframe fixture</p>
<script>window.documentLoads = (window.documentLoads || 0) + 1;</script>
<script type="module" src="/extensions/autodownload/auto_download.js"></script>`;

async function main() {
    const server = http.createServer((req, res) => {
        if (req.url === '/scripts/app.js' || req.url === '/scripts/api.js' || req.url === '/extensions/autodownload/auto_download.js') {
            res.setHeader('Content-Type', 'text/javascript');
            res.end(req.url.includes('app.js') ? app : req.url.includes('api.js') ? api : extension);
        } else if (req.url === '/child') {
            res.setHeader('Content-Type', 'text/html'); res.end(child);
        } else {
            const port = server.address().port;
            res.setHeader('Content-Type', 'text/html');
            res.end(`<!doctype html><title>Notebook iframe fixture</title>
<button id="fullscreen" onclick="document.querySelector('iframe').requestFullscreen()">View output fullscreen</button>
<iframe src="http://127.0.0.1:${port}/child" sandbox="allow-scripts allow-same-origin allow-downloads" allowfullscreen width="900" height="500"></iframe>`);
        }
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let browser;
    try {
        browser = await firefox.launch({ headless: true });
        const context = await browser.newContext({ acceptDownloads: true });
        const page = await context.newPage();
        const errors = [];
        const saved = [];
        let downloadCount = 0;
        page.on('pageerror', error => errors.push(error.message));
        page.on('download', download => {
            downloadCount++;
            saved.push((async () => {
                const filename = download.suggestedFilename();
                const target = path.join(output, filename);
                assert.equal(await download.failure(), null);
                await download.saveAs(target);
                return filename;
            })());
        });
        await page.goto(`http://localhost:${server.address().port}/`);
        const frame = page.frames().find(frame => frame.url().includes('/child'));
        await frame.waitForFunction(() => window.test && window.ready);
        await frame.evaluate(() => window.ready);
        async function emitRun(run, expected) {
            const before = downloadCount;
            await frame.evaluate(run => run.forEach(payload => window.test.emit(payload)), run);
            await frame.waitForFunction(size => window.test.nodes[0].imgs?.filter(img => img.complete && img.naturalWidth).length === size, expected);
            // A separate browser download notification may arrive after image decoding.
            await page.waitForFunction(() => true);
            const deadline = Date.now() + 10000;
            while (downloadCount < before + run.length && Date.now() < deadline) {
                await new Promise(resolve => setTimeout(resolve, 50));
            }
            assert.equal(downloadCount - before, run.length);
            assert.equal(await frame.evaluate(() => window.test.nodes[1].imgs), undefined);
        }
        await emitRun(fixture.runs[0], 1);
        await emitRun(fixture.runs[1], 4);
        // Repeated extension setup must not produce duplicate downloads.
        await frame.evaluate(() => window.test.setupAgain());
        await page.locator('#fullscreen').click();
        await page.waitForFunction(() => !!document.fullscreenElement);
        await emitRun(fixture.runs[2], 1);
        await page.evaluate(() => document.exitFullscreen());
        await emitRun(fixture.runs[3], 2);
        assert.equal(await frame.evaluate(() => window.documentLoads), 1);
        const names = await Promise.all(saved);
        assert.equal(names.length, 8);
        assert.equal(new Set(names).size, 8);
        const payloads = fixture.runs.flat();
        for (const payload of payloads) {
            assert.deepEqual(fs.readFileSync(path.join(output, payload.filename)), Buffer.from(payload.data, 'base64'));
        }
        // Removing the graph node must not stop the actual download.
        await frame.evaluate(() => {window.test.nodes.splice(0, 1);});
        const extra = {...fixture.runs[0][0], filename: 'removed-node.png'};
        const removedDownload = page.waitForEvent('download');
        await frame.evaluate(extra => window.test.emit(extra), extra);
        await removedDownload;
        await Promise.all(saved);
        assert.equal(downloadCount, 9);
        assert.deepEqual(errors, []);
        const report = {browser: await browser.version(), downloads: downloadCount,
            crossOriginIframe: true, fullscreen: true, iframeReloads: 0,
            pngBytesUnchanged: true, duplicateSetup: 'passed', wrongNodePreview: 'passed'};
        fs.writeFileSync(path.join(output, 'browser-report.json'), JSON.stringify(report, null, 2));
        console.log(JSON.stringify(report, null, 2));
        await context.close();
    } finally {
        if (browser) await browser.close();
        await new Promise(resolve => server.close(resolve));
    }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
