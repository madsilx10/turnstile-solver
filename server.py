import asyncio
import json
import os
from aiohttp import web
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

PORT = int(os.environ.get('PORT', 8080))

async def solve_turnstile(sitekey: str, siteurl: str) -> str:
    options = ChromiumOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--headless=new')

    token = None

    async with Chrome(options=options) as browser:
        tab = await browser.start()

        # Intercept turnstile token via network monitoring
        captured = {}

        async def on_request(event):
            try:
                req = event.get('params', {}).get('request', {})
                url = req.get('url', '')
                post_data = req.get('postData', '')
                if 'challenges.cloudflare.com' in url and 'turnstile' in url.lower():
                    captured['url'] = url
                if post_data and 'token' in post_data.lower():
                    captured['post'] = post_data
            except Exception:
                pass

        # Inject script to intercept turnstile token
        inject_script = """
        (function() {
            const originalFetch = window.fetch;
            window.fetch = async function(...args) {
                const response = await originalFetch.apply(this, args);
                return response;
            };

            // Poll for turnstile token
            const checkInterval = setInterval(() => {
                const inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
                inputs.forEach(input => {
                    if (input.value && input.value.length > 10) {
                        window.__turnstileToken = input.value;
                        clearInterval(checkInterval);
                    }
                });
            }, 100);
        })();
        """

        await tab.go_to(siteurl)
        await asyncio.sleep(3)

        # Try to get token from DOM
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                result = await tab.execute_script("""
                    (function() {
                        // Check window variable
                        if (window.__turnstileToken) return window.__turnstileToken;
                        
                        // Check input fields
                        const inputs = document.querySelectorAll(
                            'input[name="cf-turnstile-response"], ' +
                            'input[name="cf_turnstile_response"], ' +
                            'textarea[name="cf-turnstile-response"]'
                        );
                        for (const input of inputs) {
                            if (input.value && input.value.length > 10) return input.value;
                        }
                        return null;
                    })()
                """)
                if result:
                    token = result
                    break
            except Exception:
                pass

    return token


async def handle_solve(request):
    try:
        body = await request.json()
        sitekey = body.get('sitekey')
        siteurl = body.get('siteurl')

        if not sitekey or not siteurl:
            return web.json_response({'error': 'sitekey and siteurl required'}, status=400)

        print(f'[+] Solving turnstile for {siteurl} sitekey={sitekey}')
        token = await solve_turnstile(sitekey, siteurl)

        if token:
            print(f'[+] Token solved: {token[:30]}...')
            return web.json_response({'token': token})
        else:
            print('[!] Failed to get token')
            return web.json_response({'error': 'failed to solve turnstile'}, status=500)

    except Exception as e:
        print(f'[!] Error: {e}')
        return web.json_response({'error': str(e)}, status=500)


async def handle_health(request):
    return web.json_response({'status': 'ok'})


app = web.Application()
app.router.add_post('/solve', handle_solve)
app.router.add_get('/health', handle_health)

if __name__ == '__main__':
    print(f'[+] Turnstile solver running on port {PORT}')
    web.run_app(app, host='0.0.0.0', port=PORT)
