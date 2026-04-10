import feedparser
import httpx
import asyncio

async def test_bhaskar_feed():
    url = "https://www.bhaskar.com/rss-v1--category-1061.xml"
    print(f"Attempting to fetch: {url}")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
        try:
            response = await client.get(url)
            print(f"Status Code: {response.status_code}")
            
            feed = feedparser.parse(response.text)
            
            print(f"Feed Title: {feed.feed.get('title', 'Unknown')}")
            print(f"Total Entries Found: {len(feed.entries)}")
            
            if len(feed.entries) > 0:
                print("\n --- Sample Entry ---")
                entry = feed.entries[0]
                print(f"Title: {entry.get('title', 'N/A')}")
                print(f"Link: {entry.get('link', 'N/A')}")
                
                # Image check
                image_url = None
                if 'media_content' in entry:
                    image_url = entry.media_content[0]['url']
                elif 'enclosures' in entry and entry.enclosures:
                    image_url = entry.enclosures[0]['url']
                
                print(f"Image URL: {image_url if image_url else 'Not found in standard tags'}")
                print(f"Summary Snippet: {entry.get('summary', 'N/A')[:100]}...")
            else:
                print("No entries found. The URL might be a redirect or index page.")
                
        except Exception as e:
            print(f"Error during fetch: {e}")

if __name__ == "__main__":
    asyncio.run(test_bhaskar_feed())
