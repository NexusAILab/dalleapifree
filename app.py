import asyncio
import time
import json
from aiohttp import ClientSession, BaseConnector
from urllib.parse import quote
from typing import List, Dict
from flask import Flask, jsonify, request, send_from_directory
import os 

app = Flask(__name__)

try:
    from bs4 import BeautifulSoup
    has_requirements = True
except ImportError:
    has_requirements = False

BING_URL = "https://www.bing.com"
TIMEOUT_LOGIN = 1200
TIMEOUT_IMAGE_CREATION = 300
ERRORS = [
    "this prompt is being reviewed",
    "this prompt has been blocked",
    "we're working hard to offer image creator in more languages",
    "we can't create your images right now"
]
BAD_IMAGES = [
    "https://r.bing.com/rp/in-2zU3AJUdkgFe7ZKv19yPBHVs.png",
    "https://r.bing.com/rp/TX9QuO3WzcCJz1uaaSwQAz39Kb0.jpg",
]

def create_session(cookies: Dict[str, str], proxy: str = None, connector: BaseConnector = None) -> ClientSession:
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referrer-policy": "origin-when-cross-origin",
        "referrer": "https://www.bing.com/images/create/",
        "origin": "https://www.bing.com",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.54",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"111\", \"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"111\"",
        "sec-ch-ua-mobile": "?0",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
    }
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return ClientSession(headers=headers)

async def create_images(session: ClientSession, prompt: str, timeout: int = TIMEOUT_IMAGE_CREATION) -> List[str]:
    if not has_requirements:
        raise MissingRequirementsError('Install "beautifulsoup4" package')
    url_encoded_prompt = quote(prompt)
    payload = f"q={url_encoded_prompt}&rt=4&FORM=GENCRE"
    url = f"{BING_URL}/images/create?q={url_encoded_prompt}&rt=4&FORM=GENCRE"
    async with session.post(url, allow_redirects=False, data=payload, timeout=timeout) as response:
        response.raise_for_status()
        text = (await response.text()).lower()
        for error in ERRORS:
            if error in text:
                pass
                raise RuntimeError(f"Create images failed: {error}")
    if response.status != 302:
        url = f"{BING_URL}/images/create?q={url_encoded_prompt}&rt=3&FORM=GENCRE"
        async with session.post(url, allow_redirects=False, timeout=timeout) as response:
            if response.status != 302:
                raise RuntimeError(f"Create images failed. Code: {response.status}")

    redirect_url = response.headers["Location"].replace("&nfy=1", "")
    redirect_url = f"{BING_URL}{redirect_url}"
    request_id = redirect_url.split("id=")[1]
    async with session.get(redirect_url) as response:
        response.raise_for_status()

    polling_url = f"{BING_URL}/images/create/async/results/{request_id}?q={url_encoded_prompt}"
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            raise RuntimeError(f"Timeout error after {timeout} sec")
        async with session.get(polling_url) as response:
            if response.status != 200:
                raise RuntimeError(f"Polling images faild. Code: {response.status}")
            text = await response.text()
            if not text or "GenerativeImagesStatusPage" in text:
                await asyncio.sleep(1)
            else:
                break
    error = None
    try:
        error = json.loads(text).get("errorMessage")
    except:
        pass
    if error == "Pending":
        raise RuntimeError("Prompt is been blocked")
    elif error:
        raise RuntimeError(error)
    return read_images(text)

def read_images(html_content: str) -> List[str]:
    soup = BeautifulSoup(html_content, "html.parser")
    tags = soup.find_all("img", class_="mimg")
    if not tags:
        tags = soup.find_all("img", class_="gir_mmimg")
    images = [img["src"].split("?w=")[0] for img in tags]
    if any(im in BAD_IMAGES for im in images):
        raise RuntimeError("Bad images found")
    if not images:
        raise RuntimeError("No images found")
    return images

async def fetch_images(cookie, prompt):
    async with create_session(cookies={'_U': cookie}) as session:
        try:
            images = await create_images(session, prompt)
            return images
        except Exception as e:
            print(f"Error for cookie {cookie}: {e}")
            return []

