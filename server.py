import asyncio
import os
import nodriver as uc
from aiohttp import web

PORT = int(os.environ.get('PORT', 8080))

async def solve_turnstile(siteurl: str) -> str:
    token = None
    browser = await uc.start(
        headless=True,
        browser_args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
        ]
    )
    try:
        tab = await browser.get(siteurl)
        await asyncio.sleep(3)

        for _ in range(30):
            await asyncio.sleep(1)
            try:
                result = await tab.evaluate("""
                    (function() {
                        if (window.__turnstileToken) return window.__turnstileToken;
                        const inputs = document.querySelectorAll(
                            'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]'
                        );
                        for (const input of inputs) {
                            if (input.value && input.value.length > 10) return input.value;
                        }
                        return null;
                    })()
                """)
                if result and result != 'null':
                    token = result
                    break
            except Exception as e:
                print(f'[!] Script error: {e}')
    finally:
        browser.stop()

    return token


async def handle_solve(request):
    try:
        body = await request.json()
        siteurl = body.get('siteurl')
        if not siteurl:
            return web.json_response({'error': 'siteurl required'}, status=400)

        print(f'[+] Solving for {siteurl}')
        token = await solve_turnstile(siteurl)

        if token:
            print(f'[+] Token: {token[:30]}...')
            return web.json_response({'token': token})
        else:
            return web.json_response({'error': 'failed to solve'}, status=500)

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
