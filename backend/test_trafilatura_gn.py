import trafilatura
import httpx
import asyncio

async def test_trafilatura(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/"
    }
    print(f"Testing URL: {url}")
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            print(f"Final URL: {resp.url}")
            print(f"Status Code: {resp.status_code}")
            content = trafilatura.extract(resp.text, include_comments=False)
            if content:
                print(f"Content Length: {len(content)}")
                print(f"Snippet: {content[:100]}...")
            else:
                print("Content extraction FAILED (None returned)")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test with a typical Google News redirect URL
    url = "https://news.google.com/rss/articles/CBMi9AFBVV95cUxOVlFWV3dybEpZUE5fUVBkck5meTVwaTJFd21oYkN3Vk9JdWNCOG8yVlhJWUlGYXU3RFhjektFQ2RwLWIwYzl3SUZiaG5QYjl0RUlNZmdER3JPX0JNOVZObk1pT0NMSmJPLWFaZWdreFlwZ1hRa1pPTHM3UnZmTjJDTmk5Nmd3NmgxVXlWcTVNaDNHcGViSUdNeEFjU3VJX2xESFEwOXFVczJwOHVSS0tydEdpZDM5eEdkMm5sY3hGeFc4ek9hMmNBMTE1ZHFfRENROWlJS0ZLT2YzTzNSWVJCOWIyVTNFMy0xaVpBYUkyblh0UVY10gH8AUFVX3lxTE1EeEZBcEhRbm5PX2NDU1h6eWtyMC10WlVIWXlHMXR2VzZKMWY0SUFGZ1FFRTZlMVZMU2hDa0VsQjgwSld2VmxpbnMyNi1UWk5XeVpEd0EyMzY5cEpib21UQzRBNDVGYk1kUDRUbTFZTUV2bnFlcGFBWDVnTkZEMUZPdlVEVXdsM1RGY242a0JLNzdXRlZBaXk0M083TjhqYXJManRPM1ZnSFVZWGJtNmNMRXl5SXdVUHZIWGRGLUw0R3pWMDZxeWdkd1hTV05UdlhfWVZZUjdUV0xPbXVfX3Jyejh2Z25qTnFJOHlNb3p3MktnZHA0Z3NOYm9scg?oc=5&hl=en-IN&gl=IN&ceid=IN:en"
    asyncio.run(test_trafilatura(url))