@app.route('/images', methods=['GET'])
async def get_images():
    prompt = request.args.get('prompt', '')
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    cookies = [
        '1gDyr76kjtfdoSESMQyelziRf68svs00c3v7NGn_foZivt7hg9xYMnPREGDYZIbpHiqQjN1aQRgQEWTp49ASATzKWo6F370HaSRT7YSM2GYXN0hWb_eZ6Axt0faAskVG8Di0sGmoS4MQ8aUPIyPq87b2pMIFKJX030R2F90AQ_C7VfOt4TPdn0vfaN6Ob0hN8DrM9R8XJxW_VvuMD4xssWA',
        '1Z6MDLopA6Ew8hsPm7P_w7yvLB14APupuv2DfP1_OCxFgiI4tu3JgqW8R3OfFa_g7y23S0VBXwGkt4rUXDClC5JOB6v_wptkqLOWKiY0_ro9ajk26_kJmgkJUSGJuVk8PJ2rw_rWzWoaxulhBuwXtmjehadmzaMsIFl0OIkxNwVZzpqR2lWJtpMx_iTgyiBR5JIif-rj5DVRCsmeGI3E_vg',
        '1PuyuSqJ9DuJDOhGH6cXfeu1iSFX4TNicgY3DrL4FHgFJ-0qHlavA-dq5pJfxJwIte1GhhRZJ3JHKDqWKXposqmwslUbeMFtWOIyF4B75I2vsuWREIaTvl2GCVvj2WO1kSbBW2PoSmoftwQnDQLGFyaOA9gOBJD-EBogd7BMjrxhppa1_NKAHhGagXcFhHJDlc16prbPLk7xCGBY5Fppfp0bcmmfLGifFGxXPT3XQdJg',
        '1axEJnQWWspXv445u02fo0haaJ-zjnJrFGlKBpaLReoaRXX8_PpnFew9KM0ISoYI4vTvIG1kz_KuklFHZfPsaaQBtdLNWItySFZztq59fAi7VWXivvR183cqBeuwSvR_XQF5bM_DK4jFZJx3RxmM0_thcBcZVd5fLP6lYAFFku6a3GE63wSz03safei-fNDdWyRPh1gMDyaBm-SZ6TC4zkQ'
    ]
    tasks = [fetch_images(cookie, prompt) for cookie in cookies]
    results = await asyncio.gather(*tasks)
    all_images = [image for sublist in results for image in sublist]
    return jsonify(all_images)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
"""   
async def main():
    cookies = [
        '1gDyr76kjtfdoSESMQyelziRf68svs00c3v7NGn_foZivt7hg9xYMnPREGDYZIbpHiqQjN1aQRgQEWTp49ASATzKWo6F370HaSRT7YSM2GYXN0hWb_eZ6Axt0faAskVG8Di0sGmoS4MQ8aUPIyPq87b2pMIFKJX030R2F90AQ_C7VfOt4TPdn0vfaN6Ob0hN8DrM9R8XJxW_VvuMD4xssWA',
        '1Z6MDLopA6Ew8hsPm7P_w7yvLB14APupuv2DfP1_OCxFgiI4tu3JgqW8R3OfFa_g7y23S0VBXwGkt4rUXDClC5JOB6v_wptkqLOWKiY0_ro9ajk26_kJmgkJUSGJuVk8PJ2rw_rWzWoaxulhBuwXtmjehadmzaMsIFl0OIkxNwVZzpqR2lWJtpMx_iTgyiBR5JIif-rj5DVRCsmeGI3E_vg',
        '1PuyuSqJ9DuJDOhGH6cXfeu1iSFX4TNicgY3DrL4FHgFJ-0qHlavA-dq5pJfxJwIte1GhhRZJ3JHKDqWKXposqmwslUbeMFtWOIyF4B75I2vsuWREIaTvl2GCVvj2WO1kSbBW2PoSmoftwQnDQLGFyaOA9gOBJD-EBogd7BMjrxhppa1_NKAHhGagXcFhHJDlc16prbPLk7xCGBY5Fppfp0bcmmfLGifFGxXPT3XQdJg',
        '1axEJnQWWspXv445u02fo0haaJ-zjnJrFGlKBpaLReoaRXX8_PpnFew9KM0ISoYI4vTvIG1kz_KuklFHZfPsaaQBtdLNWItySFZztq59fAi7VWXivvR183cqBeuwSvR_XQF5bM_DK4jFZJx3RxmM0_thcBcZVd5fLP6lYAFFku6a3GE63wSz03safei-fNDdWyRPh1gMDyaBm-SZ6TC4zkQ'
    ]

    tasks = [fetch_images(cookie) for cookie in cookies]
    results = await asyncio.gather(*tasks)
    all_images = [image for sublist in results for image in sublist]
    print(f"All images: {all_images}")

asyncio.run(main())
"""   
